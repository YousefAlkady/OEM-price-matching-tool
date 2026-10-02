from odoo import models, fields

class TecdocPartImage(models.Model):
    _name = 'tecdoc.part.image'
    _description = 'TecDoc Part Image'

    name = fields.Char(string='Name')
    part_id = fields.Many2one('tecdoc.part', string='Part', ondelete='cascade', required=True)
    image_url = fields.Char(string='Image URL')
    image = fields.Binary(string='Image', attachment=True)
