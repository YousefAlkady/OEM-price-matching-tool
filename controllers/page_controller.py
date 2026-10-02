from odoo import http
from odoo.http import request


class PageController(http.Controller):

    @http.route('/tecdoc', type='http', auth='user', csrf=False)
    def tecdoc_page(self, **kwargs):
        return request.render('rapidapi_bdeel.tecdoc_search_page', {})
