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
    tecdoc_max_alternatives = fields.Integer(
        string='Alternatives Kept per Search',
        config_parameter='tecdoc.max_alternatives',
        default=20,
        help="An OEM search can return hundreds of aftermarket articles; only this many are kept (articles with images first)."
    )
    tecdoc_fitment_makes = fields.Char(
        string='Vehicle Makes to Keep',
        config_parameter='tecdoc.fitment_makes',
        help="Comma-separated makes (e.g. TOYOTA, HYUNDAI, KIA). Compatible vehicles of other makes are not stored. Empty = keep all."
    )
    tecdoc_lang_id = fields.Char(
        string='Catalog Language ID',
        config_parameter='tecdoc.lang_id',
        default='4',
        help="TecDoc language id (4 = English)."
    )
    tecdoc_country_filter_id = fields.Char(
        string='Country Filter ID',
        config_parameter='tecdoc.country_filter_id',
        default='63',
        help="TecDoc country filter for the make/model/engine lists. Tests showed it does not change part fitment results."
    )
    tecdoc_calls_this_month = fields.Char(string='Calls This Month', compute='_compute_tecdoc_usage')

    @api.depends('tecdoc_monthly_call_budget')
    def _compute_tecdoc_usage(self):
        used, budget = self.env['tecdoc.api.abstract'].get_monthly_usage()
        for rec in self:
            rec.tecdoc_calls_this_month = f"{used} / {budget}" if budget else f"{used} (no cap)"
