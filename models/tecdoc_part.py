import logging
import json
import base64
import requests
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class TecdocPart(models.Model):
    _name = 'tecdoc.part'
    _description = 'TecDoc Auto Part'

    name = fields.Char(string='Name/Description', required=True)
    part_number = fields.Char(string='Part Number', index=True, required=True)
    oem_number = fields.Text(string='OEM Number')
    brand = fields.Char(string='Brand')
    vehicle_model = fields.Char(string='Vehicle Model')
    vin = fields.Char(string='VIN', index=True)
    description = fields.Text(string='Description')
    category = fields.Char(string='Category')
    weight = fields.Float(string='Weight (kg)')
    volume = fields.Float(string='Volume (m3)')
    hs_code = fields.Char(string='HS Code')
    barcode = fields.Char(string='Barcode (EAN)')
    specs_text = fields.Text(string='Specifications')
    accessories_raw = fields.Text(string='Accessories Raw JSON')
    article_id = fields.Char(string='TecDoc Article ID', index=True)
    active = fields.Boolean(default=True)
    raw_data = fields.Text(string='Raw API Data')  # cached json to avoid re-fetching

    # relationships
    image_ids = fields.One2many('tecdoc.part.image', 'part_id', string='Images')
    vehicle_ids = fields.Many2many('tecdoc.vehicle', string='Compatible Vehicles')
    cross_reference_ids = fields.One2many('tecdoc.part.cross_reference', 'part_id', string='Alternative OEMs')
    product_tmpl_id = fields.Many2one('product.template', string='Odoo Product', help='Linked Odoo E-commerce Product')

    def unlink(self):
        for record in self:
            if record.product_tmpl_id:
                record.product_tmpl_id.tecdoc_part_id = False
        return super(TecdocPart, self).unlink()

    def action_view_odoo_product(self):
        self.ensure_one()
        if self.product_tmpl_id:
            return {
                'name': 'Odoo Product',
                'type': 'ir.actions.act_window',
                'res_model': 'product.template',
                'view_mode': 'form',
                'res_id': self.product_tmpl_id.id,
            }

    def action_create_odoo_product(self):
        for record in self:
            desc = record.category or ""
            brand_part = record.brand or ""
            name_part = record.name or ""
            if brand_part and brand_part.lower() not in ("unknown brand", "unknown"):
                product_name = f"{brand_part} - {name_part}"
            else:
                product_name = name_part or brand_part or record.part_number

            product_vals = {
                'name': product_name,
                'default_code': record.part_number,
                'detailed_type': 'product',
                'description': desc,
                'tecdoc_brand': record.brand,
                'tecdoc_article_number': record.part_number,
                'tecdoc_oem_number': record.oem_number,
                'tecdoc_part_id': record.id,
                'weight': record.weight,
                'volume': record.volume,
                'hs_code': record.hs_code,
                'barcode': record.barcode,
                'description_sale': record.specs_text,
                'description_purchase': f"TecDoc Brand: {record.brand}\nPart Number: {record.part_number}\nOEMs: {record.oem_number or 'N/A'}",
            }

            if record.product_tmpl_id:
                record.product_tmpl_id.write(product_vals)
                product_tmpl = record.product_tmpl_id
            else:
                product_tmpl = self.env['product.template'].create(product_vals)
                record.product_tmpl_id = product_tmpl.id

            if record.image_ids and record.image_ids[0].image:
                product_tmpl.image_1920 = record.image_ids[0].image
                extra_images = []
                for idx, img in enumerate(record.image_ids[1:]):
                    extra_images.append((0, 0, {
                        'name': img.name or f"{product_tmpl.name} - Image {idx + 2}",
                        'image_1920': img.image,
                    }))
                product_tmpl.product_template_image_ids = [(5, 0, 0)] + extra_images

            if record.category:
                categ = self.env['product.public.category'].search([('name', '=', record.category)], limit=1)
                if not categ:
                    categ = self.env['product.public.category'].create({'name': record.category})
                product_tmpl.public_categ_ids = [(4, categ.id)]

            if record.brand:
                vendor = self.env['res.partner'].search([('name', '=', record.brand), ('supplier_rank', '>', 0)], limit=1)
                if not vendor:
                    vendor = self.env['res.partner'].search([('name', '=', record.brand)], limit=1)
                if not vendor:
                    vendor = self.env['res.partner'].create({'name': record.brand, 'supplier_rank': 1})

                existing_seller = self.env['product.supplierinfo'].search([
                    ('product_tmpl_id', '=', product_tmpl.id),
                    ('partner_id', '=', vendor.id)
                ], limit=1)
                if not existing_seller:
                    self.env['product.supplierinfo'].create({
                        'product_tmpl_id': product_tmpl.id,
                        'partner_id': vendor.id,
                    })

            if record.accessories_raw:
                try:
                    acc_list = json.loads(record.accessories_raw)
                    acc_product_ids = []
                    for acc in acc_list:
                        acc_oem = acc.get('articleNo')
                        acc_brand = acc.get('supplierName', '')
                        if not acc_oem:
                            continue
                        existing_acc = self.env['product.template'].search([
                            '|', ('default_code', '=', acc_oem),
                                 ('tecdoc_article_number', '=', acc_oem)
                        ], limit=1)
                        if existing_acc:
                            acc_product_ids.append(existing_acc.id)
                        else:
                            new_acc = self.env['product.template'].create({
                                'name': f"{acc_brand} - {acc.get('articleProductName', 'Accessory')}",
                                'default_code': acc_oem,
                                'tecdoc_brand': acc_brand,
                                'tecdoc_article_number': acc_oem,
                                'detailed_type': 'product',
                            })
                            acc_product_ids.append(new_acc.id)
                    if acc_product_ids:
                        product_tmpl.accessory_product_ids = [(6, 0, acc_product_ids)]
                except Exception:
                    pass

            if record.cross_reference_ids:
                alt_product_ids = []
                for cross in record.cross_reference_ids:
                    if not cross.oem_number:
                        continue
                    existing_alt = self.env['product.template'].search([
                        '|', ('default_code', '=', cross.oem_number),
                             ('tecdoc_article_number', '=', cross.oem_number)
                    ], limit=1)
                    if existing_alt:
                        alt_product_ids.append(existing_alt.id)
                    else:
                        new_alt = self.env['product.template'].create({
                            'name': f"[{cross.oem_number}] - {cross.brand or 'Unknown Brand'}",
                            'default_code': cross.oem_number,
                            'tecdoc_brand': cross.brand or '',
                            'tecdoc_article_number': cross.oem_number,
                            'detailed_type': 'product',
                        })
                        alt_product_ids.append(new_alt.id)
                if alt_product_ids:
                    product_tmpl.alternative_product_ids = [(6, 0, alt_product_ids)]
                    product_tmpl.optional_product_ids = [(6, 0, alt_product_ids)]


    def action_fetch_cross_references(self):
        CrossRef = self.env['tecdoc.part.cross_reference']
        api_abstract = self.env['tecdoc.api.abstract']

        for record in self:
            if not record.article_id:
                continue

            data = api_abstract._make_rapidapi_request(f"/artlookup/select-article-cross-references/article-id/{record.article_id}/lang-id/4")
            if isinstance(data, dict) and 'error' in data:
                return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': 'API Error', 'message': data['message'], 'type': 'danger'}}

            if data and isinstance(data, dict) and 'articles' in data:
                for cross in data['articles']:
                    oem_num = cross.get('articleNo', '')
                    alt_brand = cross.get('supplierName', '')
                    if oem_num and alt_brand:
                        existing = CrossRef.search([('part_id', '=', record.id), ('oem_number', '=', oem_num)], limit=1)
                        if not existing:
                            CrossRef.create({
                                'part_id': record.id,
                                'oem_number': oem_num,
                                'brand': alt_brand
                            })
                        elif not existing.brand or existing.brand == 'Unknown Brand':
                            existing.brand = alt_brand

        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_fetch_linked_vehicles(self):
        Vehicle = self.env['tecdoc.vehicle'].sudo()
        api_abstract = self.env['tecdoc.api.abstract']

        for record in self:
            search_no = record.oem_number if record.oem_number else record.part_number
            if not search_no:
                continue

            data = api_abstract._make_rapidapi_request("/articles/get-compatible-cars-by-oem-no/type-id/1", params={
                "langId": "4", "countryFilterId": "63", "articleOemNo": search_no
            })

            if isinstance(data, dict) and 'error' in data:
                return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': 'API Error', 'message': data['message'], 'type': 'danger'}}

            articles = data.get('articles') or []
            vehicles = []
            for art in articles:
                vehicles.extend(art.get('compatibleCars') or [])

            seen = set()
            unique_vehicles = []
            for v in vehicles:
                vid = str(v.get('vehicleId', ''))
                if vid and vid != 'None' and vid not in seen:
                    seen.add(vid)
                    unique_vehicles.append(v)

            vehicle_ids = []
            for v in unique_vehicles:
                v_id_str = str(v.get('vehicleId', ''))
                if not v_id_str or v_id_str == 'None':
                    continue

                existing_vehicle = Vehicle.search([('vehicle_id', '=', v_id_str)], limit=1)
                if not existing_vehicle:
                    make_from = str(v.get('yearOfConstrFrom', ''))
                    make_to = str(v.get('yearOfConstrTo', ''))
                    make_date_str = f"{make_from}–{make_to}" if make_from and make_to else make_from or make_to
                    existing_vehicle = Vehicle.create({
                        'vehicle_id': v_id_str,
                        'brand': v.get('manufacturerName', ''),
                        'vehicle_model': v.get('modelName', ''),
                        'type': v.get('typeEngineName', ''),
                        'make_date': make_date_str,
                    })
                vehicle_ids.append(existing_vehicle.id)

            if vehicle_ids:
                record.write({'vehicle_ids': [(6, 0, vehicle_ids)]})

        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_refetch_all_data(self):
        for record in self:
            record._reparse_raw_data()
            record.action_fetch_cross_references()
            record.action_fetch_linked_vehicles()
            record.action_fallback_search_missing_info()
            record.action_create_odoo_product()

    def action_fallback_search_missing_info(self):
        api_abstract = self.env['tecdoc.api.abstract']

        for record in self:
            needs_vehicles = not record.vehicle_ids
            needs_cross_refs = not record.cross_reference_ids
            needs_images = True

            if not (needs_vehicles or needs_cross_refs or needs_images):
                continue

            search_candidates = []
            if record.part_number:
                search_candidates.append(record.part_number)
            if record.cross_reference_ids:
                for cross in record.cross_reference_ids:
                    if cross.oem_number:
                        search_candidates.append(cross.oem_number)

            if not search_candidates:
                continue

            found_data = False
            for candidate in search_candidates:
                if found_data:
                    break

                data = api_abstract._make_rapidapi_request("/artlookup/search-articles-by-article-no", params={
                    "langId": "4", "articleNo": candidate, "articleType": "ArticleNumber"
                })

                if isinstance(data, dict) and 'error' in data:
                    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': 'API Error', 'message': data['message'], 'type': 'danger'}}

                articles = data.get('articles') or []
                for art in articles:
                    art_id = str(art.get('articleId', ''))
                    if art_id:
                        update_vals = {}
                        if not record.article_id:
                            update_vals['article_id'] = art_id
                        if not record.brand or record.brand == 'Unknown':
                            update_vals['brand'] = art.get('brandName') or art.get('supplierName') or 'Unknown'
                        if not record.name or 'Pending Fetch' in record.name:
                            update_vals['name'] = art.get('genericArticleDescription') or art.get('articleProductName') or record.name
                        if not record.oem_number:
                            update_vals['oem_number'] = candidate
                        if update_vals:
                            record.write(update_vals)

                        oem_candidates = [candidate]
                        if record.oem_number and record.oem_number != candidate:
                            oem_candidates.append(record.oem_number)

                        if needs_cross_refs:
                            cr_data = api_abstract._make_rapidapi_request(f"/artlookup/select-article-cross-references/article-id/{art_id}/lang-id/4")
                            if cr_data and 'articles' in cr_data:
                                CrossRef = self.env['tecdoc.part.cross_reference']
                                for cross in cr_data['articles']:
                                    oem_num = cross.get('articleNo', '')
                                    alt_brand = cross.get('supplierName', '')
                                    if oem_num and alt_brand:
                                        oem_candidates.append(oem_num)
                                        exists = CrossRef.search([('part_id', '=', record.id), ('oem_number', '=', oem_num)], limit=1)
                                        if not exists:
                                            CrossRef.create({
                                                'part_id': record.id,
                                                'oem_number': oem_num,
                                                'brand': alt_brand
                                            })
                                            needs_cross_refs = False

                        if needs_vehicles:
                            for oem_candidate in set(oem_candidates):
                                if not needs_vehicles:
                                    break
                                v_data = api_abstract._make_rapidapi_request("/articles/get-compatible-cars-by-oem-no/type-id/1", params={
                                    "langId": "4", "countryFilterId": "63", "articleOemNo": oem_candidate
                                })
                                if v_data and 'articles' in v_data:
                                    v_articles = v_data.get('articles') or []
                                    v_list = []
                                    for v_art in v_articles:
                                        v_list.extend(v_art.get('compatibleCars') or [])

                                    if not v_list:
                                        continue

                                    Vehicle = self.env['tecdoc.vehicle'].sudo()
                                    new_v_ids = []
                                    for v in v_list:
                                        v_id_str = str(v.get('vehicleId', ''))
                                        if not v_id_str or v_id_str == 'None':
                                            continue
                                        existing_vehicle = Vehicle.search([('vehicle_id', '=', v_id_str)], limit=1)
                                        if not existing_vehicle:
                                            make_from = str(v.get('yearOfConstrFrom', ''))
                                            make_to = str(v.get('yearOfConstrTo', ''))
                                            existing_vehicle = Vehicle.create({
                                                'vehicle_id': v_id_str,
                                                'brand': v.get('manufacturerName', ''),
                                                'vehicle_model': v.get('modelName', ''),
                                                'type': v.get('typeEngineName', ''),
                                                'make_date': f"{make_from}–{make_to}" if make_from and make_to else make_from or make_to,
                                            })
                                        new_v_ids.append(existing_vehicle.id)
                                    if new_v_ids:
                                        record.write({'vehicle_ids': [(4, vid) for vid in new_v_ids]})
                                        needs_vehicles = False

                        if needs_images:
                            media_data = api_abstract._make_rapidapi_request("/articles/article-all-media-info", params={
                                "articleId": art_id, "langId": "4"
                            })
                            if isinstance(media_data, list):
                                for media in media_data:
                                    if media.get('articleMediaType') != 'PDF' and media.get('s3image'):
                                        try:
                                            img_dl = requests.get(media['s3image'], timeout=5)
                                            if img_dl.status_code == 200:
                                                exists = self.env['tecdoc.part.image'].search([
                                                    ('part_id', '=', record.id),
                                                    ('image_url', '=', media['s3image'])
                                                ], limit=1)
                                                if not exists:
                                                    self.env['tecdoc.part.image'].create({
                                                        'name': media.get('articleMediaFileName', 'image'),
                                                        'part_id': record.id,
                                                        'image_url': media['s3image'],
                                                        'image': base64.b64encode(img_dl.content)
                                                    })
                                        except Exception:
                                            pass

                        found_data = True
                        break

            record.action_create_odoo_product()

    def _reparse_raw_data(self):
        for record in self:
            if record.raw_data:
                try:
                    article = json.loads(record.raw_data)
                    oem_set = set()
                    if record.oem_number:
                        oem_set.update([x.strip() for x in record.oem_number.split(',') if x.strip()])

                    native = (article.get('oemNumbers') or article.get('oeNumbers') or article.get('crossReferences') or [])
                    if isinstance(native, list):
                        for ref in native:
                            if isinstance(ref, dict):
                                oem = ref.get('oemNumber') or ref.get('articleNo') or ref.get('number')
                                if oem:
                                    oem_set.add(str(oem).strip())

                    for ref in article.get('enriched_cross_refs', []):
                        oem = ref.get('oemNumber')
                        if oem:
                            oem_set.add(str(oem).strip())

                    if oem_set:
                        record.oem_number = ", ".join(sorted(filter(None, oem_set)))
                except Exception:
                    pass

    @api.model
    def api_save_parts_from_data(self, articles_data, vehicle_data=None, oem_number=None, compatible_vehicles=None):
        if not isinstance(articles_data, list):
            return

        api_abstract = self.env['tecdoc.api.abstract']
        PartImage = self.env['tecdoc.part.image'].sudo()
        Vehicle = self.env['tecdoc.vehicle'].sudo()
        CrossRef = self.env['tecdoc.part.cross_reference'].sudo()

        vehicle_record = self._get_or_create_vehicle(Vehicle, vehicle_data)
        compatible_vehicle_ids = self._resolve_compatible_vehicles(Vehicle, compatible_vehicles)

        article_ids = [str(a.get('articleId')) for a in articles_data if isinstance(a, dict) and a.get('articleId')]
        specs_map = {}
        if article_ids:
            spec_data = api_abstract._make_rapidapi_request("/articles/get-article-specifications-list-of-articles-ids", method="POST", payload={"langId": 4, "articleIds": [int(aid) for aid in article_ids]})
            if isinstance(spec_data, dict) and 'articles' in spec_data:
                for art_spec in spec_data.get('articles', []):
                    aid = str(art_spec.get('articleId'))
                    specs_map[aid] = art_spec.get('allSpecifications', [])

        for idx, article in enumerate(articles_data):
            if not isinstance(article, dict):
                continue

            article_id = str(article.get('articleId', ''))
            part_number = article.get('articleNo') or article.get('articleSearchNo', '')
            if not part_number:
                continue

            try:
                with self.env.cr.savepoint():
                    consolidated_oems = self._consolidate_oems(article, oem_number)

                    domain = [('article_id', '=', article_id)] if article_id else [('part_number', '=', part_number)]
                    existing_part = self.search(domain, limit=1)

                    vals = {
                        'name': article.get('articleProductName', 'Unknown Part'),
                        'part_number': part_number,
                        'brand': article.get('supplierName', article.get('brandName', '')),
                        'article_id': article_id,
                        'category': article.get('articleProductName', ''),
                        'raw_data': json.dumps(article),
                    }

                    specs = specs_map.get(article_id) or []
                    specs_lines = []
                    for spec in specs:
                        name_raw = str(spec.get('criteriaName', ''))
                        val_raw = str(spec.get('criteriaValue', ''))
                        name = name_raw.lower()
                        val_str = val_raw.replace(',', '.')

                        if name_raw and val_raw:
                            specs_lines.append(f"• {name_raw}: {val_raw}")

                        try:
                            if 'weight' in name:
                                vals['weight'] = float(val_str)
                            elif 'volume' in name:
                                vals['volume'] = float(val_str)
                            elif 'customs tariff number' in name or 'hs code' in name:
                                vals['hs_code'] = val_str
                            elif 'ean' in name or 'barcode' in name:
                                vals['barcode'] = val_raw
                        except ValueError:
                            pass

                    if specs_lines:
                        vals['specs_text'] = "Specifications:\n" + "\n".join(specs_lines)

                    if not vals.get('barcode'):
                        vals['barcode'] = article.get('eanNumber', '')

                    if idx < 2:
                        acc_data = api_abstract._make_rapidapi_request(f"/articles/selecting-list-of-accessories-list-for-the-article/article-id/{article_id}/lang-id/4/country-filter-id/63")
                        if isinstance(acc_data, dict) and acc_data.get('articles'):
                            vals['accessories_raw'] = json.dumps(acc_data['articles'])

                    if consolidated_oems:
                        vals['oem_number'] = consolidated_oems
                    if vehicle_data and isinstance(vehicle_data, dict):
                        v_model = vehicle_data.get('carName', vehicle_data.get('modelName', ''))
                        v_vin = vehicle_data.get('vin', vehicle_data.get('kba', ''))
                        if v_model:
                            vals['vehicle_model'] = v_model
                        if v_vin:
                            vals['vin'] = v_vin

                    if existing_part:
                        existing_part.write(vals)
                        part_record = existing_part
                    else:
                        part_record = self.create(vals)

                    if vehicle_record:
                        part_record.vehicle_ids = [(4, vehicle_record.id)]
                    if compatible_vehicle_ids:
                        part_record.vehicle_ids = [(4, vid) for vid in compatible_vehicle_ids]

                    self._save_cross_references(CrossRef, part_record, article.get('enriched_cross_refs', []))

                    if idx < 2:
                        self._save_part_image(PartImage, part_record, article)

                    try:
                        part_record.action_create_odoo_product()
                    except Exception as exc:
                        _logger.error(f"Odoo product sync failed for {part_number}: {exc}")

            except Exception as exc:
                _logger.error(f"Skipping article {part_number} due to DB error: {exc}")
                continue

    def _get_or_create_vehicle(self, Vehicle, vehicle_data):
        if not vehicle_data or not isinstance(vehicle_data, dict):
            return None

        vin = vehicle_data.get('vin', '') or vehicle_data.get('kba', '')
        brand = vehicle_data.get('makeName', '')
        model = vehicle_data.get('modelName', '')
        make_date = str(vehicle_data.get('yearOfConstrFrom', ''))
        vtype = vehicle_data.get('typeName', '')
        vehicle_id_s = str(vehicle_data.get('vehicleId', ''))
        car_name = vehicle_data.get('carName', '')

        if car_name and not brand:
            parts = car_name.split(' ', 1)
            brand = parts[0]
            model = model or (parts[1] if len(parts) > 1 else '')

        if not (vin or brand or (vehicle_id_s and vehicle_id_s != 'None')):
            return None

        if vehicle_id_s and vehicle_id_s != 'None':
            domain = [('vehicle_id', '=', vehicle_id_s)]
        elif vin:
            domain = [('vin', '=', vin)]
        else:
            domain = [('brand', '=', brand), ('vehicle_model', '=', model)]

        record = Vehicle.search(domain, limit=1)
        if not record:
            create_vals = {
                'brand': brand,
                'vehicle_model': model,
                'make_date': make_date,
                'type': vtype,
            }
            if vin:
                create_vals['vin'] = vin
            if vehicle_id_s and vehicle_id_s != 'None':
                create_vals['vehicle_id'] = vehicle_id_s
            record = Vehicle.create(create_vals)
        return record

    def _resolve_compatible_vehicles(self, Vehicle, compatible_vehicles):
        if not compatible_vehicles:
            return []

        ids = []
        for v in compatible_vehicles:
            v_id_str = str(v.get('vehicleId', ''))
            if not v_id_str or v_id_str == 'None':
                continue

            existing = Vehicle.search([('vehicle_id', '=', v_id_str)], limit=1)
            if not existing:
                make_from = str(v.get('yearOfConstrFrom', ''))
                make_to = str(v.get('yearOfConstrTo', ''))
                make_date_s = f"{make_from}\u2013{make_to}" if make_from and make_to else make_from or make_to
                existing = Vehicle.create({
                    'vehicle_id': v_id_str,
                    'brand': v.get('manufacturerName', ''),
                    'vehicle_model': v.get('modelName', ''),
                    'type': v.get('typeEngineName', ''),
                    'make_date': make_date_s,
                })
            ids.append(existing.id)

        return ids

    @staticmethod
    def _consolidate_oems(article, oem_number):
        oem_set = set()
        if oem_number:
            oem_set.add(oem_number)

        native = (article.get('oemNumbers') or article.get('oeNumbers') or article.get('crossReferences') or [])
        if isinstance(native, list):
            for ref in native:
                if isinstance(ref, dict):
                    oem = ref.get('oemNumber') or ref.get('articleNo') or ref.get('number')
                    if oem:
                        oem_set.add(str(oem).strip())

        for ref in article.get('enriched_cross_refs', []):
            oem = ref.get('oemNumber')
            if oem:
                oem_set.add(str(oem).strip())

        consolidated = ", ".join(sorted(filter(None, oem_set)))
        return consolidated[:2000] if len(consolidated) > 2000 else consolidated

    @staticmethod
    def _save_cross_references(CrossRef, part_record, enriched_refs):
        for ref in enriched_refs:
            oem = ref.get('oemNumber') or ref.get('articleNo') or ref.get('number')
            brand = ref.get('brandName') or ref.get('manufacturerName') or ref.get('mfrName') or ref.get('supplierName') or ref.get('brand') or ''
            if not oem:
                continue
            exists = CrossRef.search([('part_id', '=', part_record.id), ('oem_number', '=', str(oem))], limit=1)
            if not exists:
                CrossRef.create({
                    'part_id': part_record.id,
                    'oem_number': str(oem),
                    'brand': brand or '',
                })

    @staticmethod
    def _save_part_image(PartImage, part_record, article):
        images_to_save = []
        images = article.get('images') or article.get('articleImages') or []
        for img in images:
            if isinstance(img, dict):
                url = img.get('imageURL800') or img.get('imageURL400') or img.get('imageURL') or img.get('url')
                if url:
                    images_to_save.append((url, "image"))
            elif isinstance(img, str) and img:
                images_to_save.append((img, "image"))

        if not images_to_save and article.get('s3image'):
            images_to_save.append((article['s3image'], article.get('articleMediaFileName', 'image')))

        for image_url, image_name in images_to_save:
            exists = PartImage.search([('part_id', '=', part_record.id), ('image_url', '=', image_url)], limit=1)
            if exists:
                continue

            try:
                img_response = requests.get(image_url, timeout=5)
                if img_response.status_code == 200:
                    img_data = base64.b64encode(img_response.content)
                    PartImage.create({
                        'name': image_name,
                        'part_id': part_record.id,
                        'image_url': image_url,
                        'image': img_data,
                    })
            except Exception:
                pass
