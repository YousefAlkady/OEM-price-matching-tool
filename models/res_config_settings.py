from odoo import api, fields, models


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
    tecdoc_monthly_call_budget = fields.Integer(
        string='Monthly Call Budget',
        config_parameter='tecdoc.monthly_call_budget',
        help="Stop calling the API after this many billed calls per month (0 = no cap). Set it at or below your RapidAPI plan limit."
    )
    tecdoc_user_calls_per_minute = fields.Integer(
        string='Calls per User per Minute',
        config_parameter='tecdoc.user_calls_per_minute',
        default=30,
        help="Per-user limit on billed API calls in any 60 seconds (0 = no limit)."
    )
    tecdoc_cache_ttl_days = fields.Integer(
        string='Cache Lifetime (days)',
        config_parameter='tecdoc.cache_ttl_days',
        default=30,
        help="How long an API response is reused before it is fetched again."
    )
    tecdoc_calls_this_month = fields.Char(string='Calls This Month', compute='_compute_tecdoc_usage')

    @api.depends('tecdoc_monthly_call_budget')
    def _compute_tecdoc_usage(self):
        used, budget = self.env['tecdoc.api.abstract'].get_monthly_usage()
        for rec in self:
            rec.tecdoc_calls_this_month = f"{used} / {budget}" if budget else f"{used} (no cap)"
