from odoo import http
from odoo.http import request


class SearchController(http.Controller):

    @http.route('/api/tecdoc/search', type='json', auth='user', methods=['POST'], csrf=False)
    def search_parts(self, search_type, query=None, **kwargs):
        # rate limits, budget and caching are enforced in tecdoc.api.abstract
        return request.env['tecdoc.part'].search_catalog(search_type, query, **kwargs)
