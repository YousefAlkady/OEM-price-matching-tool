"""Record one real response per Auto Parts Catalog endpoint into tests/fixtures/.

Usage: put RAPIDAPI_KEY=... in a file named .env at the repo root (gitignored), then
    python tools/record_fixtures.py
Costs about 12 API calls. Existing fixtures are kept (delete a file to re-record).
"""
import json
import pathlib
import sys
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)
HOST = "auto-parts-catalog.p.rapidapi.com"

env = {}
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
HEAD = {"x-rapidapi-key": env["RAPIDAPI_KEY"], "x-rapidapi-host": HOST}
calls = 0


def call(name, path, method="GET", params=None, data=None):
    global calls
    f = OUT / f"{name}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    calls += 1
    r = (requests.post(f"https://{HOST}{path}", data=data, headers=HEAD, timeout=30) if method == "POST"
         else requests.get(f"https://{HOST}{path}", params=params, headers=HEAD, timeout=30))
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text
    f.write_text(json.dumps({"status": r.status_code, "ratelimit_remaining": r.headers.get("x-ratelimit-requests-remaining"),
                             "path": path, "params": params, "body": body}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{name}: HTTP {r.status_code}, remaining={r.headers.get('x-ratelimit-requests-remaining')}")
    return {"body": body}


def first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return None
    return d


mf = call("manufacturers", "/manufacturers/list/type-id/1")
# Sample OEM numbers taken from the client's product export (Hyundai / Toyota / Nissan)
for label, oem in (("hyundai", "86551-AA000"), ("toyota_oem", "04465-0K090")):
    s = call(f"search_oem_{label}", "/artlookup/search-articles-by-article-no",
             params={"langId": "4", "articleNo": oem, "articleType": "OENumber"})
    arts = s["body"].get("articles") if isinstance(s["body"], dict) else None
    if arts and label == "hyundai":
        aid = str(arts[0].get("articleId"))
        call("cross_references", f"/artlookup/select-article-cross-references/article-id/{aid}/lang-id/4")
        call("media", "/articles/article-all-media-info", params={"articleId": aid, "langId": "4"})
        call("specs", "/articles/get-article-specifications-list-of-articles-ids", "POST", data={"langId": 4, "articleIds": [int(aid)]})
        call("accessories", f"/articles/selecting-list-of-accessories-list-for-the-article/article-id/{aid}/lang-id/4/country-filter-id/63")
call("compatible_cars_hyundai", "/articles/get-compatible-cars-by-oem-no/type-id/1",
     params={"langId": "4", "countryFilterId": "63", "articleOemNo": "86551-AA000"})
call("compatible_cars_hyundai_egypt_filter_test", "/articles/get-compatible-cars-by-oem-no/type-id/1",
     params={"langId": "4", "articleOemNo": "86551-AA000"})
print(f"done, {calls} API calls made")
