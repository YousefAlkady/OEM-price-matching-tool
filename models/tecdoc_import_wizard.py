from odoo import models, fields, api
import base64
import csv
import io
import logging

_logger = logging.getLogger(__name__)

class TecdocImportWizard(models.TransientModel):
    _name = 'tecdoc.import.wizard'
    _description = 'Import OEMs from CSV to TecDoc Parts'

    file = fields.Binary(string='File', required=True)
    filename = fields.Char(string='Filename')

    def action_import(self):
        if not self.file:
            return

        try:
            file_content = base64.b64decode(self.file).decode('utf-8')
            csv_data = csv.reader(io.StringIO(file_content))
        except Exception:
            return

        oem_numbers = []
        for row in csv_data:
            if row and row[0]:
                oem = str(row[0]).strip()
                if oem and oem.lower() not in ('oem', 'part number', 'part_number', 'article'):
                    oem_numbers.append(oem)

        if not oem_numbers:
            return

        PartModel = self.env['tecdoc.part']

        count = 0
        for oem in oem_numbers[:100]:
            exists = PartModel.search(['|', ('oem_number', '=', oem), ('part_number', '=', oem)], limit=1)
            if not exists:
                PartModel.create({
                    'name': f'Pending Fetch - {oem}',
                    'part_number': oem,
                    'oem_number': oem,
                    'brand': 'Unknown'
                })
                count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Import Completed',
                'message': f'Successfully created {count} pending parts. Select them in the list and click Action -> Deep Search Missing Info (Bulk) to fetch their data.',
                'type': 'success',
                'sticky': True,
            }
        }
