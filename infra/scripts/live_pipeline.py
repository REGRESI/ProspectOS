"""Live acceptance M2–M4 against the local stack (development only, real public data).

1. ICP template "office_cleaning_ortenau" in the demo workspace.
2. OSM search around a place (default Offenburg, 30 km) over the CleanStar categories,
   up to 200 results, import of all non-duplicate companies.
3. Website/Impressum research batch (default 50 companies with website).
4. Ranking top 20 with reasons.
Prints counts only plus company names/URLs (public business data); writes the full JSON
report to the path given by REPORT (default: no file).

  uv run --env-file ../../.env python ../../infra/scripts/live_pipeline.py [place] [radius] [research_n]
"""

import json
import os
import sys
import time

import httpx

API = os.getenv("API_URL", "http://127.0.0.1:8000")
if os.getenv("APP_ENV", "development") != "development":
    sys.exit("development only")
place = sys.argv[1] if len(sys.argv) > 1 else "Offenburg"
radius = int(sys.argv[2]) if len(sys.argv) > 2 else 30
research_n = int(sys.argv[3]) if len(sys.argv) > 3 else 50
steps = os.getenv("STEPS", "discover,research,rank").split(",")

c = httpx.Client(base_url=API, timeout=180)
login = c.post(
    "/v1/auth/demo",
    json={"email": "demo@prospectos.local", "password": os.getenv("DEMO_PASSWORD") or "ProspectDemo!2026"},
)
login.raise_for_status()
c.headers["X-CSRF-Token"] = login.json()["csrf_token"]
ws = c.get("/v1/workspaces").json()["items"][0]["id"]
w = f"/v1/workspaces/{ws}"
report: dict = {"place": place, "radius_km": radius}


def wait(job_id, timeout=900):
    started = time.time()
    while time.time() - started < timeout:
        job = c.get(f"{w}/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "ambiguous", "dead", "cancelled"):
            return job
        time.sleep(3)
    return job


icp = c.post(f"{w}/icp-profiles/from-template", json={"template": "office_cleaning_ortenau"})
icp.raise_for_status()
industries = icp.json()["industries"]

if "discover" in steps:
    search = c.post(
        f"{w}/discovery/searches",
        json={
            "name": f"CleanStar {place} {radius} km",
            "filters": {
                "provider": "osm",
                "country": "germany",
                "city": place,
                "radius_km": radius,
                "industries": industries,
                "max_results": 200,
                "exclude_customers": True,
            },
        },
    )
    search.raise_for_status()
    queued = c.post(f"{w}/discovery/searches/{search.json()['id']}/run", json={"confirmed": True})
    print("discovery queued:", queued.status_code, queued.json().get("warnings"))
    queued.raise_for_status()
    job = wait(queued.json()["id"])
    print("discovery job:", job["status"], job.get("last_error") or "")
    if job["status"] != "succeeded":
        sys.exit(1)
    run_id = job["result"]["run_id"]
    rows, page = [], 1
    while True:
        r = c.get(f"{w}/discovery/runs/{run_id}/results", params={"page": page, "limit": 100}).json()
        rows += r["items"]
        if len(rows) >= r["total"] or not r["items"]:
            break
        page += 1
    keys = [x["key"] for x in rows if not x["imported"] and not x["duplicate_of"]]
    by_cat: dict[str, int] = {}
    for x in rows:
        by_cat[x.get("industry") or "?"] = by_cat.get(x.get("industry") or "?", 0) + 1
    print(f"results: {len(rows)} total, {sum(1 for x in rows if x['duplicate_of'])} probable duplicates")
    print("by category:", json.dumps(by_cat, ensure_ascii=False))
    imported = {"companies": 0, "linked_duplicates": 0, "facts": 0}
    for i in range(0, len(keys), 100):
        body = c.post(f"{w}/discovery/runs/{run_id}/import-selected", json={"keys": keys[i : i + 100]})
        body.raise_for_status()
        for k in imported:
            imported[k] += body.json().get(k, 0)
    print("imported:", imported)
    report["discovery"] = {"results": len(rows), "by_category": by_cat, "imported": imported}

if "research" in steps:
    batch = c.post(f"{w}/companies/research-batch", json={"limit": research_n, "only_missing": True})
    print("research batch:", batch.status_code, batch.json() if batch.status_code < 300 else batch.text)
    batch.raise_for_status()
    outcomes: dict[str, int] = {}
    for job_id in batch.json()["job_ids"]:
        job = wait(job_id, timeout=300)
        key = job["status"] + (":" + (job.get("last_error") or "") if job["status"] != "succeeded" else "")
        outcomes[key] = outcomes.get(key, 0) + 1
    print("research outcomes:", outcomes)
    report["research"] = {"queued": batch.json()["queued"], "outcomes": outcomes}

if "rank" in steps:
    ranking = c.get(f"{w}/ranking/companies", params={"limit": 200}).json()
    print(f"ranking: {ranking['total']} companies, profile {ranking['profile']['name']}")
    for item in ranking["items"][:20]:
        print(f"{item['rank']:3d}. {item['priority']:3d} {item['name'][:45]:45s} {item['location'][:20]:20s} | {item['reason'][:80]}")
    report["ranking"] = ranking["items"]

if os.getenv("REPORT"):
    with open(os.environ["REPORT"], "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
