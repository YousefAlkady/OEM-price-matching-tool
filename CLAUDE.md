# Odoo OEM Connect (module name `rapidapi_bdeel`)

Odoo 18 module (19 soon). Maps a client's internal part references to OEM numbers, images, fitment and alternatives via the RapidAPI "Auto Parts Catalog" (TecDoc) API. Read `PLAN.md` first: it holds the phases, decisions and open questions. Current phase is noted at the top of its Section 2 progress list.

## Rules
- Odoo 18 API: no `detailed_type` (use `type='consu'` + `is_storable=True`). Keep version-specific code in one place; 19 deprecates `_sql_constraints`.
- Every RapidAPI call goes through `models/rapidapi_abstract.py::_make_rapidapi_request`. Errors are dicts with both `error` and `message`.
- The AI never invents OEM numbers: candidates come from TecDoc or client data; code validates the choice.
- Do not call the real API in tests (free plan = 100 calls/month). Use recorded fixtures.
- Business logic stays in Odoo; n8n only moves files/messages and calls `/api/v1/*` (Phase 3).
- No bulk export of TecDoc data; cache only for the client's own SKUs.

## Environment
- Odoo 18 source + venv: `C:\Odoo\Enerprise 18` (Python in `venv\Scripts`). Postgres data under `C:\Odoo\Community18\PostgreSQL`.
- Sample client data: `C:\Users\A\Downloads\Product (product.template).xlsx` (Odoo export; blank rows alternate; Internal Reference is often already the OEM number; OEM column empty).
- Work on branches; the owner reviews, then merges and pushes to `main`.

## Tests
`python -m py_compile` for syntax; Odoo tests via `odoo -d <db> -i rapidapi_bdeel --test-tags rapidapi_bdeel --stop-after-init`.
