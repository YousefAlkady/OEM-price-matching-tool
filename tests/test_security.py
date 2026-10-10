import os
from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from .common import FakeBinaryResponse, FakeResponse, load_data, patch_router

SEARCH = "search-articles-by-article-no"
COMPAT = "get-compatible-cars-by-oem-no"


@tagged('post_install', '-at_install')
class TestSecurity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env['ir.config_parameter'].sudo()
        icp.set_param('tecdoc.rapidapi_key', 'test-key')
        icp.set_param('tecdoc.monthly_call_budget', 0)
        icp.set_param('tecdoc.user_calls_per_minute', 0)
        cls.viewer = new_test_user(cls.env, 'tecdoc_viewer', groups='base.group_user,rapidapi_bdeel.group_tecdoc_viewer')
        cls.operator = new_test_user(cls.env, 'tecdoc_operator', groups='base.group_user,rapidapi_bdeel.group_tecdoc_operator')
        cls.manager = new_test_user(cls.env, 'tecdoc_manager', groups='base.group_user,rapidapi_bdeel.group_tecdoc_manager')
        cls.part = cls.env['tecdoc.part'].create({'name': 'Test part', 'part_number': 'T-1'})

    def _http(self, **routes):
        base = {
            SEARCH: FakeResponse(200, load_data('search_oem_toyota.json')),
            COMPAT: FakeResponse(200, load_data('compatible_cars_toyota.json')),
        }
        base.update(routes)
        patcher, mocked = patch_router(base)
        self.addCleanup(patcher.stop)
        return mocked

    # --- roles -------------------------------------------------------
    def test_viewer_can_read_but_not_change_parts(self):
        part = self.part.with_user(self.viewer)
        self.assertEqual(part.name, 'Test part')
        with self.assertRaises(AccessError):
            part.write({'name': 'changed'})
        with self.assertRaises(AccessError):
            self.env['tecdoc.part'].with_user(self.viewer).create({'name': 'x', 'part_number': 'x'})

    def test_viewer_cannot_make_paid_api_calls(self):
        http = self._http()
        result = self.env['tecdoc.part'].with_user(self.viewer).search_catalog('oem_number', '04465-0K090')
        self.assertEqual(result['status'], 403)
        self.assertEqual(http.calls, [])

    def test_internal_user_without_role_cannot_read_parts(self):
        plain = new_test_user(self.env, 'plain_user', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.part.with_user(plain).read(['name'])

    def test_user_without_role_can_still_open_linked_products(self):
        product = self.env['product.template'].create({'name': 'Linked product', 'tecdoc_part_id': self.part.id})
        self.env['tecdoc.part.image'].create({'part_id': self.part.id, 'image_url': 'https://x.your-objectstorage.com/a.webp'})
        sales = new_test_user(self.env, 'sales_only', groups='base.group_user,sales_team.group_sale_salesman')
        Product = self.env['product.template'].with_user(sales)
        arch_fields = Product.get_views([(False, 'form')])['models']['product.template']['fields']
        # what the web client does when it opens the form
        Product.browse(product.id).web_read({name: {} for name in arch_fields})

    def test_operator_can_search_and_save_but_not_delete(self):
        self._http()
        result = self.env['tecdoc.part'].with_user(self.operator).search_catalog('oem_number', '04465-0K090')
        self.assertEqual(result['status'], 200)
        with self.assertRaises(AccessError):
            self.part.with_user(self.operator).unlink()

    def test_manager_can_delete_parts(self):
        self.part.with_user(self.manager).unlink()
        self.assertFalse(self.part.exists())

    def test_only_manager_reads_the_api_log(self):
        with self.assertRaises(AccessError):
            self.env['tecdoc.api.log'].with_user(self.operator).search([])
        self.env['tecdoc.api.log'].with_user(self.manager).search([])

    def test_nobody_but_admin_edits_the_api_log(self):
        log = self.env['tecdoc.api.log'].sudo().create({'endpoint': '/x', 'billed': True})
        with self.assertRaises(AccessError):
            log.with_user(self.manager).unlink()

    # --- input validation ---------------------------------------------
    def test_invalid_vin_is_rejected_without_api_call(self):
        http = self._http()
        result = self.env['tecdoc.part'].with_user(self.operator).search_catalog('vin', '../manufacturers/list')
        self.assertEqual(result['status'], 400)
        self.assertEqual(http.calls, [])

    def test_non_numeric_article_id_is_rejected_without_api_call(self):
        http = self._http()
        result = self.env['tecdoc.part'].with_user(self.operator).search_catalog('alternatives', '1/../../vin/decoder-v2/X')
        self.assertEqual(result['status'], 400)
        self.assertEqual(http.calls, [])

    def test_overlong_query_is_rejected_without_api_call(self):
        http = self._http()
        result = self.env['tecdoc.part'].with_user(self.operator).search_catalog('oem_number', 'A' * 200)
        self.assertEqual(result['status'], 400)
        self.assertEqual(http.calls, [])

    # --- server-side fetches (SSRF) -------------------------------------
    def test_image_download_refuses_unlisted_hosts(self):
        http = self._http(**{'169.254.169.254': FakeBinaryResponse(), 'evil.example': FakeBinaryResponse()})
        api = self.env['tecdoc.api.abstract']
        self.assertIsNone(api._download_binary('http://169.254.169.254/latest/meta-data'))
        self.assertIsNone(api._download_binary('https://evil.example/x.png'))
        self.assertIsNone(api._download_binary('https://fsn1.your-objectstorage.com.evil.example/x.png'))
        self.assertEqual(http.calls, [])

    def test_image_download_allows_the_catalog_image_host(self):
        self._http(**{'your-objectstorage.com': FakeBinaryResponse()})
        content = self.env['tecdoc.api.abstract']._download_binary('https://fsn1.your-objectstorage.com/tecdoc2025/x.webp')
        self.assertTrue(content)

    # --- secrets ----------------------------------------------------------
    def test_api_key_from_environment_takes_precedence(self):
        http = self._http()
        with patch.dict(os.environ, {'TECDOC_RAPIDAPI_KEY': 'env-key'}):
            self.env['tecdoc.part'].search_catalog('oem_number', '04465-0K090')
        sent_key = http.get.call_args.kwargs['headers']['x-rapidapi-key']
        self.assertEqual(sent_key, 'env-key')
