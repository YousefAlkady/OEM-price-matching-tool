from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    tecdoc_part_id = fields.Many2one('tecdoc.part', string="Linked TecDoc Part")

    tecdoc_vehicle_ids = fields.Many2many(
        'tecdoc.vehicle',
        compute='_compute_tecdoc_vehicle_ids',
        string="Compatible Vehicles",
    )
    tecdoc_cross_reference_ids = fields.One2many(
        'tecdoc.part.cross_reference',
        compute='_compute_tecdoc_cross_reference_ids',
        string="Alternative OEMs",
    )

    tecdoc_oem_number = fields.Text(related='tecdoc_part_id.oem_number', string="OEM Numbers", readonly=True)
    tecdoc_brand = fields.Char(related='tecdoc_part_id.brand', string="TecDoc Brand", readonly=True)
    tecdoc_article_number = fields.Char(related='tecdoc_part_id.part_number', string="Article/Part Number", readonly=True)
    tecdoc_image_ids = fields.One2many(related='tecdoc_part_id.image_ids', string="TecDoc Images", readonly=True)
    tecdoc_raw_data = fields.Text(related='tecdoc_part_id.raw_data', string="TecDoc Raw Data", readonly=True)

    @api.depends('tecdoc_part_id', 'tecdoc_part_id.vehicle_ids')
    def _compute_tecdoc_vehicle_ids(self):
        for rec in self:
            rec.tecdoc_vehicle_ids = rec.tecdoc_part_id.vehicle_ids if rec.tecdoc_part_id else self.env['tecdoc.vehicle']

    @api.depends('tecdoc_part_id', 'tecdoc_part_id.cross_reference_ids')
    def _compute_tecdoc_cross_reference_ids(self):
        for rec in self:
            rec.tecdoc_cross_reference_ids = rec.tecdoc_part_id.cross_reference_ids if rec.tecdoc_part_id else self.env['tecdoc.part.cross_reference']

    def action_refetch_tecdoc_data(self):
        for record in self:
            if record.tecdoc_part_id:
                record.tecdoc_part_id._reparse_raw_data()
                record.tecdoc_part_id.action_fetch_cross_references()
                record.tecdoc_part_id.action_fetch_linked_vehicles()
                record.tecdoc_part_id.action_create_odoo_product()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_fallback_search_missing_info(self):
        for record in self:
            if not record.tecdoc_part_id:
                search_term = record.default_code or record.name
                if not search_term:
                    continue
                new_part = self.env['tecdoc.part'].create({
                    'part_number': search_term,
                    'name': 'Pending Fetch...',
                    'product_tmpl_id': record.id
                })
                record.tecdoc_part_id = new_part.id

            if not record.tecdoc_part_id.product_tmpl_id:
                record.tecdoc_part_id.product_tmpl_id = record.id

            record.tecdoc_part_id.action_fallback_search_missing_info()
            record.tecdoc_part_id.action_create_odoo_product()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_view_tecdoc_part(self):
        self.ensure_one()
        if self.tecdoc_part_id:
            return {
                'name': 'TecDoc Raw Data',
                'type': 'ir.actions.act_window',
                'res_model': 'tecdoc.part',
                'view_mode': 'form',
                'res_id': self.tecdoc_part_id.id,
            }
