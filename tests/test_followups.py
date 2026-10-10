import json

from odoo.tests.common import TransactionCase, tagged

from .common import FakeResponse, load_data, patch_router

SEARCH = "search-articles-by-article-no"
COMPAT = "get-compatible-cars-by-oem-no"
VIN_CHECK = "tecdoc-vin-check"
VIN_DECODER = "decoder-v2"
SAMPLE_VIN = "WVWZZZ1JZXW000001"


@tagged('post_install', '-at_install')
class TestPhase2Followups(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env['ir.config_parameter'].sudo()
        icp.set_param('tecdoc.rapidapi_key', 'test-key')
        icp.set_param('tecdoc.monthly_call_budget', 0)
        icp.set_param('tecdoc.user_calls_per_minute', 0)
        cls.Part = cls.env['tecdoc.part']
        cls.Log = cls.env['tecdoc.api.log'].sudo()

    def _routes(self, **overrides):
        routes = {
            SEARCH: FakeResponse(200, load_data('search_oem_toyota.json')),
            COMPAT: FakeResponse(200, load_data('compatible_cars_toyota.json')),
            VIN_CHECK: FakeResponse(200, load_data('vin_check.json')),
            VIN_DECODER: FakeResponse(200, load_data('vin_decoder.json')),
        }
        routes.update(overrides)
        patcher, mocked = patch_router(routes)
        self.addCleanup(patcher.stop)
        return mocked

    # 1. per-user limit is for interactive searches only -----------------
    def test_bulk_deep_search_is_not_stopped_by_the_per_user_limit(self):
        self.env['ir.config_parameter'].sudo().set_param('tecdoc.user_calls_per_minute', 1)
        self._routes()
        parts = self.Part.create([{'name': f'Pending Fetch - P{i}', 'part_number': f'P-{i}'} for i in range(3)])
        parts.action_fallback_search_missing_info()
        self.assertFalse(self.Log.search_count([('error_message', 'ilike', 'Too many searches')]))
        self.assertGreaterEqual(self.Log.search_count([('billed', '=', True)]), 3)

    def test_interactive_search_is_limited_per_user(self):
        self.env['ir.config_parameter'].sudo().set_param('tecdoc.user_calls_per_minute', 1)
        self._routes()
        self.Part.search_catalog('oem_number', '04465-0K090')
        result = self.Part.search_catalog('oem_number', '58101-3XA10')
        self.assertEqual(result['status'], 429)

    # 2. cache entries are compressed -----------------------------------
    def test_cache_entries_are_stored_compressed(self):
        self._routes()
        body = load_data('compatible_cars_toyota.json')
        api = self.env['tecdoc.api.abstract']
        first = api._make_rapidapi_request("/articles/get-compatible-cars-by-oem-no/type-id/1",
                                           params={"langId": "4", "articleOemNo": "04465-0K090"})
        entry = self.env['tecdoc.api.cache'].sudo().search([], limit=1, order='id desc')
        self.assertLess(len(entry.response), len(json.dumps(body)) / 5)
        second = api._make_rapidapi_request("/articles/get-compatible-cars-by-oem-no/type-id/1",
                                            params={"langId": "4", "articleOemNo": "04465-0K090"})
        self.assertEqual(first, second)

    def test_old_uncompressed_cache_rows_are_still_readable(self):
        Cache = self.env['tecdoc.api.cache'].sudo()
        Cache.store('legacy-key', '/x', {"a": 1}, 30)
        Cache.search([('key', '=', 'legacy-key')]).response = json.dumps({"a": 1})
        self.assertEqual(Cache.get_valid('legacy-key'), {"a": 1})

    # 3. VIN lookup ------------------------------------------------------
    def test_vin_lookup_saves_the_vehicle_from_catalog_data(self):
        self._routes()
        result = self.Part.search_catalog('vin', SAMPLE_VIN.lower())
        self.assertEqual(result['status'], 200)
        vehicle = self.env['tecdoc.vehicle'].search([('vin', '=', SAMPLE_VIN)])
        self.assertEqual(len(vehicle), 1)
        self.assertEqual(vehicle.vehicle_id, '8456')
        self.assertEqual(vehicle.brand, 'VW')
        self.assertEqual(vehicle.vehicle_model, 'GOLF IV (1J1)')

    def test_vin_without_vehicle_id_stores_no_fake_id(self):
        check = load_data('vin_check.json')
        check['data']['matchingVehicles']['array'] = [{'carName': 'VW GOLF IV (1J1) 1.9 TDI', 'vehicleId': None}]
        self._routes(**{VIN_CHECK: FakeResponse(200, check)})
        self.Part.search_catalog('vin', SAMPLE_VIN)
        vehicle = self.env['tecdoc.vehicle'].search([('vin', '=', SAMPLE_VIN)])
        self.assertFalse(vehicle.vehicle_id)

    def test_repeated_vin_lookup_does_not_duplicate_the_vehicle(self):
        self._routes()
        self.Part.search_catalog('vin', SAMPLE_VIN)
        self.Part.search_catalog('vin', SAMPLE_VIN)
        self.assertEqual(self.env['tecdoc.vehicle'].search_count([('vin', '=', SAMPLE_VIN)]), 1)
