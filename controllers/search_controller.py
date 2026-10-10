import logging
import time

from odoo import http
from odoo.http import request

from .db_service import DbServiceMixin

_logger = logging.getLogger(__name__)


class SearchController(DbServiceMixin, http.Controller):

    @http.route('/api/tecdoc/search', type='json', auth='user', methods=['POST'], csrf=False)
    def search_parts(self, search_type, query=None, **kwargs):
        now = time.time()
        session = request.session
        history = session.get('tecdoc_search_history', [])
        history = [t for t in history if now - t < 60]  # keep last 60 seconds
        if len(history) > 30:  # max 30 requests per minute
            _logger.warning("Rate limit exceeded for user session.")
            return {"status": 429, "error": "Too Many Requests", "message": "Please wait a moment before searching again.", "data": []}
        history.append(now)
        session['tecdoc_search_history'] = history


        # check local cache first
        cached_data = self._check_db_for_parts(search_type, query)
        if cached_data:
            _logger.info(f"Returning CACHED data for {search_type}: {query}")
            return {"status": 200, "data": cached_data, "cached": True}

        # build request params based on search type
        method   = "GET"
        payload  = None
        params   = None
        endpoint = ""

        if search_type == 'vin':
            endpoint = f"/vin/tecdoc-vin-check/{query}"

        elif search_type == 'part_number':
            endpoint = "/artlookup/search-articles-by-article-no"
            params   = {"langId": "4", "articleNo": query, "articleType": "ArticleNumber"}

        elif search_type == 'oem_number':
            endpoint = "/artlookup/search-articles-by-article-no"
            params   = {"langId": "4", "articleNo": query, "articleType": "OENumber"}

        elif search_type == 'engine_code':
            endpoint = "/artlookup/search-articles-by-article-no"
            params   = {"langId": "4", "articleNo": query, "articleType": "EngineCode"}

        elif search_type == 'alternatives':
            if not query:
                return {
                    "status":  400,
                    "error":   "Bad Request",
                    "message": "Article ID is required for alternatives search",
                }
            endpoint = f"/artlookup/select-article-cross-references/article-id/{query}/lang-id/4"

        elif search_type == 'text':
            endpoint = "/artlookup/search-articles-by-article-no"
            params   = {"langId": "4", "articleNo": query, "articleType": "ArticleNumber"}

        elif search_type == 'exact_vehicle':
            endpoint = "/articles/list-articles"
            method   = "POST"
            payload  = {"typeId": "1", "langId": "4", "vehicleId": kwargs.get('vehicle_id')}
            if kwargs.get('category_id'):
                payload["categoryId"] = kwargs.get('category_id')

        else:
            return {
                "status":  400,
                "error":   "Bad Request",
                "message": f"Invalid search_type: {search_type}",
            }

        _logger.info(f"Executing RapidAPI search — type: {search_type} | query: {query}")
        data = request.env['tecdoc.api.abstract']._make_rapidapi_request(endpoint, method=method, payload=payload, params=params)

        if isinstance(data, dict) and "error" in data:
            err_msg = data.get("message", data.get("error", "Unknown error"))
            if data.get("error") == "quota_exceeded":
                return {
                    "status":  429,
                    "error":   "Monthly quota exceeded",
                    "message": err_msg,
                    "data":    [],
                }
            if data.get("error") == "rate_limit":
                return {"status": 429, "error": "Too Many Requests", "message": err_msg, "data": []}
            return {"status": 500, "error": "API Request Failed", "message": err_msg, "data": []}

        articles = data.get('articles', data) if isinstance(data, dict) else data
        if not isinstance(articles, list):
            articles = []

        if search_type == 'vin':
            return self._handle_vin_response(data, query)

        if search_type == 'oem_number':
            articles = self._filter_oem_articles(articles, query, data)
            # cap at 50 to avoid timeouts on popular numbers
            articles = articles[:50]

        vehicle_data = None
        if search_type == 'exact_vehicle':
            vehicle_data = {}
            if kwargs.get('vehicle_name'):
                vehicle_data['carName'] = kwargs.get('vehicle_name')
            if kwargs.get('vehicle_id'):
                vehicle_data['vehicleId'] = str(kwargs.get('vehicle_id'))

        compatible_vehicles_list = []

        if isinstance(articles, list):
            compatible_vehicles_list = self._run_enrichment_cascade(
                articles, search_type, query
            )
            oem_to_save = query if search_type == 'oem_number' else None
            request.env['tecdoc.part'].sudo().api_save_parts_from_data(
                articles,
                vehicle_data=vehicle_data,
                oem_number=oem_to_save,
                compatible_vehicles=compatible_vehicles_list or None,
            )

        return {
            "status":               200,
            "data":                 articles if articles else [],
            "compatible_vehicles":  compatible_vehicles_list,
            "cached":               False,
        }

    def _handle_vin_response(self, data, vin):
        inner = data.get('data', {}) if isinstance(data, dict) else {}

        # secondary decoder call for richer specs
        decoder_data = {}
        try:
            dec = request.env['tecdoc.api.abstract']._make_rapidapi_request(f"/vin/decoder-v2/{vin}", method="GET")
            if isinstance(dec, dict) and 'error' not in dec:
                decoder_data = dec
        except Exception as exc:
            _logger.warning(f"VIN decoder-v2 failed: {exc}")

        self._save_vin_vehicle(inner, decoder_data, vin)

        return {"status": 200, "data": inner, "decoder": decoder_data, "cached": False}

    def _save_vin_vehicle(self, inner, decoder_data, vin):
        matching_vehicles = inner.get('matchingVehicles', {})
        if isinstance(matching_vehicles, dict):
            mv_list = matching_vehicles.get('array', [])
        elif isinstance(matching_vehicles, list):
            mv_list = matching_vehicles
        else:
            mv_list = []

        if not mv_list and not decoder_data:
            return

        Vehicle  = request.env['tecdoc.vehicle'].sudo()
        existing = Vehicle.search([('vin', '=', vin)], limit=1)
        if existing:
            return

        first_v  = mv_list[0] if mv_list and isinstance(mv_list[0], dict) else {}
        v_id_str = str(first_v.get('vehicleId', ''))

        v_model = decoder_data.get('model', '')
        if not v_model:
            match_models = inner.get('matchingModels')
            if isinstance(match_models, dict):
                models_arr = match_models.get('array')
                if isinstance(models_arr, list) and models_arr:
                    v_model = models_arr[0].get('modelName', '')

        v_brand = decoder_data.get('make', '')
        if not v_brand and first_v.get('carName'):
            v_brand = first_v['carName'].split()[0]

        v_type = decoder_data.get('trim', '') or first_v.get('carName', '')

        Vehicle.create({
            'vin':           vin,
            'vehicle_id':    v_id_str,
            'brand':         v_brand,
            'vehicle_model': v_model,
            'make_date':     decoder_data.get('year', decoder_data.get('model_year', '')),
            'type':          v_type,
        })

    @staticmethod
    def _filter_oem_articles(articles, query, raw_data):
        # keep only articles that actually reference the queried oem number
        if not isinstance(articles, list) or not query:
            return articles

        q_norm    = query.strip().upper().replace(' ', '').replace('-', '')
        filtered  = []
        seen_ids  = set()

        for art in articles:
            if not isinstance(art, dict):
                continue
            art_id = art.get('articleId') or art.get('articleNo', '')
            if art_id in seen_ids:
                continue

            oem_refs = (art.get('oemNumbers')
                        or art.get('oeNumbers')
                        or art.get('crossReferences')
                        or [])
            if isinstance(oem_refs, list):
                matched = any(
                    q_norm in str(
                        ref.get('oemNumber') or ref.get('articleNo') or ref.get('number') or ''
                    ).strip().upper().replace(' ', '').replace('-', '')
                    for ref in oem_refs if isinstance(ref, dict)
                )
            else:
                matched = False

            if not oem_refs or matched:
                filtered.append(art)
                seen_ids.add(art_id)

        if filtered:
            total = len(raw_data.get('articles', articles) if isinstance(raw_data, dict) else articles)
            _logger.info(f"OEM filter: kept {len(filtered)}/{total} articles for OEM# {query}")
            return filtered

        return articles

    def _run_enrichment_cascade(self, articles, search_type, query):
        # fetch alternatives and compatible vehicles for the top 2 articles
        compatible_vehicles = []

        if search_type in ('oem_number', 'part_number', 'engine_code', 'alternatives') and query:
            compatible_vehicles = self._fetch_compatible_vehicles(query)

        _logger.info(f"Starting enrichment cascade on top 2 articles for query: {query}")

        for art in articles[:2]:
            if not isinstance(art, dict):
                continue

            art_id = str(art.get('articleId', ''))
            art_no = art.get('articleNo') or art.get('articleSearchNo')

            if art_id:
                try:
                    alt_data = request.env['tecdoc.api.abstract']._make_rapidapi_request(
                        f"/artlookup/select-article-cross-references/article-id/{art_id}/lang-id/4",
                        method="GET",
                    )
                    cross_refs = []
                    if isinstance(alt_data, dict) and 'articles' in alt_data:
                        for alt_art in alt_data['articles']:
                            oem_no = (alt_art.get('oemNumber')
                                      or alt_art.get('articleNo')
                                      or alt_art.get('number'))
                            brand  = alt_art.get('brandName') or alt_art.get('mfrName') or alt_art.get('supplierName') or alt_art.get('manufacturerName')
                            if oem_no:
                                cross_refs.append({'oemNumber': oem_no, 'brandName': brand})
                    if cross_refs:
                        art['enriched_cross_refs'] = cross_refs
                        _logger.info(f"Cascade: {len(cross_refs)} alternatives for article {art_id}")
                except Exception as exc:
                    _logger.warning(f"Cascade: failed alternatives for {art_id}: {exc}")

                try:
                    media_data = request.env['tecdoc.api.abstract']._make_rapidapi_request(
                        "/articles/article-all-media-info",
                        method="GET",
                        params={"articleId": art_id, "langId": "4"}
                    )
                    if isinstance(media_data, list):
                        images = []
                        for media in media_data:
                            if media.get('articleMediaType') != 'PDF' and media.get('s3image'):
                                images.append({'url': media['s3image']})
                        if images:
                            art['images'] = images
                            _logger.info(f"Cascade: fetched {len(images)} images for article {art_id}")
                except Exception as exc:
                    _logger.warning(f"Cascade: failed media fetch for {art_id}: {exc}")

            if art_no and art_no != query:
                try:
                    extra = self._fetch_compatible_vehicles(art_no)
                    compatible_vehicles.extend(extra)
                except Exception as exc:
                    _logger.warning(f"Cascade: compatible vehicles failed for {art_no}: {exc}")

        return compatible_vehicles
