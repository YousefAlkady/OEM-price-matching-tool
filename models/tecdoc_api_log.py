from datetime import timedelta

from odoo import api, fields, models, tools

# cache-hit rows only feed the cache-hit-rate figure; billed rows are kept for cost history
CACHED_LOG_RETENTION_DAYS = 90


class TecdocApiLog(models.Model):
    _name = 'tecdoc.api.log'
    _description = 'TecDoc API Request Log'
    _order = 'create_date desc'

    endpoint = fields.Char(string='Endpoint', required=True)
    method = fields.Char(string='Method')
    payload = fields.Text(string='Payload / Parameters')
    params_hash = fields.Char(string='Cache Key', index=True)
    response_code = fields.Integer(string='Response Code')
    error_message = fields.Text(string='Error Message')
    status = fields.Selection([
        ('success', 'Success'),
        ('cached', 'Served from cache'),
        ('error', 'Error'),
    ], string='Status', default='error')
    billed = fields.Boolean(string='Billed Call', index=True, help='The request reached RapidAPI and counts against the monthly quota.')
    duration_ms = fields.Integer(string='Duration (ms)')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, index=True)

    def init(self):
        # budget, usage and per-user limits all count by (company/user, billed, create_date)
        tools.create_index(self.env.cr, 'tecdoc_api_log_usage_idx', self._table, ['company_id', 'billed', 'create_date'])
        tools.create_index(self.env.cr, 'tecdoc_api_log_user_idx', self._table, ['create_uid', 'billed', 'create_date'])

    @api.autovacuum
    def _gc_cached_rows(self):
        cutoff = fields.Datetime.now() - timedelta(days=CACHED_LOG_RETENTION_DAYS)
        self.search([('status', '=', 'cached'), ('create_date', '<', cutoff)]).unlink()
