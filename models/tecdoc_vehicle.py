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
            'view_mode': 'list,form',
            'domain': [('vehicle_ids', '=', self.id)],
            'context': {'default_vehicle_ids': [(4, self.id)]},
        }

    @staticmethod
    def _production_range(car):
        start = (car.get('constructionIntervalStart') or '')[:7]
        end = (car.get('constructionIntervalEnd') or '')[:7]
        if not start:
            return end
        return f"{start} – {end or 'present'}"

    @api.model
    def upsert_from_cars(self, cars):
        """Create missing vehicles from API 'compatibleCars' rows. Returns {vehicleId: record}."""
        by_id = {}
        for car in cars:
            vid = str(car.get('vehicleId', ''))
            if vid and vid != 'None':
                by_id.setdefault(vid, car)
        if not by_id:
            return {}
        result = {v.vehicle_id: v for v in self.search([('vehicle_id', 'in', list(by_id))])}
        to_create = []
        for vid, car in by_id.items():
            if vid in result:
                continue
            brand = car.get('manufacturerName', '')
            model = car.get('modelName', '')
            if not brand and car.get('carName'):
                brand, _sep, rest = car['carName'].partition(' ')
                model = model or rest
            to_create.append({
                'vehicle_id': vid,
                'brand': brand,
                'vehicle_model': model,
                'type': car.get('typeEngineName', ''),
                'make_date': self._production_range(car),
            })
        for vehicle in self.create(to_create):
            result[vehicle.vehicle_id] = vehicle
        return result

    @api.model
    def save_from_vin(self, vin, inner, decoder_data):
        if self.search_count([('vin', '=', vin)]):
            return
        matching = inner.get('matchingVehicles', {})
        mv_list = matching.get('array', []) if isinstance(matching, dict) else (matching if isinstance(matching, list) else [])
        if not mv_list and not decoder_data:
            return
        first = mv_list[0] if mv_list and isinstance(mv_list[0], dict) else {}

        # TecDoc names first: fitment data and the make filter use them (e.g. 'VW', not 'VOLKSWAGEN');
        # the second decoder is US-oriented and often rejects other VINs
        models_arr = (inner.get('matchingModels') or {}).get('array') if isinstance(inner.get('matchingModels'), dict) else None
        model = (models_arr[0].get('modelName', '') if isinstance(models_arr, list) and models_arr else '') \
            or decoder_data.get('model', '')
        brand = (first.get('carName', '').split() or [''])[0] or decoder_data.get('make', '')
        vehicle_id = first.get('vehicleId')

        self.create({
            'vin': vin,
            'vehicle_id': str(vehicle_id) if vehicle_id not in (None, '', 'None') else False,
            'brand': brand,
            'vehicle_model': model,
            'make_date': str(decoder_data.get('year', decoder_data.get('model_year', ''))),
            'type': decoder_data.get('trim', '') or first.get('carName', ''),
        })

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
