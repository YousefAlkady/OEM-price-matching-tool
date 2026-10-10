import hashlib
import json
import logging
import re
import time
from datetime import timedelta

import requests
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

# one retry for a per-second burst limit; RapidAPI allows 5-25 req/s depending on plan
BURST_RETRY_DELAY = 1.0

# param names that hold part numbers; normalized in the cache key so
# "86551-AA000", "86551AA000" and "86551 aa000" share one cache entry
PART_NO_PARAMS = ('articleNo', 'articleOemNo')

DEFAULT_CACHE_TTL_DAYS = 30
DEFAULT_USER_CALLS_PER_MINUTE = 30


def normalize_part_no(value):
    """Upper-case and drop everything that is not a letter or digit."""
    return re.sub(r'[^0-9A-Z]', '', str(value or '').upper())


def _error(code, message):
    # every failure carries both keys so callers can use either
    return {"error": code, "message": message}


def cache_key(method, endpoint, params=None, payload=None):
    def norm(data):
        if not isinstance(data, dict):
            return data
        return {k: (normalize_part_no(v) if k in PART_NO_PARAMS else v) for k, v in data.items()}
    raw = json.dumps([method, endpoint, norm(params), norm(payload)], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class TecdocApiAbstract(models.AbstractModel):
    _name = 'tecdoc.api.abstract'
    _description = 'RapidAPI Integration Abstract Model'

    @api.model
    def _get_int_param(self, name, default):
        try:
            return int(self.env['ir.config_parameter'].sudo().get_param(name, default))
        except (TypeError, ValueError):
            return default

    @api.model
    def _month_start(self):
        return fields.Datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @api.model
    def get_monthly_usage(self):
        """Billed calls this month for the current company, and the configured budget (0 = no cap)."""
        used = self.env['tecdoc.api.log'].sudo().search_count([
            ('billed', '=', True),
            ('company_id', '=', self.env.company.id),
            ('create_date', '>=', self._month_start()),
        ])
        return used, self._get_int_param('tecdoc.monthly_call_budget', 0)

    @api.model
    def _check_limits(self):
        """Return an error dict if this call must not go out, else None."""
        used, budget = self.get_monthly_usage()
        if budget and used >= budget:
            return _error("budget_exceeded", f"Monthly API budget reached ({used}/{budget} calls). An administrator can raise it in TecDoc settings.")
        if budget and used >= budget * 0.8:
            _logger.warning("TecDoc API budget at %s/%s calls this month", used, budget)

        per_minute = self._get_int_param('tecdoc.user_calls_per_minute', DEFAULT_USER_CALLS_PER_MINUTE)
        if per_minute:
            recent = self.env['tecdoc.api.log'].sudo().search_count([
                ('billed', '=', True),
                ('create_uid', '=', self.env.uid),
                ('create_date', '>=', fields.Datetime.now() - timedelta(seconds=60)),
            ])
            if recent >= per_minute:
                return _error("rate_limit", "Too many searches in the last minute. Please wait a moment and try again.")
        return None

    @api.model
    def _log_call(self, endpoint, method, params, payload, status, response_code=0, error=None, billed=False, duration_ms=0, key=None):
        self.env['tecdoc.api.log'].sudo().create({
            'endpoint': endpoint,
            'method': method,
            'payload': json.dumps(params or payload or {}, default=str)[:2000],
            'params_hash': key,
            'status': status,
            'response_code': response_code,
            'error_message': error,
            'billed': billed,
            'duration_ms': duration_ms,
            'company_id': self.env.company.id,
        })

    @api.model
    def _make_rapidapi_request(self, endpoint, method="GET", payload=None, params=None, use_cache=True):
        key = cache_key(method, endpoint, params, payload)
        Cache = self.env['tecdoc.api.cache'].sudo()

        if use_cache:
            cached = Cache.get_valid(key)
            if cached is not None:
                self._log_call(endpoint, method, params, payload, 'cached', key=key)
                return cached

        icp = self.env['ir.config_parameter'].sudo()
        rapidapi_key = icp.get_param('tecdoc.rapidapi_key', '')
        rapidapi_host = icp.get_param('tecdoc.rapidapi_host', 'auto-parts-catalog.p.rapidapi.com')
        url = f"https://{rapidapi_host}{endpoint}"

        if not rapidapi_key:
            _logger.error("RapidAPI Key is not configured in settings.")
            return _error("missing_key", "RapidAPI Key is not configured in settings.")

        blocked = self._check_limits()
        if blocked:
            self._log_call(endpoint, method, params, payload, 'error', error=blocked['message'], key=key)
            return blocked

        headers = {
            "x-rapidapi-key": rapidapi_key,
            "x-rapidapi-host": rapidapi_host,
            "Content-Type": "application/x-www-form-urlencoded" if method == "POST" else "application/json",
        }

        result = _error("rate_limit", "RapidAPI rate limit hit. Please wait a moment and try again.")
        for attempt in (1, 2):
            started = time.monotonic()
            try:
                _logger.info("RapidAPI %s: %s", method, url)
                if method == "POST":
                    response = requests.post(url, data=payload, headers=headers, timeout=15)
                else:
                    response = requests.get(url, params=params, headers=headers, timeout=15)
            except requests.exceptions.RequestException as exc:
                _logger.error("RapidAPI request failed: %s", exc)
                result = _error("network", "Network error connecting to RapidAPI. Please check your internet connection.")
                self._log_call(endpoint, method, params, payload, 'error', error=str(exc), key=key)
                return result

            duration_ms = int((time.monotonic() - started) * 1000)
            status = response.status_code
            # RapidAPI counts every request that reaches it, including errors
            log = dict(response_code=status, billed=True, duration_ms=duration_ms, key=key)

            if status == 429:
                remaining = response.headers.get("x-ratelimit-requests-remaining")
                if remaining is not None and str(remaining).strip() == "0":
                    result = _error("quota_exceeded", "You have used all your RapidAPI requests for this month. Please upgrade your plan.")
                    self._log_call(endpoint, method, params, payload, 'error', error=result['message'], **log)
                    return result
                self._log_call(endpoint, method, params, payload, 'error', error="burst rate limit", **log)
                if attempt == 1:
                    _logger.warning("RapidAPI 429 burst limit for %s, retrying once", url)
                    time.sleep(BURST_RETRY_DELAY)
                    continue
                return result

            if status == 401:
                result = _error("unauthorized", "Invalid API Key! Please double-check your RapidAPI Key in Settings.")
            elif status == 403:
                result = _error("not_subscribed", "Your RapidAPI Key is valid but not subscribed to the 'Auto Parts Catalog' API. Subscribe to a plan on RapidAPI to activate it.")
            elif status >= 400:
                _logger.error("RapidAPI HTTP %s for %s", status, url)
                result = _error("http_%s" % status, f"RapidAPI returned HTTP {status}.")
            else:
                try:
                    result = response.json()
                except ValueError:
                    result = _error("bad_response", "RapidAPI returned a response that is not valid JSON.")

            failed = isinstance(result, dict) and "error" in result and "message" in result
            self._log_call(endpoint, method, params, payload, 'error' if failed else 'success',
                           error=result.get('message') if failed else None, **log)
            if not failed and use_cache:
                ttl = self._get_int_param('tecdoc.cache_ttl_days', DEFAULT_CACHE_TTL_DAYS)
                Cache.store(key, endpoint, result, ttl)
            return result

        return result
