import logging
from odoo.http import request

_logger = logging.getLogger(__name__)

class DbServiceMixin:
    def _check_db_for_parts(self, search_type, query):
        if not query:
            return None

        Part = request.env['tecdoc.part'].sudo()
        domain = []

        if search_type == 'part_number':
            domain = [('part_number', '=', query)]
        elif search_type == 'oem_number':
            domain = [('oem_number', '=', query)]
        elif search_type == 'vin':
            domain = [('vin', '=', query)]

        if not domain:
            return None

        parts = Part.search(domain)
        if parts:
            result = []
            for part in parts:
                if part.raw_data:
                    try:
                        import json
                        result.append(json.loads(part.raw_data))
                    except Exception:
                        pass
            if result:
                return result
        return None

    def _fetch_compatible_vehicles(self, article_no):
        try:
            _logger.info(f"Fetching compatible vehicles for: {article_no}")
            data = request.env['tecdoc.api.abstract']._make_rapidapi_request(
                "/articles/get-compatible-cars-by-oem-no/type-id/1",
                method="GET",
                params={
                    "langId": "4",
                    "countryFilterId": "63",
                    "articleOemNo": article_no,
                },
            )

            if not isinstance(data, dict) or 'error' in data:
                return []

            vehicles = []
            for art in (data.get('articles') or []):
                vehicles.extend(art.get('compatibleCars') or [])

            seen, unique = set(), []
            for v in vehicles:
                vid = str(v.get('vehicleId', ''))
                if vid and vid != 'None' and vid not in seen:
                    seen.add(vid)
                    unique.append(v)

            return unique
        except Exception as exc:
            _logger.warning(f"_fetch_compatible_vehicles failed for {article_no}: {exc}")
            return []
