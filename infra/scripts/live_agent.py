"""M8 live acceptance: one CleanStar instruction through the job agent (development only).

  uv run --env-file ../../.env python ../../infra/scripts/live_agent.py "<Auftrag>"
Only confirmation is done by this script; all steps run in the worker.
"""

import os
import sys
import time

import httpx

API = os.getenv("API_URL", "http://127.0.0.1:8000")
if os.getenv("APP_ENV", "development") != "development":
    sys.exit("development only")
instruction = sys.argv[1] if len(sys.argv) > 1 else (
    "Finde 40 Firmen im Umkreis von 15 km um Lahr, recherchiere sie, priorisiere sie, "
    "bereite eine Kampagne vor und fülle die Tagesliste für LinkedIn"
)
c = httpx.Client(base_url=API, timeout=60)
login = c.post("/v1/auth/demo", json={"email": "demo@prospectos.local", "password": os.getenv("DEMO_PASSWORD") or "ProspectDemo!2026"})
login.raise_for_status()
c.headers["X-CSRF-Token"] = login.json()["csrf_token"]
ws = c.get("/v1/workspaces").json()["items"][0]["id"]
w = f"/v1/workspaces/{ws}"
plan = c.post(f"{w}/agent/plan", json={"instruction": instruction})
plan.raise_for_status()
run = plan.json()
print("plan:", run["plan"])
for line in run["estimate"]["lines"]:
    print(f"  - {line['label']}: {line['note']}")
started = time.time()
run = c.post(f"{w}/agent/runs/{run['id']}/confirm").json()
last = ""
while run["status"] == "running" and time.time() - started < 1800:
    time.sleep(5)
    run = c.get(f"{w}/agent/runs/{run['id']}").json()
    line = " | ".join(f"{p['label']}: {p['status']}" for p in run["progress"])
    if line != last:
        print(f"[{int(time.time() - started):4d}s] {line}")
        last = line
print("status:", run["status"], f"after {int(time.time() - started)} s")
for p in run["progress"]:
    print(f"  {p['label']}: {p['status']} – {p['detail']}")
for t in run["results"]["top"][:10]:
    print(f"  {t['priority']:3d} {t['name'][:40]:40s} {t['location'][:18]:18s} {t['reason'][:70]} {t['sources'][:1]}")
