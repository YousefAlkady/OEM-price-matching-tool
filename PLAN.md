# Auto Parts Automation Platform: Execution Plan

Source material: `reports/Auto parts automation platform.md` (deep research) and the code review in the 2026-10-09 session.
Business model: pay-per-call TecDoc via a RapidAPI wrapper, enrich only the client's stocked SKUs once, cache, and sell packages on top.

## 0. Decisions needed before Phase 1 (blockers)

| # | Question | Why it matters | Default if unanswered |
|---|---|---|---|
| D1 | Odoo version (17 / 18 / 19)? | `detailed_type`, `hs_code`, API options differ | Assume 17, isolate version-specific code in one compat helper |
| D2 | RapidAPI plan: price per call, quota, per-second limit | Margin math, throttle settings | Make throttle and budget configurable |
| D3 | Written answer from the wrapper author: may results be stored persistently for the client's own SKUs? | Legal basis of the whole caching model | Store only for client SKUs, no bulk export |
| D4 | Hosting: Odoo.sh, self-hosted VPS, or client premises? | Odoo.sh forbids pgvector and Docker sidecars | Assume a VPS with Docker |
| D5 | First pilot client and the format of their stock list | Drives the import design | Excel with a part-number column |

### Answers received (2026-10-09)
- **D1:** Odoo 18 now, 19 soon. Code must avoid `detailed_type` (removed in 18; use `type='consu'` + `is_storable`) and keep version-specific code in one compat helper so 19 is a small change.
- **D2:** RapidAPI "Auto Parts Catalog" plans (hard limits, no overage): Basic $0 = 100 req/mo, 5 req/s; Pro $39 = 20,000 req/mo, 15 req/s; Ultra $69 = 100,000 req/mo, 20 req/s; Mega $299 = 1,000,000 req/mo, 25 req/s. Bandwidth: 10 GB/mo included, then $0.001 per MB.
  - Cost per call: Pro about $0.00195, Ultra about $0.00069, Mega about $0.0003.
  - Consequence: the current 0.5 s sleep is unnecessary at 15 req/s; the real constraint is the monthly hard limit. Basic's 100 calls means development must use recorded fixtures.
  - Consequence: one client with 5,000 SKUs fits Pro at 3 calls/SKU (15,000 calls) but needs Ultra at the current ~10 calls/SKU.
  - Decision: each client holds their own RapidAPI subscription and key (they pay the plan; we sell the platform). Reselling shared API access risks breaching RapidAPI's acceptable-use policy.
- **D3:** answered 2026-10-10: the API owner stated that storing results is allowed. Keep a copy of that written statement with the client contract. Cache TTL (default 30 days) is now only about data freshness, not licensing.
- **D4:** client hosts Odoo on their own server; we develop locally and ship. Deliverable = installable module + Docker Compose for optional n8n + install guide. No pgvector assumptions in the core module.
- **D5:** open. Desired part record ("part passport"): client internal reference mapped to international OEM number, plus images, compatible vehicles and alternative parts with their info. Open question: does the client's stock list contain OEM or brand numbers, or only internal codes and names? This decides how hard the mapping step is.

## 1. Target architecture (end state)

```
 Email / FTP / WhatsApp / Excel
            |
         [ n8n ]  (one instance per client)  <- orchestration only, no business rules
            | HTTPS + token
 [ Odoo module "oem_connect" ]  <- models, security, review UI, dashboards, queue_job tasks
            |
 [ Provider adapter layer ]  -> RapidAPI TecDoc (primary) -> second listing (fallback)
            |
 [ Cache + budget + audit ]  (tecdoc.api.log, per-client call budget)
            |
 [ Matcher service (phase 5, optional external FastAPI + pgvector) ]
```

Rule: **business logic lives in Odoo (or the matcher service), never inside n8n.** n8n moves files and messages and calls stable endpoints. This keeps flows replaceable and the product sellable.

## 2. Phases

Each phase ends with a working, committed, reviewable state. Each is one or two Claude sessions.

### Phase 1: Make it run and stop the bleeding (small)
Fixes: review items 1, 2, 8, 9, 10, 13, 14, 16, 18, 19.
- Fix `catalog_controller.py` imports; fix `OEM-Price-matching-tool.py:21` syntax error.
- Error responses always carry `error` and `message`; guard `.get` on list responses.
- Separate 429 per-second bursts from quota exhaustion; retry with backoff on bursts.
- API key field masked (`password=True`).
- Repo: remove `.pyc`, replace `.gitignore`, delete `fix.py`/`fix2.py`, fix README, add a manifest version/license.
- Add `CLAUDE.md` (via the `init` skill) describing the module, conventions, and this plan.
- Exit check: module installs on a clean DB; dropdown endpoints respond.

### Phase 2: Cost control and honest data layer (medium)
Fixes: review items 3, 4, 5, 6, 7, 10, 14, 15, 17.
- `tecdoc.api.log` written by the single request wrapper: endpoint, params hash, status, cost units, company.
- Cache by `(provider, endpoint, params_hash)` with a configurable TTL; replace the broken `oem_number = query` lookup with a normalized-key lookup (new indexed `oem_key` field + cross-reference table).
- Enrichment reduced to about 3 calls per SKU (article, cross-refs, fitment on demand); the rest lazy.
- Search becomes read-only; "Add to catalog" button creates the product. Remove auto-creation of accessory and cross-reference products.
- Per-company monthly call budget plus a hard stop and a clear message.
- Security groups: Viewer, Operator, Admin; record rules; unique constraint `(provider, article_id)`.
- Move `time.sleep` out of the request path (token-bucket throttle).
- Exit check: one OEM search costs at most 3 logged calls; second identical search costs 0.

### Phase 3: Inventory-first enrichment + first n8n flow (medium, **n8n enters here**)
- New model `oem.enrichment.job` (sku, status: pending / enriched / failed / needs_review, attempts, cost).
- Importer for `.xlsx` and CSV (encoding detection, header mapping, no silent truncation, row-level error report). Processing runs as queued jobs (OCA `queue_job`) in batches.
- Authenticated endpoint set `/api/v1/` in the module: `POST /stock/import`, `GET /jobs/<id>`, `POST /price-lists/ingest`. Token-based, per-client.
- Dashboard v1: enrichment status board, API spend, data quality %.
- **n8n, flow 1: stock-file auto-sync** (see section 4 for the walkthrough).
- Exit check: dropping an Excel file in the mailbox updates stock and queues new SKUs for enrichment, with a diff report and a rollback.

### Phase 3b: OEM inference engine (core selling point, medium-large)
Goal: for stocked parts that have only an internal reference (and a name), decide the OEM number(s) and map them, with proof and a safety net.

Principle: **the AI never invents an OEM number.** Candidates come only from TecDoc (or the client's own mapped data). The AI chooses among them or says "none". Code validates that the answer is one of the candidates.

Pipeline (cheap stages first, stop as soon as a stage is confident):
1. **Parse and normalize** the internal reference and the Arabic/English name: strip separators, detect an embedded brand or article number, extract vehicle make/model/year, part type, side/position, size. A shared Arabic-to-TecDoc product-group dictionary is built once and reused for every client.
2. **Direct hit:** if the internal reference looks like a manufacturer article number, search TecDoc by article number (1 call). The result already carries its OEM numbers.
3. **Vehicle-first lookup:** from the vehicle and part type in the name, walk make, model, engine, category, then list articles (shared catalog lookups are cached once for all SKUs).
4. **Known mappings:** the client's already-mapped parts, previously human-confirmed mappings, and competitor/supplier lists that carry OEM codes (the existing Nour-style files).
5. **Rank candidates:** deterministic scores (vehicle fit, category, brand, size) plus a cheap-model judgment over the candidate list with a structured answer: chosen index, confidence, reason, or none.
6. **Decide by confidence band:**
   - High: mapped automatically, flagged "AI-mapped", fully reversible.
   - Medium: goes to the review queue with the top candidates and their fitment shown.
   - Low: left unmapped with suggestions.
7. **Learn:** every human confirmation becomes an authoritative mapping that is never re-fetched or re-decided.

Data rules:
- One part maps to many OEM numbers (different car makers, superseded numbers); exactly one is flagged primary for the client's main vehicle makes.
- Every mapping stores provenance: method, candidates considered, score, model, date, reviewer.

Benchmark before trusting it: take the client's parts that **already have OEM numbers**, hide the OEM, and measure how often the engine recovers it. Set the auto-map threshold from that result so wrong automatic mappings stay rare.

Cost: roughly 3 to 8 TecDoc calls plus one small model call per unmapped SKU, estimated at one to two cents per SKU on the Pro plan.

### Phase 4: Pricing intelligence (medium)
- Competitor price list ingestion (Excel first), stored versioned.
- Matcher v1 inside Odoo: normalize codes, exact match on OEM/article keys, then RapidFuzz name match, then a review queue (`oem.match.candidate` with score, method, decision, reviewer). Threshold tuned against a labeled sample from the existing `Bdeel_List.xlsx` / `Nour.xlsx`.
- Dashboards: price gap, margin watch, missed demand (log searches that found nothing in stock).
- **n8n, flow 2: weekly competitor list pull and supplier price-list email ingestion** with LLM extraction into a staging table (validated against a JSON schema, human approval before publishing).

### Phase 5: Quality upgrades and selling features (medium-large, modular)
Build in this order, each as an optional add-on module:
1. Fitment-aware quoting (VIN or model, in-stock parts, alternatives on stockout).
2. Landed cost and currency watch.
3. Matcher v2 (pgvector + multilingual embeddings + LLM rerank) as an external service, only if v1 accuracy on the labeled set is insufficient.
4. **n8n, flow 3: WhatsApp quote bot** (part number or VIN in, availability/price/alternatives out; no prices sent without a salesperson approval rule at first).
5. Export documents (commercial invoice, packing list, HS-code suggestions with broker approval).
6. B2B portal.

### Phase 6: Productize (parallel with phases 4 to 5)
- Tiers: Core / Pricing / Automation / Export, enforced by a feature-flag model in the module.
- Install and onboarding script, demo dataset, backup and monitoring checklist (Sentry, uptime check).
- Sales assets: pilot offer, ROI sheet, deck.
- Pilot with 1 to 3 clients before pricing is fixed.

## 3. Test strategy (cheap and early)
- Odoo `TransactionCase` tests for: normalization, cache hit and miss, budget cap, importer, matcher decisions. Mock all RapidAPI calls with recorded fixtures so tests cost zero API calls.
- One recorded fixture per endpoint (capture once with a real key, then replay).
- Labeled match set (about 200 pairs from the existing Excel files) as the matcher benchmark.

## 4. n8n: when it enters, and the step-by-step setup

**It enters in Phase 3, not earlier**, because n8n must call stable endpoints. Wiring it up before Phase 2 would automate a leaky, expensive process.

**Licensing:** run one n8n instance per client (self-hosted, internal use); do not host several customers on one instance without an Enterprise or Embed licence. Re-check n8n's current licence page before selling. Activepieces (MIT) is the fallback.

### Walkthrough (done together during Phase 3)
1. **Install:** Docker Compose on the client VPS: n8n + Postgres (not SQLite) + a reverse proxy with HTTPS. Set `N8N_ENCRYPTION_KEY`, basic auth or SSO, and persistent volumes. Queue mode (Redis + workers) only when volume demands it.
2. **Odoo side:** create an integration user with a restricted group, generate an API token, expose `/api/v1/*` (Phase 3). Do not rely on Odoo's XML-RPC/JSON-RPC, which are being phased out; the module's own endpoints stay stable across Odoo versions.
3. **Credentials in n8n:** store the token as an n8n credential (header auth), never inside workflow nodes.
4. **Flow 1, stock sync:**
   - Trigger: IMAP email (attachment) or FTP/folder watch.
   - Node: extract file, convert to rows, basic checks (required columns, row count sanity).
   - Node: HTTP Request to `POST /api/v1/stock/import` with `dry_run=true`; read the diff summary.
   - Branch: if changes exceed the threshold, send a Telegram/email approval request and wait; otherwise call the endpoint with `dry_run=false`.
   - Node: error workflow that notifies on any failure; log every run.
5. **Test with a sample file and a dry run** before connecting the real mailbox.
6. **Export** the workflow JSON into the repo under `n8n/flows/` so it is versioned and reusable for the next client.
7. **Flows 2 and 3** follow the same pattern: trigger, light prep, call an Odoo endpoint, human approval on anything risky.
8. LLM steps (price-list extraction, WhatsApp understanding) use structured outputs validated against a schema; low-confidence rows go to the Odoo review queue, never straight into prices.

## 5. Token-efficient execution with Claude

**Principles**
- One phase = one session. Start each with `PLAN.md` + `CLAUDE.md` only; finish with a commit and `/clear`. Never carry a whole phase of chat into the next.
- Read narrowly: use `Grep` and line ranges instead of whole files. Skip `tecdoc.js` (25 KB) unless the task touches the UI; never read `.pyc`.
- Batch independent tool calls in one turn; run tests in the terminal and show only failures.
- Pin the target: a phase's exit check is written down before coding, so there is no open-ended exploration.

**Which model and effort for what**
- Haiku-class or low effort: mechanical edits, renames, fixtures, README, repo cleanup.
- Sonnet-class (default): feature work, importer, controllers, tests.
- Highest effort only for: the cache/budget design, the matcher design, and the security model. Think once, then implement at low effort.

**Skills and tools to use**
| Need | Use |
|---|---|
| Project memory and conventions | `init` (CLAUDE.md), memory files for decisions D1 to D5 |
| Excel inputs/outputs and test data | `anthropic-skills:xlsx` |
| Before every merge | `code-review`, then `security-review` after phases 2 and 3 |
| Tidy after features | `simplify` |
| LLM extraction and matching code | `claude-api` (model ids, structured output, caching, batch pricing) |
| Run and verify the module | `run` |
| Fewer approval prompts | `fewer-permission-prompts` after the first session |
| Recurring checks (API spend alert, weekly competitor pull) | `schedule` / `loop` |
| Reusable client onboarding | `skill-creator` to package "onboard a new client" as a project skill |
| Sales deck / proposal / ROI doc | `pptx` / `docx` skills, or a published Artifact |
| Parallel independent work | Subagents in worktrees (e.g., tests + docs while features are built) |
| Broad code search | `Explore` agent instead of many reads |

**Cost-saving habits in the product itself** (these also protect your margin)
- Record API fixtures once; tests never hit RapidAPI.
- Use the Batch API and prompt caching for bulk LLM jobs; use the cheapest model that passes the labeled benchmark.
- Cache LLM extractions by file hash so a re-sent file costs nothing.

## 6. Risks and mitigations
- Wrapper licence uncertainty -> D3 written answer, provider adapter, no bulk export.
- Vendor outage or quota -> fallback provider, circuit breaker, budget alerts.
- Wrong automatic matches -> review queue, thresholds tuned on labeled data, human approval on prices.
- Odoo version drift -> compat helper, own stable API.
- Scope creep -> phases 5 and 6 items ship only after a pilot client asks for them.
- AI numbers in this plan (pricing, ROI) are estimates until a pilot confirms them.

## 7. Next action
Answer D1 to D5, then start Phase 1 (about one short session).
