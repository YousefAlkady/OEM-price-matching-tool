import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class CatalogController(http.Controller):

    def _locale(self):
        icp = request.env['ir.config_parameter'].sudo()
        return icp.get_param('tecdoc.lang_id', '4'), icp.get_param('tecdoc.country_filter_id', '63')

    def _catalog_get(self, endpoint):
        data = request.env['tecdoc.api.abstract']._make_rapidapi_request(endpoint, method="GET")
        if isinstance(data, dict) and "error" in data:
            return None, {"status": 500, "error": "API Request Failed", "message": data.get("message", data["error"])}
        return data, None

    @http.route('/api/tecdoc/manufacturers', type='json', auth='user', methods=['POST'], csrf=False)
    def get_manufacturers(self):
        data, err = self._catalog_get("/manufacturers/list/type-id/1")
        if err:
            return err
        return {"status": 200, "data": data.get('data', data) if isinstance(data, dict) else data}

    @http.route('/api/tecdoc/models', type='json', auth='user', methods=['POST'], csrf=False)
    def get_models(self, brand_id):
        lang_id, country_id = self._locale()
        data, err = self._catalog_get(f"/models/list/type-id/1/manufacturer-id/{brand_id}/lang-id/{lang_id}/country-filter-id/{country_id}")
        if err:
            return err
        return {"status": 200, "data": data.get('data', data) if isinstance(data, dict) else data}

    @http.route('/api/tecdoc/engines', type='json', auth='user', methods=['POST'], csrf=False)
    def get_engines(self, brand_id, model_id):
        lang_id, country_id = self._locale()
        data, err = self._catalog_get(f"/types/type-id/1/list-vehicles-types/{model_id}/lang-id/{lang_id}/country-filter-id/{country_id}")
        if err:
            return err
        return {"status": 200, "data": data.get('data', data) if isinstance(data, dict) else data}

    @http.route('/api/tecdoc/categories', type='json', auth='user', methods=['POST'], csrf=False)
    def get_categories(self, vehicle_id):
        lang_id, _country_id = self._locale()
        data, err = self._catalog_get(f"/category/type-id/1/products-groups-variant-1/{vehicle_id}/lang-id/{lang_id}")
        if err:
            return err
        cats = data.get('categories', data.get('data', data)) if isinstance(data, dict) else data
        return {"status": 200, "data": cats}
