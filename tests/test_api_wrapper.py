from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from .common import FakeResponse, patch_http

SEARCH = "/artlookup/search-articles-by-article-no"


@tagged('post_install', '-at_install')
class TestApiWrapper(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        icp = cls.env['ir.config_parameter'].sudo()
        icp.set_param('tecdoc.rapidapi_key', 'test-key')
        icp.set_param('tecdoc.monthly_call_budget', 0)
        icp.set_param('tecdoc.user_calls_per_minute', 0)
        cls.api = cls.env['tecdoc.api.abstract']
        cls.Log = cls.env['tecdoc.api.log'].sudo()

    def _http(self, *responses):
        patcher, mocked = patch_http(*responses)
        self.addCleanup(patcher.stop)
        return mocked

    def _search(self, number):
        return self.api._make_rapidapi_request(SEARCH, params={"langId": "4", "articleNo": number, "articleType": "OENumber"})

    def test_successful_call_is_logged_as_billed(self):
        self._http(FakeResponse(200, {"articles": [{"articleId": 1}]}))
        self._search("04465-0K090")
        log = self.Log.search([('endpoint', '=', SEARCH)], limit=1)
        self.assertEqual(log.status, 'success')
        self.assertTrue(log.billed)
        self.assertEqual(log.response_code, 200)

    def test_repeat_call_is_served_from_cache_without_http(self):
        http = self._http(FakeResponse(200, {"articles": [{"articleId": 1}]}))
        first = self._search("04465-0K090")
        second = self._search("04465-0K090")
        self.assertEqual(first, second)
        self.assertEqual(http.get.call_count, 1)

    def test_part_number_spellings_share_one_cache_entry(self):
        http = self._http(FakeResponse(200, {"articles": [{"articleId": 1}]}))
        for spelling in ("86551-AA000", "86551AA000", "86551 aa000"):
            self._search(spelling)
        self.assertEqual(http.get.call_count, 1)

    def test_expired_cache_entry_is_refetched(self):
        http = self._http(FakeResponse(200, {"articles": []}))
        self._search("04465-0K090")
        self.env['tecdoc.api.cache'].sudo().search([]).write({'expires_at': fields.Datetime.now() - timedelta(days=1)})
        self._search("04465-0K090")
        self.assertEqual(http.get.call_count, 2)

    def test_error_responses_are_not_cached(self):
        http = self._http(FakeResponse(500, {}))
        with self.assertLogs('odoo.addons.rapidapi_bdeel.models.rapidapi_abstract', level='ERROR'):
            result = self._search("04465-0K090")
            self._search("04465-0K090")
        self.assertEqual(result['error'], 'http_500')
        self.assertEqual(http.get.call_count, 2)

    def test_budget_reached_blocks_the_call(self):
        self.env['ir.config_parameter'].sudo().set_param('tecdoc.monthly_call_budget', 1)
        http = self._http(FakeResponse(200, {"articles": []}))
        self._search("AAA1")
        result = self._search("BBB2")
        self.assertEqual(result['error'], 'budget_exceeded')
        self.assertIn('message', result)
        self.assertEqual(http.get.call_count, 1)

    def test_user_rate_limit_blocks_the_call(self):
        self.env['ir.config_parameter'].sudo().set_param('tecdoc.user_calls_per_minute', 1)
        http = self._http(FakeResponse(200, {"articles": []}))
        self._search("AAA1")
        result = self._search("BBB2")
        self.assertEqual(result['error'], 'rate_limit')
        self.assertEqual(http.get.call_count, 1)

    def test_monthly_quota_429_is_reported_without_retry(self):
        http = self._http(FakeResponse(429, {}, {"x-ratelimit-requests-remaining": "0"}))
        result = self._search("04465-0K090")
        self.assertEqual(result['error'], 'quota_exceeded')
        self.assertEqual(http.get.call_count, 1)

    def test_burst_429_is_retried_once(self):
        http = self._http(FakeResponse(429, {}, {"x-ratelimit-requests-remaining": "500"}),
                          FakeResponse(200, {"articles": []}))
        result = self._search("04465-0K090")
        self.assertEqual(result, {"articles": []})
        self.assertEqual(http.get.call_count, 2)

    def test_usage_counts_only_billed_calls_of_this_month(self):
        self._http(FakeResponse(200, {"articles": []}))
        self._search("04465-0K090")
        self._search("04465-0K090")  # cache hit, not billed
        used, _budget = self.api.get_monthly_usage()
        self.assertEqual(used, 1)
