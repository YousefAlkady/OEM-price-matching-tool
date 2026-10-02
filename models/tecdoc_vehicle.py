from odoo import models, fields, api

class TecdocVehicle(models.Model):
    _name = 'tecdoc.vehicle'
    _description = 'TecDoc Vehicle'

    name = fields.Char(string='Vehicle Name', compute='_compute_name', store=True)
    vehicle_id = fields.Char(string='TecDoc Vehicle ID', index=True)
    vin = fields.Char(string='VIN Number', index=True)
    brand = fields.Char(string='Brand/Make')
    vehicle_model = fields.Char(string='Model')
    make_date = fields.Char(string='Make Date')
    type = fields.Char(string='Type/Engine')

    part_ids = fields.Many2many('tecdoc.part', relation='tecdoc_part_tecdoc_vehicle_rel', column1='tecdoc_vehicle_id', column2='tecdoc_part_id', string='Compatible Parts')
    parts_count = fields.Integer(string='Parts Count', compute='_compute_parts_count')

    def _compute_parts_count(self):
        for rec in self:
            rec.parts_count = self.env['tecdoc.part'].search_count([('vehicle_ids', '=', rec.id)])

    def action_view_parts(self):
        self.ensure_one()
        return {
            'name': 'Compatible Parts',
            'type': 'ir.actions.act_window',
            'res_model': 'tecdoc.part',
            'view_mode': 'tree,form',
            'domain': [('vehicle_ids', '=', self.id)],
            'context': {'default_vehicle_ids': [(4, self.id)]},
        }

    @api.depends('brand', 'vehicle_model', 'vin', 'name')
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.brand:
                parts.append(rec.brand)
            if rec.vehicle_model:
                parts.append(rec.vehicle_model)
            if rec.vin:
                parts.append(f"({rec.vin})")
            rec.name = ' '.join(parts) if parts else 'Unknown Vehicle'
