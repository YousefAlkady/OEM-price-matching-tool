from odoo.tests.common import TransactionCase, tagged

from .common import FakeBinaryResponse, FakeResponse, load_data, patch_router

SEARCH = "search-articles-by-article-no"
COMPAT = "get-compatible-cars-by-oem-no"
XREF = "select-article-cross-references"
SPECS = "get-article-specifications-list-of-articles-ids"
TOYOTA_OEM = "04465-0K090"


@tagged('post_install', '-at_install')
class TestCatalogSearch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env['ir.config_parameter'].sudo()
        icp.set_param('tecdoc.rapidapi_key', 'test-key')
        icp.set_param('tecdoc.monthly_call_budget', 0)
        icp.set_param('tecdoc.user_calls_per_minute', 0)
        icp.set_param('tecdoc.max_alternatives', 50)
        icp.set_param('tecdoc.fitment_makes', '')
        cls.Part = cls.env['tecdoc.part']

    def _routes(self, **overrides):
        routes = {
            SEARCH: FakeResponse(200, load_data('search_oem_toyota.json')),
            COMPAT: FakeResponse(200, load_data('compatible_cars_toyota.json')),
            XREF: FakeResponse(200, load_data('cross_references.json')),
            SPECS: FakeResponse(200, {"count": 0, "articles": []}),
            "your-objectstorage.com": FakeBinaryResponse(),
        }
        routes.update(overrides)
        patcher, mocked = patch_router(routes)
        self.addCleanup(patcher.stop)
        return mocked

    def _billed(self):
        return self.env['tecdoc.api.abstract'].get_monthly_usage()[0]

    def test_oem_search_costs_at_most_two_billed_calls(self):
        self._routes()
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        self.assertLessEqual(self._billed(), 2)

    def test_part_number_search_costs_at_most_three_billed_calls(self):
        self._routes()
        self.Part.search_catalog('part_number', '0 986 494 153')
        self.assertLessEqual(self._billed(), 3)

    def test_repeat_search_makes_no_http_calls(self):
        http = self._routes()
        first = self.Part.search_catalog('oem_number', TOYOTA_OEM)
        calls_after_first = len(http.calls)
        second = self.Part.search_catalog('oem_number', '044650K090')
        self.assertEqual(len(http.calls), calls_after_first)
        self.assertFalse(first['cached'])
        self.assertTrue(second['cached'])

    def test_search_creates_no_products(self):
        self._routes()
        before = self.env['product.template'].search_count([])
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        self.assertEqual(self.env['product.template'].search_count([]), before)

    def test_search_keeps_at_most_max_alternatives(self):
        self.env['ir.config_parameter'].sudo().set_param('tecdoc.max_alternatives', 10)
        self._routes()
        result = self.Part.search_catalog('oem_number', TOYOTA_OEM)
        self.assertEqual(len(result['data']), 10)
        self.assertEqual(self.Part.search_count([]), 10)

    def test_articles_with_images_rank_first(self):
        self._routes()
        result = self.Part.search_catalog('oem_number', TOYOTA_OEM)
        has_image = [bool(a.get('s3image')) for a in result['data']]
        self.assertEqual(has_image, sorted(has_image, reverse=True))

    def test_fitment_is_limited_to_configured_makes(self):
        self.env['ir.config_parameter'].sudo().set_param('tecdoc.fitment_makes', 'toyota, lexus')
        self._routes()
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        makes = set(self.env['tecdoc.vehicle'].search([]).mapped('brand'))
        self.assertTrue(makes)
        self.assertNotIn('MITSUBISHI', makes)

    def test_each_part_gets_only_its_own_fitment(self):
        self._routes()
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        expected = {str(a['articleId']): {str(c['vehicleId']) for c in a['compatibleCars']}
                    for a in load_data('compatible_cars_toyota.json')['articles']}
        parts = self.Part.search([('article_id', 'in', list(expected))])
        self.assertTrue(parts)
        for part in parts:
            self.assertEqual(set(part.vehicle_ids.mapped('vehicle_id')), expected[part.article_id], part.article_id)

    def test_unreadable_image_does_not_block_add_to_catalog(self):
        self._routes(**{"your-objectstorage.com": FakeBinaryResponse(content=b'not an image')})
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        part = self.Part.search([('article_id', '=', '70801')])
        with self.assertLogs('odoo.addons.rapidapi_bdeel.models.tecdoc_part', level='WARNING'):
            part.action_create_odoo_product()
        self.assertTrue(part.product_tmpl_id)
        self.assertFalse(part.product_tmpl_id.image_1920)

    def test_vehicle_production_dates_are_filled(self):
        self._routes()
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        vehicles = self.env['tecdoc.vehicle'].search([])
        self.assertTrue(vehicles)
        self.assertTrue(all(v.make_date for v in vehicles))

    def test_category_is_the_product_type_not_the_name(self):
        self._routes()
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        part = self.Part.search([('article_id', '=', '70801')])
        self.assertEqual(part.category, 'Brake Pad Set, disc brake')
        self.assertIn('BOSCH', part.name)
        self.assertNotEqual(part.name, part.category)

    def test_searched_oem_number_is_recorded_on_parts(self):
        self._routes()
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        part = self.Part.search([('article_id', '=', '70801')])
        self.assertIn(TOYOTA_OEM, part.oem_number)

    def test_search_stores_image_links_without_downloading(self):
        http = self._routes()
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        self.assertFalse([u for u in http.calls if 'objectstorage' in u])
        part = self.Part.search([('article_id', '=', '70801')])
        self.assertTrue(part.image_ids.image_url)

    def test_no_catalog_data_returns_empty_and_is_cached(self):
        http = self._routes(**{SEARCH: FakeResponse(200, load_data('search_oem_empty.json')),
                               COMPAT: FakeResponse(200, {"countArticles": None, "articles": []})})
        result = self.Part.search_catalog('oem_number', '86551-AA000')
        self.assertEqual(result['data'], [])
        calls = len(http.calls)
        self.Part.search_catalog('oem_number', '86551-AA000')
        self.assertEqual(len(http.calls), calls)

    def test_add_to_catalog_creates_one_product_and_no_alternative_products(self):
        self._routes()
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        part = self.Part.search([('article_id', '=', '70801')])
        part.cross_reference_ids = [(0, 0, {'oem_number': 'ZZ-999', 'brand': 'TEXTAR'})]
        before = self.env['product.template'].search_count([])
        part.action_create_odoo_product()
        self.assertEqual(self.env['product.template'].search_count([]), before + 1)
        self.assertTrue(part.product_tmpl_id.image_1920)
        self.assertTrue(part.product_tmpl_id.is_storable)

    def test_same_article_is_saved_once(self):
        self._routes()
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        self.Part.search_catalog('part_number', '0 986 494 153')
        self.assertEqual(self.Part.search_count([('article_id', '=', '70801')]), 1)

    # --- review findings ------------------------------------------------
    def test_archived_part_is_reused_not_recreated(self):
        self._routes()
        self.Part.search_catalog('oem_number', TOYOTA_OEM)
        part = self.Part.search([('article_id', '=', '70801')])
        part.active = False
        self.Part.search_catalog('part_number', '0 986 494 153')
        self.assertEqual(self.Part.with_context(active_test=False).search_count([('article_id', '=', '70801')]), 1)

    def test_same_oem_in_different_spellings_is_stored_once(self):
        self._routes()
        self.Part.search_catalog('oem_number', '04465-0K090')
        self.Part.search_catalog('oem_number', '044650K090')
        part = self.Part.search([('article_id', '=', '70801')])
        self.assertEqual(part.oem_number, '04465-0K090')

    def test_alternatives_need_an_exact_oem_match(self):
        Product = self.env['product.template']
        near = self.Part.create({'name': 'near', 'part_number': 'N1', 'oem_number': '12345, 01234-X',
                                 'product_tmpl_id': Product.create({'name': 'near product'}).id})
        same = self.Part.create({'name': 'same', 'part_number': 'S1', 'oem_number': '12-34',
                                 'product_tmpl_id': Product.create({'name': 'same product'}).id})
        part = self.Part.create({'name': 'part', 'part_number': 'P1', 'oem_number': '1234'})
        found = part._find_existing_alternative_products()
        self.assertIn(same.product_tmpl_id, found)
        self.assertNotIn(near.product_tmpl_id, found)
