from odoo import models, fields

class TecdocApiLog(models.Model):
    _name = 'tecdoc.api.log'
    _description = 'TecDoc API Request Log'
    _order = 'create_date desc'

    endpoint = fields.Char(string='Endpoint', required=True)
    payload = fields.Text(string='Payload / Parameters')
    response_code = fields.Integer(string='Response Code')
    error_message = fields.Text(string='Error Message')
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
    ], string='Status', default='error')
