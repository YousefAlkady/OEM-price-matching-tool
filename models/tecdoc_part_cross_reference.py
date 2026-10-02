from odoo import models, fields, api

class TecdocPartCrossReference(models.Model):
    _name = 'tecdoc.part.cross_reference'
    _description = 'TecDoc Part Cross Reference'

    name = fields.Char(string='Name', compute='_compute_name', store=True)
    part_id = fields.Many2one('tecdoc.part', string='Original Part', required=True, ondelete='cascade')
    oem_number = fields.Char(string='OEM Number', required=True)
    brand = fields.Char(string='Alternative Brand')

    @api.depends('brand', 'oem_number')
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.brand or 'Unknown Brand'} - {rec.oem_number or ''}"
