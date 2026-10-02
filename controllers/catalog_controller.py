import logging

from odoo import http

from .rapidapi_client import RapidApiMixin

_logger = logging.getLogger(__name__)


class CatalogController(http.Controller):

    @http.route('/api/tecdoc/manufacturers', type='json', auth='user', methods=['POST'], csrf=False)
    def get_manufacturers(self):
        data = request.env['tecdoc.api.abstract']._make_rapidapi_request("/manufacturers/list/type-id/1", method="GET")

        if isinstance(data, dict) and "error" in data:
            return {"status": 500, "error": "API Request Failed", "message": data["error"]}

        return {
            "status": 200,
            "data":   data.get('data', data) if isinstance(data, dict) else data,
        }

    @http.route('/api/tecdoc/models', type='json', auth='user', methods=['POST'], csrf=False)
    def get_models(self, brand_id):
        endpoint = f"/models/list/type-id/1/manufacturer-id/{brand_id}/lang-id/4/country-filter-id/63"
        data = request.env['tecdoc.api.abstract']._make_rapidapi_request(endpoint, method="GET")

        if isinstance(data, dict) and "error" in data:
            return {"status": 500, "error": "API Request Failed", "message": data["error"]}

        return {
            "status": 200,
            "data":   data.get('data', data) if isinstance(data, dict) else data,
        }

    @http.route('/api/tecdoc/engines', type='json', auth='user', methods=['POST'], csrf=False)
    def get_engines(self, brand_id, model_id):
        endpoint = f"/types/type-id/1/list-vehicles-types/{model_id}/lang-id/4/country-filter-id/63"
        data = request.env['tecdoc.api.abstract']._make_rapidapi_request(endpoint, method="GET")

        if isinstance(data, dict) and "error" in data:
            return {"status": 500, "error": "API Request Failed", "message": data["error"]}

        return {
            "status": 200,
            "data":   data.get('data', data) if isinstance(data, dict) else data,
        }

    @http.route('/api/tecdoc/categories', type='json', auth='user', methods=['POST'], csrf=False)
    def get_categories(self, vehicle_id):
        endpoint = f"/category/type-id/1/products-groups-variant-1/{vehicle_id}/lang-id/4"
        data = request.env['tecdoc.api.abstract']._make_rapidapi_request(endpoint, method="GET")

        if isinstance(data, dict) and "error" in data:
            return {"status": 500, "error": "API Request Failed", "message": data["error"]}

        cats = data.get('categories', data.get('data', data)) if isinstance(data, dict) else data
        return {"status": 200, "data": cats}
