import logging
import requests
import time
from odoo import models, api

_logger = logging.getLogger(__name__)

class TecdocApiAbstract(models.AbstractModel):
    _name = 'tecdoc.api.abstract'
    _description = 'RapidAPI Integration Abstract Model'

    @api.model
    def _make_rapidapi_request(self, endpoint, method="GET", payload=None, params=None):
        rapidapi_key = self.env['ir.config_parameter'].sudo().get_param('tecdoc.rapidapi_key', '')
        rapidapi_host = self.env['ir.config_parameter'].sudo().get_param('tecdoc.rapidapi_host', 'auto-parts-catalog.p.rapidapi.com')
        base_url = f"https://{rapidapi_host}"

        if not rapidapi_key:
            _logger.error("RapidAPI Key is not configured in settings.")
            return {"error": "Missing API Key", "message": "RapidAPI Key is not configured in settings."}

        url = f"{base_url}{endpoint}"

        headers = {
            "x-rapidapi-key":  rapidapi_key,
            "x-rapidapi-host": rapidapi_host,
            "Content-Type":    "application/x-www-form-urlencoded" if method == "POST" else "application/json",
        }

        try:
            _logger.info(f"RapidAPI {method}: {url}")
            time.sleep(0.5)  # api rate limit protection

            if method == "POST":
                response = requests.post(url, data=payload, headers=headers, timeout=15)
            else:
                response = requests.get(url, params=params, headers=headers, timeout=15)

            if response.status_code == 429:
                _logger.warning(f"RapidAPI 429 Too Many Requests for {url}. Failing immediately.")
                return {"error": "rate_limit", "message": "You have exceeded your RapidAPI monthly quota. Please upgrade your plan."}

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as exc:
            _logger.error(f"RapidAPI HTTP Error: {exc}")
            if exc.response is not None and exc.response.status_code == 403:
                return {"error": "Your RapidAPI Key is valid, but it is not subscribed to the API! Please go to RapidAPI, search for 'Auto Parts Catalog', and click 'Subscribe to Test' (it is free) to activate your key."}
            elif exc.response is not None and exc.response.status_code == 401:
                return {"error": "Invalid API Key! Please double-check your RapidAPI Key in Settings."}
            elif exc.response is not None and exc.response.status_code == 429:
                return {"error": "You have exceeded your RapidAPI monthly quota. Please upgrade your plan."}
            else:
                return {"error": str(exc)}
        except requests.exceptions.RequestException as exc:
            _logger.error(f"RapidAPI request failed: {exc}")
            return {"error": "Network error connecting to RapidAPI. Please check your internet connection."}
