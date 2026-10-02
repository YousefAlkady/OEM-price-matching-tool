from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tecdoc_rapidapi_key = fields.Char(
        string='RapidAPI Key',
        config_parameter='tecdoc.rapidapi_key',
        help="Your RapidAPI Key for Auto Parts Catalog"
    )
    tecdoc_rapidapi_host = fields.Char(
        string='RapidAPI Host',
        config_parameter='tecdoc.rapidapi_host',
        default='auto-parts-catalog.p.rapidapi.com',
        help="The host for the RapidAPI Auto Parts Catalog"
    )
