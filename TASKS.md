# TASKS: Odoo OEM Connect

Source: `PLAN.md`. Task size: XS 1 file, S 1-2, M 3-5 (anything bigger is split). One phase = one session; end each phase with a checkpoint, a commit on a branch, and owner review. Tests never call the real API (recorded fixtures in `tests/fixtures/`, gitignored).

Verification command for all tasks unless stated:
`C:\Odoo\devenv\venv\Scripts\python.exe -m odoo ... -d oem_test -i rapidapi_bdeel --test-tags /rapidapi_bdeel --stop-after-init` (exact command fixed in task 0.2).

## Phase 0: Dev environment (do first)
- [x] 0.0 Phase 1 fixes merged to local `main`. (Push blocked: remote repo not found.)
- [x] 0.1 Record API fixtures (done, 17 calls; 83/100 free calls left). Findings in `docs/api-findings.md`.
- [x] 0.2 Odoo 18 test harness: venv deps installed, throwaway DB, `odoo.conf` in `C:\Odoo\devenv`, module symlinked as `rapidapi_bdeel`. AC: module installs with zero errors/warnings; one smoke test passes. Dep: Postgres login. [S]
- [x] 0.3 Fix any install errors found by 0.2 (view xml, field names, deps). AC: clean install + upgrade. Dep 0.2. [S-M]
### Checkpoint 0: module installs on Odoo 18, fixtures exist, findings written into `docs/api-findings.md`.

## Phase 2: Cost control and honest data layer
- [x] 2.1 API log: wrapper writes `tecdoc.api.log` (endpoint, params hash, status, duration, company). AC: every call logged incl. failures; test with mocked `requests`. Files: rapidapi_abstract.py, tecdoc_api_log.py + view, tests. Dep 0.3. [M]
- [x] 2.2 Response cache: model `tecdoc.api.cache` keyed (endpoint, params_hash), TTL setting (default 30 days, configurable), used by the wrapper. AC: second identical call = 0 HTTP calls; expired entry refetched; test proves it. Dep 2.1. [M]
- [x] 2.3 Normalized lookup keys: `oem_key` (indexed, normalized) on part and cross-reference; replace broken `oem_number = query` cache check. AC: search "86551-AA000", "86551AA000", "86551 aa000" hit the same cached part. Files: tecdoc_part.py, tecdoc_part_cross_reference.py, db_service.py, tests. Dep 2.2. [M]
- [x] 2.4 Call budget: per-company monthly cap + counter; hard stop with a clear message; warning at 80%. AC: cap reached -> no HTTP call, message returned; counter resets monthly. Files: settings, wrapper, log. Dep 2.1. [M]
- [x] 2.5 Lean enrichment: article + cross-refs mandatory, fitment/images/accessories lazy and cached; remove double `action_create_odoo_product` and hard-coded `needs_images`. AC: enriching one SKU = at most 3 logged calls on fixtures. Dep 2.2. [M]
- [x] 2.6 Read-only search: search no longer creates products, accessories or cross-ref products; explicit "Add to catalog" action. AC: after a search `product.template` count unchanged; button creates exactly one product. Dep 2.5. [M]
- [x] 2.7 Dedupe + unique constraint `(article_id)`/`(oem_key)` with a migration that merges existing duplicates. AC: install on DB with seeded duplicates merges them. Dep 2.3. [S]
- [x] 2.8 Security: groups Viewer/Operator/Admin, rewrite `ir.model.access.csv`, record rules, controllers stop using blanket `sudo()`. AC: Viewer cannot write/delete (test per model); Operator can search/enrich; Admin sees settings and budget. [M]
- [x] 2.9 Replace session-based rate limit with per-user DB-backed limit. AC: new session cannot bypass. Dep 2.1. [S]
- [x] 2.10 Fix category field, remove the `countryFilterId` assumption (no effect per findings), read `constructionIntervalStart/End` for vehicle dates, `langId` as setting. AC: category differs from name; vehicle date range filled on fixtures. Dep 0.1. [S]
- [x] 2.11 Bound the data: keep a ranked top-N alternatives set (not hundreds), and filter fitment to the client's makes/models, stored compactly (fixture shows 14,792 cars for one OEM). AC: enriching the Toyota fixture stores <= N alternatives and only matching vehicles. See `docs/api-findings.md`. Dep 2.5. [M]
### Checkpoint 2 (done 2026-10-10: 51 tests pass, code review + ponytail review fixed, migration check script): one OEM search on fixtures = at most 3 logged calls, repeat = 0; budget stops calls; security tests pass; code-review + security-review run; owner review; merge.

## Phase 3: Inventory-first enrichment and first n8n flow
- [ ] 3.1 Stock import parser: `.xlsx`/CSV, encoding detection, header mapping, skips blank rows (the sample export has alternating blank rows), per-row error report, no 100-row cap. AC: parses `Product (product.template).xlsx` to 83 products. Files: new `oem.stock.import` model/wizard + tests. [M]
- [ ] 3.2 Enrichment job model `oem.enrichment.job` (sku, status pending/enriched/failed/needs_review, attempts, cost, error) + `queue_job` dependency decision (OCA queue_job vs ir.cron batch; decide in this task). AC: jobs created per new SKU, retried with backoff, idempotent. Dep 2.5. [M]
- [ ] 3.3 Reference cleaner: strip `L `/`R ` side prefixes, separators; keep side as an attribute (L/R remain separate parts). AC: `L 86613-F2AA0` and `R86614-3X700` -> clean key + side. Tests from sample. Dep 3.1. [S]
- [ ] 3.4 Diff engine: dry-run diff of incoming stock vs current, threshold guard (e.g. >30% change needs approval), apply, snapshot, rollback. AC: dry run changes nothing; rollback restores. Dep 3.1. [M]
- [ ] 3.5 Token-authenticated API `/api/v1/stock/import`, `/api/v1/jobs/<id>`: per-client token model, constant-time compare, rate limit, audit. AC: no token = 401; wrong scope = 403; tests. Dep 2.8, 3.4. [M]
- [ ] 3.6 Dashboard v1: enrichment status board, API spend, data-quality percent. AC: counts match DB in tests. Dep 3.2. [M]
- [ ] 3.7 n8n setup + flow 1 (stock sync): docker-compose, flow JSON in `n8n/flows/`, runbook `docs/n8n-setup.md`. Walk the owner through it step by step. AC: sample file by email/folder -> dry run -> approve -> applied; error notification works. Dep 3.5. [M]
### Checkpoint 3: drop an Excel file, stock updates, new SKUs queued, diff + rollback work; security-review; merge.

## Phase 3b: OEM inference engine
- [ ] 3b.1 Mapping data model: `oem.mapping` (part, oem number, is_primary, method, score, status auto/confirmed/rejected, provenance JSON, reviewer). AC: many OEMs per part, one primary. [M]
- [ ] 3b.2 Name parser: extract make/model/year/part type/side from English names (and Arabic category) into structured fields; Arabic<->TecDoc product-group dictionary (data file). AC: parses >=90% of sample names with correct make+model (measured, reported). Dep 3.3. [M]
- [ ] 3b.3 Stage A direct hit: internal reference as article/OEM number -> TecDoc search -> mapping. AC: sample Hyundai/Toyota rows map on fixtures. Dep 2.5, 3b.1. [M]
- [ ] 3b.4 Stage B vehicle-first lookup with cached make/model/category tree. AC: identical vehicle lookups are served from cache. Dep 3b.2. [M]
- [ ] 3b.5 Stage C known mappings: reuse confirmed mappings and supplier/competitor lists carrying OEMs. Dep 3b.1. [S]
- [ ] 3b.6 Candidate ranking + LLM chooser via the `claude-api` skill: structured output (chosen index/none, confidence, reason); code rejects any answer not in the candidate list. AC: unit tests with fake LLM prove an invented OEM is rejected. Dep 3b.3-3b.5. [M]
- [ ] 3b.7 Confidence bands + review queue UI (accept/reject/pick another; confirmed = permanent). AC: high auto-maps flagged "AI-mapped" and reversible; medium appears in queue. Dep 3b.6. [M]
- [ ] 3b.8 Benchmark tool: hide known OEMs, measure recovery, set thresholds; report in `docs/benchmark.md`. Needs client rows with known OEMs. Dep 3b.6. [S]
### Checkpoint 3b: measured accuracy reported; wrong auto-maps within an agreed tolerance; owner signs off thresholds.

## Phase 4: Pricing intelligence
- [ ] 4.1 Versioned competitor/supplier price-list model + Excel ingest. Dep 3.1. [M]
- [ ] 4.2 Matcher v1: key match -> RapidFuzz name match -> review queue; reuse 3b mapping data; tuned on a labeled set (about 200 pairs from `Bdeel_List.xlsx`/`Nour.xlsx`). AC: accuracy reported vs old script. Dep 4.1, 3b.1. [M]
- [ ] 4.3 Dashboards: price gap, margin watch, missed demand (log searches with no stock hit). Dep 4.2. [M]
- [ ] 4.4 n8n flow 2: supplier price-list email ingestion with LLM extraction into a staging table, schema-validated, human approval before publish. Dep 4.1, 3.7. [M]
### Checkpoint 4: price-gap dashboard on real client data; owner review.

## Phase 5: Selling features (each an optional add-on; ship after a pilot asks)
- [ ] 5.1 Fitment-aware quoting (VIN/model -> in-stock parts + alternatives on stockout). [M]
- [ ] 5.2 Landed cost + currency watch. [M]
- [ ] 5.3 n8n flow 3: WhatsApp quote bot (approval rule before prices go out). [M]
- [ ] 5.4 Export documents (invoice, packing list, HS-code suggestions with broker approval). [M]
- [ ] 5.5 Matcher v2 (pgvector + embeddings) only if 4.2/3b.8 accuracy is insufficient. [L, split when started]
- [ ] 5.6 B2B portal. [L, split when started]

## Phase 6: Productize
- [ ] 6.1 Feature flags per package tier (Core/Pricing/Automation/Export) enforced in the module. [M]
- [ ] 6.2 Install guide, backup/monitoring checklist, demo dataset. [S]
- [ ] 6.3 Package the "onboard a new client" runbook as a project skill (`skill-creator`). [S]
- [ ] 6.4 Pilot offer, ROI sheet, deck. [S]
### Checkpoint 6: pilot client live; prices set from measured costs.

## Parallelization
Parallel-safe: 3.6 with 3.7; 4.1 with 3b.x; docs and tests alongside features. Sequential: all schema changes, 2.x chain (2.1 -> 2.2 -> 2.3/2.5 -> 2.6), 3.4 -> 3.5 -> 3.7.

## Risks
| Risk | Impact | Mitigation |
|---|---|---|
| Chinese brands (Chery/BYD/Geely/JAC) weakly covered by TecDoc | High | Measure coverage in 0.1/3b.8; fall back to client data and supplier lists; flag as "no catalog data" instead of guessing |
| `countryFilterId=63` may be the wrong market | Med | Check against fixtures in 0.1 (task 2.10) |
| Wrapper storage terms | Low | Owner confirmed storage is allowed (2026-10-10); keep the written statement |
| Odoo 19 changes | Low | Keep version-specific code in one place; test on 19 when it ships |

## Open questions
- A sample of client rows with known OEM numbers, for task 3b.8.
