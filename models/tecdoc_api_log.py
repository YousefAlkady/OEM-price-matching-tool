from odoo import models, fields


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
