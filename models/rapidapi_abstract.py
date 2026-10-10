import logging
import time

import requests
from odoo import models, api

_logger = logging.getLogger(__name__)

# one retry for a per-second burst limit; RapidAPI allows 5-25 req/s depending on plan
BURST_RETRY_DELAY = 1.0


def _error(code, message):
    # every failure carries both keys so callers can use either
    return {"error": code, "message": message}


class TecdocApiAbstract(models.AbstractModel):
    _name = 'tecdoc.api.abstract'
    _description = 'RapidAPI Integration Abstract Model'

    @api.model
    def _make_rapidapi_request(self, endpoint, method="GET", payload=None, params=None):
        icp = self.env['ir.config_parameter'].sudo()
        rapidapi_key = icp.get_param('tecdoc.rapidapi_key', '')
        rapidapi_host = icp.get_param('tecdoc.rapidapi_host', 'auto-parts-catalog.p.rapidapi.com')
        url = f"https://{rapidapi_host}{endpoint}"

        if not rapidapi_key:
            _logger.error("RapidAPI Key is not configured in settings.")
            return _error("missing_key", "RapidAPI Key is not configured in settings.")

        headers = {
            "x-rapidapi-key": rapidapi_key,
            "x-rapidapi-host": rapidapi_host,
            "Content-Type": "application/x-www-form-urlencoded" if method == "POST" else "application/json",
        }

        for attempt in (1, 2):
            try:
                _logger.info("RapidAPI %s: %s", method, url)
                if method == "POST":
                    response = requests.post(url, data=payload, headers=headers, timeout=15)
                else:
                    response = requests.get(url, params=params, headers=headers, timeout=15)
            except requests.exceptions.RequestException as exc:
                _logger.error("RapidAPI request failed: %s", exc)
                return _error("network", "Network error connecting to RapidAPI. Please check your internet connection.")

            status = response.status_code
            if status == 429:
                remaining = response.headers.get("x-ratelimit-requests-remaining")
                if remaining is not None and str(remaining).strip() == "0":
                    return _error("quota_exceeded", "You have used all your RapidAPI requests for this month. Please upgrade your plan.")
                # per-second burst: wait once and retry
                if attempt == 1:
                    _logger.warning("RapidAPI 429 burst limit for %s, retrying once", url)
                    time.sleep(BURST_RETRY_DELAY)
                    continue
                return _error("rate_limit", "RapidAPI rate limit hit. Please wait a moment and try again.")
            if status == 401:
                return _error("unauthorized", "Invalid API Key! Please double-check your RapidAPI Key in Settings.")
            if status == 403:
                return _error("not_subscribed", "Your RapidAPI Key is valid but not subscribed to the 'Auto Parts Catalog' API. Subscribe to a plan on RapidAPI to activate it.")
            if status >= 400:
                _logger.error("RapidAPI HTTP %s for %s", status, url)
                return _error("http_%s" % status, f"RapidAPI returned HTTP {status}.")

            try:
                return response.json()
            except ValueError:
                return _error("bad_response", "RapidAPI returned a response that is not valid JSON.")

        return _error("rate_limit", "RapidAPI rate limit hit. Please wait a moment and try again.")
