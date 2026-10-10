# Auto Parts Catalog API: findings from recorded responses (2026-10-10)

Recorded with `tools/record_fixtures.py` (about 17 calls, free plan). Fixtures live in `tests/fixtures/` (gitignored). Samples are OEM numbers from the client's product export.

## Coverage on the client's sample
| OEM searched | Part | Result |
|---|---|---|
| 04465-0K090 (Toyota) | brake pad set | 257 articles |
| 58101-3XA10 (Hyundai) | brake pads | 191 articles |
| 86551-AA000 (Hyundai) | front bumper bracket | **none** |
| A21-3505010AC (Chery) | brake master cylinder | **none** |
| 1064002393 (Geely) | brake master cylinder | **none** |
| 16546-4BA0A (Nissan, guessed number) | air filter | none (number may be wrong) |

Reading: TecDoc covers wear and service parts of mainstream brands well. Body/bumper parts and Chinese-brand parts looked absent in these tests. This is a small sample, not a coverage study. The inference engine must treat "no catalog data" as a normal outcome and fall back to client data.

## Behaviour that changes the design
1. **An OEM search returns every aftermarket article that cross-references that OEM** (hundreds), not one match. The OEM number is the key; the articles are alternatives. Showing or storing all of them as products is wrong. Keep a bounded, ranked set.
2. **Articles carry no OEM list.** Fields are only `articleSearchNo, articleId, articleNo, articleProductName, supplierName, supplierId, articleMediaType, articleMediaFileName, s3image`. The current `_consolidate_oems` looks for `oemNumbers/oeNumbers/crossReferences`, which never exist, so stored OEM numbers are only the query itself.
3. **Fitment is huge:** one call for one OEM returned 229 articles and 14,792 compatible cars. The current code saves every one as a vehicle record. Fitment must be filtered to the client's makes/models (known from their product category) and stored compactly.
4. **`countryFilterId` made no difference** (63 and no filter gave identical results). It is not a working market filter for this endpoint; do not rely on it.
5. **Field-name bug:** fitment cars use `constructionIntervalStart/End`; the code reads `yearOfConstrFrom/To`, so the production date range is always empty.
6. **Specifications and accessories were empty** for the tested article, so weight, volume, HS code and barcode from specs are often missing. HS code must come from elsewhere (client data or suggestion with approval).
7. **Cross-reference endpoint** returns 247 entries (articleId, articleNo, supplierName...). Same bounded-set rule.
8. **Manufacturers list** is under key `manufacturers` (698 entries), not `data`; check the JS expects that.
9. **Media** returns a list with `s3image` URLs (6 for one article).

## Plan impact
- Task 2.5/2.6: store a bounded alternatives set (for example top N by supplier tier) and never auto-create products from them.
- Task 2.10: drop the `countryFilterId` assumption; fix `constructionIntervalStart/End`.
- New task 2.11: fitment filtering by client makes/models and compact storage.
- Phase 3b: add "no catalog data" outcome; for Hyundai-style references the OEM is usually already the internal reference, so the engine's value is verification plus enrichment, not discovery.
