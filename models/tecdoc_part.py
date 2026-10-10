import base64
import json
import logging
import re

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.image import image_process

from .rapidapi_abstract import normalize_part_no

_logger = logging.getLogger(__name__)

SEARCH_ENDPOINT = "/artlookup/search-articles-by-article-no"
COMPAT_ENDPOINT = "/articles/get-compatible-cars-by-oem-no/type-id/1"
SPECS_ENDPOINT = "/articles/get-article-specifications-list-of-articles-ids"
ARTICLE_TYPES = {
    'part_number': 'ArticleNumber',
    'oem_number': 'OENumber',
    'engine_code': 'EngineCode',
    'text': 'ArticleNumber',
}
# an OEM search returns every aftermarket article that references the OEM (hundreds);
# only a bounded, ranked set is kept
DEFAULT_MAX_ALTERNATIVES = 20
DEFAULT_MAX_VEHICLES = 300
MAX_QUERY_LENGTH = 64
# values are pasted into API URL paths, so they must match these shapes exactly
VIN_RE = re.compile(r'^[A-HJ-NPR-Z0-9]{11,17}$')
ID_RE = re.compile(r'^[0-9]{1,12}$')


def _xref_endpoint(article_id, lang_id):
    return f"/artlookup/select-article-cross-references/article-id/{article_id}/lang-id/{lang_id}"


class TecdocPart(models.Model):
    _name = 'tecdoc.part'
    _description = 'TecDoc Auto Part'

    name = fields.Char(string='Name/Description', required=True)
    part_number = fields.Char(string='Part Number', index=True, required=True)
    part_number_key = fields.Char(string='Normalized Part Number', compute='_compute_part_number_key', store=True, index=True)
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
    raw_data = fields.Text(string='Raw API Data')

    # relationships
    image_ids = fields.One2many('tecdoc.part.image', 'part_id', string='Images')
    vehicle_ids = fields.Many2many('tecdoc.vehicle', string='Compatible Vehicles')
    cross_reference_ids = fields.One2many('tecdoc.part.cross_reference', 'part_id', string='Alternative OEMs')
    product_tmpl_id = fields.Many2one('product.template', string='Odoo Product', help='Linked Odoo E-commerce Product')

    _sql_constraints = [
        ('article_id_unique', 'unique(article_id)', 'This TecDoc article is already saved as a part.'),
    ]

    @api.depends('part_number')
    def _compute_part_number_key(self):
        for rec in self:
            rec.part_number_key = normalize_part_no(rec.part_number)

    def unlink(self):
        for record in self:
            if record.product_tmpl_id:
                record.product_tmpl_id.tecdoc_part_id = False
        return super().unlink()

    # ------------------------------------------------------------------
    # settings helpers
    # ------------------------------------------------------------------
    def _api(self):
        return self.env['tecdoc.api.abstract']

    def _lang_id(self):
        return self.env['ir.config_parameter'].sudo().get_param('tecdoc.lang_id', '4')

    def _fitment_makes(self):
        raw = self.env['ir.config_parameter'].sudo().get_param('tecdoc.fitment_makes', '') or ''
        return {m.strip().upper() for m in raw.split(',') if m.strip()}

    # ------------------------------------------------------------------
    # catalog search (used by the /api/tecdoc/search controller)
    # ------------------------------------------------------------------
    @api.model
    def search_catalog(self, search_type, query=None, **kwargs):
        api_model = self._api()
        if not self.env.su and not self.env.user.has_group('rapidapi_bdeel.group_tecdoc_operator'):
            return {"status": 403, "error": "Forbidden", "message": "You need the OEM Connect Operator role to search the catalog.", "data": []}
        invalid = self._validate_search(search_type, query, kwargs)
        if invalid:
            return {"status": 400, "error": "Bad Request", "message": invalid, "data": []}
        query = query.strip() if isinstance(query, str) else query
        billed_before = api_model.get_monthly_usage()[0]
        lang_id = self._lang_id()

        if search_type == 'vin':
            return self._vin_lookup(query.upper())

        if search_type in ARTICLE_TYPES:
            data = api_model._make_rapidapi_request(SEARCH_ENDPOINT, params={
                "langId": lang_id, "articleNo": query, "articleType": ARTICLE_TYPES[search_type]})
        elif search_type == 'alternatives':
            data = api_model._make_rapidapi_request(_xref_endpoint(query, lang_id))
        elif search_type == 'exact_vehicle':
            payload = {"typeId": "1", "langId": lang_id, "vehicleId": kwargs.get('vehicle_id')}
            if kwargs.get('category_id'):
                payload["categoryId"] = kwargs.get('category_id')
            data = api_model._make_rapidapi_request("/articles/list-articles", method="POST", payload=payload)
        else:
            return {"status": 400, "error": "Bad Request", "message": f"Invalid search_type: {search_type}", "data": []}

        if isinstance(data, dict) and "error" in data:
            return self._error_result(data)

        articles = self._bound_articles(self._extract_articles(data))

        fitment = {}
        if articles and search_type in ('oem_number', 'part_number', 'engine_code'):
            fitment = self._fetch_fitment(query)

        extra_vehicle = None
        if search_type == 'exact_vehicle' and kwargs.get('vehicle_id'):
            extra_vehicle = self.env['tecdoc.vehicle'].upsert_from_cars([{
                'vehicleId': kwargs.get('vehicle_id'),
                'carName': kwargs.get('vehicle_name') or '',
            }]).get(str(kwargs.get('vehicle_id')))

        parts = self._save_articles(articles, oem_number=query if search_type == 'oem_number' else None,
                                    fitment=fitment, extra_vehicle=extra_vehicle)

        if search_type == 'part_number' and parts:
            # one extra call: alternatives of the best match
            parts[:1].action_fetch_cross_references(notify=False)

        vehicles = []
        seen = set()
        for cars in fitment.values():
            for car in cars:
                vid = str(car.get('vehicleId'))
                if vid not in seen:
                    seen.add(vid)
                    vehicles.append(car)

        return {
            "status": 200,
            "data": articles,
            "compatible_vehicles": vehicles[:DEFAULT_MAX_VEHICLES],
            "cached": api_model.get_monthly_usage()[0] == billed_before,
        }

    @staticmethod
    def _validate_search(search_type, query, kwargs):
        """Return an error message if the search input is not acceptable, else None."""
        if search_type == 'exact_vehicle':
            if not ID_RE.match(str(kwargs.get('vehicle_id') or '')):
                return "A numeric vehicle id is required"
            if kwargs.get('category_id') and not ID_RE.match(str(kwargs['category_id'])):
                return "The category id must be numeric"
            return None
        if not isinstance(query, str) or not query.strip():
            return "A search value is required"
        query = query.strip()
        if len(query) > MAX_QUERY_LENGTH:
            return f"The search value is longer than {MAX_QUERY_LENGTH} characters"
        if search_type == 'vin' and not VIN_RE.match(query.upper()):
            return "That is not a valid VIN (11 to 17 letters and digits, no I, O or Q)"
        if search_type == 'alternatives' and not ID_RE.match(query):
            return "Article ID must be numeric"
        return None

    @staticmethod
    def _error_result(data):
        message = data.get("message", data.get("error", "Unknown error"))
        if data.get("error") in ("quota_exceeded", "budget_exceeded"):
            return {"status": 429, "error": "Monthly quota exceeded", "message": message, "data": []}
        if data.get("error") == "rate_limit":
            return {"status": 429, "error": "Too Many Requests", "message": message, "data": []}
        if data.get("error") == "forbidden":
            return {"status": 403, "error": "Forbidden", "message": message, "data": []}
        return {"status": 500, "error": "API Request Failed", "message": message, "data": []}

    @staticmethod
    def _extract_articles(data):
        articles = data.get('articles') if isinstance(data, dict) else data
        return [a for a in (articles or []) if isinstance(a, dict)]

    def _bound_articles(self, articles):
        limit = self._api()._get_int_param('tecdoc.max_alternatives', DEFAULT_MAX_ALTERNATIVES)
        unique, seen = [], set()
        for art in articles:
            art_id = art.get('articleId') or art.get('articleNo')
            if art_id in seen:
                continue
            seen.add(art_id)
            unique.append(art)
        # stable sort: articles with an image first, API order otherwise
        unique.sort(key=lambda a: not a.get('s3image'))
        return unique[:limit] if limit else unique

    def _fetch_fitment(self, number):
        """Compatible cars per article for one OEM/article number, filtered to the configured makes."""
        data = self._api()._make_rapidapi_request(COMPAT_ENDPOINT, params={
            "langId": self._lang_id(), "articleOemNo": number})
        if not isinstance(data, dict) or 'error' in data:
            return {}
        makes = self._fitment_makes()
        fitment = {}
        for art in data.get('articles') or []:
            cars, seen = [], set()
            for car in art.get('compatibleCars') or []:
                vid = str(car.get('vehicleId', ''))
                if not vid or vid == 'None' or vid in seen:
                    continue
                if makes and str(car.get('manufacturerName', '')).upper() not in makes:
                    continue
                seen.add(vid)
                cars.append(car)
            if cars:
                fitment[str(art.get('articleId'))] = cars[:DEFAULT_MAX_VEHICLES]
        return fitment

    def _article_vals(self, article):
        product_type = article.get('articleProductName') or ''
        supplier = article.get('supplierName') or article.get('brandName') or ''
        number = article.get('articleNo') or article.get('articleSearchNo') or ''
        name = " ".join(p for p in (supplier, number) if p)
        if product_type:
            name = f"{name} - {product_type}" if name else product_type
        return {
            'name': name or 'Unknown Part',
            'part_number': number,
            'brand': supplier,
            'article_id': str(article.get('articleId') or '') or False,
            'category': product_type,
            'raw_data': json.dumps(article),
        }

    def _save_articles(self, articles, oem_number=None, fitment=None, extra_vehicle=None):
        fitment = fitment or {}
        Vehicle = self.env['tecdoc.vehicle']
        vehicles_by_id = Vehicle.upsert_from_cars([car for cars in fitment.values() for car in cars])

        article_ids = [str(a.get('articleId')) for a in articles if a.get('articleId')]
        existing = {p.article_id: p for p in self.search([('article_id', 'in', article_ids)])} if article_ids else {}

        saved = self.browse()
        for article in articles:
            vals = self._article_vals(article)
            if not vals['part_number']:
                continue
            part = existing.get(vals['article_id'])
            if oem_number:
                current = [o.strip() for o in (part.oem_number or '').split(',')] if part else []
                if oem_number not in current:
                    current.append(oem_number)
                vals['oem_number'] = ", ".join(o for o in current if o)
            if part:
                part.write(vals)
            else:
                part = self.create(vals)

            vehicle_ids = [vehicles_by_id[str(c.get('vehicleId'))].id
                           for c in fitment.get(vals['article_id'] or '', []) if str(c.get('vehicleId')) in vehicles_by_id]
            if extra_vehicle:
                vehicle_ids.append(extra_vehicle.id)
            if vehicle_ids:
                part.vehicle_ids = [(4, vid) for vid in vehicle_ids]

            url = article.get('s3image')
            if url and url not in part.image_ids.mapped('image_url'):
                self.env['tecdoc.part.image'].create({
                    'name': article.get('articleMediaFileName') or 'image',
                    'part_id': part.id,
                    'image_url': url,
                })
            saved |= part
        return saved

    def _vin_lookup(self, vin):
        api_model = self._api()
        data = api_model._make_rapidapi_request(f"/vin/tecdoc-vin-check/{vin}")
        if isinstance(data, dict) and "error" in data:
            return self._error_result(data)
        inner = data.get('data', {}) if isinstance(data, dict) else {}

        decoder = api_model._make_rapidapi_request(f"/vin/decoder-v2/{vin}")
        decoder_data = decoder if isinstance(decoder, dict) and 'error' not in decoder else {}

        self.env['tecdoc.vehicle'].save_from_vin(vin, inner, decoder_data)
        return {"status": 200, "data": inner, "decoder": decoder_data, "cached": False}

    # ------------------------------------------------------------------
    # record actions (buttons)
    # ------------------------------------------------------------------
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

    def _notify(self, title, message, kind='danger'):
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': title, 'message': message, 'type': kind}}

    def action_fetch_cross_references(self, notify=True):
        CrossRef = self.env['tecdoc.part.cross_reference']
        lang_id = self._lang_id()
        for record in self:
            if not record.article_id:
                continue
            data = self._api()._make_rapidapi_request(_xref_endpoint(record.article_id, lang_id))
            if isinstance(data, dict) and 'error' in data:
                if notify:
                    return self._notify('API Error', data['message'])
                continue
            known = set(record.cross_reference_ids.mapped('oem_number'))
            for cross in self._bound_articles(self._extract_articles(data)):
                number = cross.get('articleNo')
                brand = cross.get('supplierName') or ''
                if number and number not in known:
                    CrossRef.create({'part_id': record.id, 'oem_number': number, 'brand': brand})
                    known.add(number)
        if notify:
            return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_fetch_linked_vehicles(self):
        Vehicle = self.env['tecdoc.vehicle']
        for record in self:
            numbers = [o.strip() for o in (record.oem_number or '').split(',') if o.strip()] or [record.part_number]
            fitment = self._fetch_fitment(numbers[0]) if numbers[0] else {}
            cars = fitment.get(record.article_id or '') or [c for cs in fitment.values() for c in cs]
            vehicles = Vehicle.upsert_from_cars(cars[:DEFAULT_MAX_VEHICLES])
            if vehicles:
                record.vehicle_ids = [(4, v.id) for v in vehicles.values()]
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_refetch_all_data(self):
        self._reparse_raw_data()
        self.action_fetch_cross_references(notify=False)
        self.action_fetch_linked_vehicles()
        self.action_create_odoo_product()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_fallback_search_missing_info(self):
        """Find catalog data for parts that only have a part number (e.g. imported or pending)."""
        lang_id = self._lang_id()
        for record in self:
            candidates = [record.part_number] + record.cross_reference_ids.mapped('oem_number')
            for candidate in filter(None, candidates):
                data = self._api()._make_rapidapi_request(SEARCH_ENDPOINT, params={
                    "langId": lang_id, "articleNo": candidate, "articleType": "ArticleNumber"})
                if isinstance(data, dict) and 'error' in data:
                    return self._notify('API Error', data['message'])
                articles = self._bound_articles(self._extract_articles(data))
                if not articles:
                    continue
                vals = self._article_vals(articles[0])
                update = {k: v for k, v in vals.items()
                          if k in ('brand', 'category', 'raw_data') or not record[k]
                          or (k == 'name' and 'Pending Fetch' in (record.name or ''))}
                update.pop('part_number', None)
                if vals['article_id'] and self.search_count([('article_id', '=', vals['article_id']), ('id', '!=', record.id)]):
                    _logger.info("Article %s already saved as another part; not reassigning", vals['article_id'])
                    update.pop('article_id', None)
                if not record.oem_number:
                    update['oem_number'] = candidate
                record.write(update)
                url = articles[0].get('s3image')
                if url and url not in record.image_ids.mapped('image_url'):
                    self.env['tecdoc.part.image'].create({'name': 'image', 'part_id': record.id, 'image_url': url})
                if not record.vehicle_ids:
                    record.action_fetch_linked_vehicles()
                break
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _reparse_raw_data(self):
        for record in self:
            if not record.raw_data:
                continue
            try:
                vals = self._article_vals(json.loads(record.raw_data))
            except (ValueError, TypeError) as exc:
                _logger.warning("Could not re-parse raw data for %s: %s", record.part_number, exc)
                continue
            record.write({k: vals[k] for k in ('name', 'brand', 'category') if vals[k]})

    def _fetch_specs(self):
        ids = [int(r.article_id) for r in self if r.article_id and r.article_id.isdigit()]
        if not ids:
            return
        data = self._api()._make_rapidapi_request(SPECS_ENDPOINT, method="POST",
                                                  payload={"langId": int(self._lang_id()), "articleIds": ids})
        if not isinstance(data, dict) or 'articles' not in data:
            return
        specs_map = {str(a.get('articleId')): a.get('allSpecifications') or [] for a in data['articles']}
        for record in self:
            specs = specs_map.get(record.article_id)
            if not specs:
                continue
            vals, lines = {}, []
            for spec in specs:
                name_raw = str(spec.get('criteriaName', ''))
                val_raw = str(spec.get('criteriaValue', ''))
                if name_raw and val_raw:
                    lines.append(f"• {name_raw}: {val_raw}")
                name, val_str = name_raw.lower(), val_raw.replace(',', '.')
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
            if lines:
                vals['specs_text'] = "Specifications:\n" + "\n".join(lines)
            record.write(vals)

    def _ensure_images_downloaded(self):
        for img in self.mapped('image_ids').filtered(lambda i: i.image_url and not i.image):
            content = self._api()._download_binary(img.image_url)
            if not content:
                continue
            try:
                image_process(content, verify_resolution=True)
            except (UserError, ValueError, OSError) as exc:
                _logger.warning("Skipping unreadable image %s: %s", img.image_url, exc)
                continue
            img.image = base64.b64encode(content)

    def action_create_odoo_product(self):
        """Add to catalog: create or update the Odoo product. Only links products that already exist."""
        ProductTmpl = self.env['product.template']
        self.filtered(lambda r: not r.specs_text)._fetch_specs()
        for record in self:
            record._ensure_images_downloaded()
            vals = {
                'name': record.name or record.part_number,
                'default_code': record.part_number,
                'type': 'consu',
                'is_storable': True,
                'description': record.category or "",
                'tecdoc_part_id': record.id,
                'weight': record.weight,
                'volume': record.volume,
                'description_sale': record.specs_text,
                'description_purchase': f"TecDoc Brand: {record.brand}\nPart Number: {record.part_number}\nOEMs: {record.oem_number or 'N/A'}",
            }
            if 'hs_code' in ProductTmpl._fields and record.hs_code:
                vals['hs_code'] = record.hs_code
            # barcodes are unique across products
            if record.barcode and not self.env['product.product'].search_count([('barcode', '=', record.barcode)]):
                vals['barcode'] = record.barcode

            if record.product_tmpl_id:
                record.product_tmpl_id.write(vals)
                product_tmpl = record.product_tmpl_id
            else:
                product_tmpl = ProductTmpl.create(vals)
                record.product_tmpl_id = product_tmpl.id

            images = record.image_ids.filtered('image')
            if images:
                product_tmpl.image_1920 = images[0].image
                product_tmpl.product_template_image_ids = [(5, 0, 0)] + [
                    (0, 0, {'name': img.name or f"{product_tmpl.name} - Image {idx + 2}", 'image_1920': img.image})
                    for idx, img in enumerate(images[1:])]

            if record.category:
                categ = self.env['product.public.category'].search([('name', '=', record.category)], limit=1)
                if not categ:
                    categ = self.env['product.public.category'].create({'name': record.category})
                product_tmpl.public_categ_ids = [(4, categ.id)]

            if record.brand:
                vendor = self.env['res.partner'].search([('name', '=', record.brand)], limit=1)
                if not vendor:
                    vendor = self.env['res.partner'].create({'name': record.brand, 'supplier_rank': 1})
                if not self.env['product.supplierinfo'].search_count([('product_tmpl_id', '=', product_tmpl.id), ('partner_id', '=', vendor.id)]):
                    self.env['product.supplierinfo'].create({'product_tmpl_id': product_tmpl.id, 'partner_id': vendor.id})

            alternatives = record._find_existing_alternative_products() - product_tmpl
            if alternatives:
                product_tmpl.alternative_product_ids = [(6, 0, alternatives.ids)]

            if record.accessories_raw:
                try:
                    numbers = [a.get('articleNo') for a in json.loads(record.accessories_raw) if a.get('articleNo')]
                except (ValueError, TypeError, AttributeError) as exc:
                    _logger.warning("Accessories data unreadable for %s: %s", record.part_number, exc)
                    numbers = []
                accessories = ProductTmpl.search([('default_code', 'in', numbers)]) if numbers else ProductTmpl
                if accessories:
                    product_tmpl.accessory_product_ids = [(6, 0, accessories.ids)]

    def _find_existing_alternative_products(self):
        """Products already in the catalog that share an OEM number or are listed as cross references."""
        self.ensure_one()
        products = self.env['product.template']
        for oem in [o.strip() for o in (self.oem_number or '').split(',') if o.strip()]:
            siblings = self.search([('oem_number', 'ilike', oem), ('id', '!=', self.id), ('product_tmpl_id', '!=', False)])
            products |= siblings.mapped('product_tmpl_id')
        numbers = self.cross_reference_ids.mapped('oem_number')
        if numbers:
            products |= products.search([('default_code', 'in', numbers)])
        return products
