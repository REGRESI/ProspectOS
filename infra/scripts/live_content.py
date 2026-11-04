"""M7 live acceptance: 6-week LinkedIn plan + N finished posts with GPT-Image (real LLM).

  uv run --env-file ../../.env python ../../infra/scripts/live_content.py [posts=4]
Development only. Raises the demo workspace AI budget to BUDGET_MINOR (default 1500 cents)
because image jobs are booked at the configured cost cap.
"""

import os
import sys
import time

import httpx

API = os.getenv("API_URL", "http://127.0.0.1:8000")
if os.getenv("APP_ENV", "development") != "development":
    sys.exit("development only")
n_posts = int(sys.argv[1]) if len(sys.argv) > 1 else 4
c = httpx.Client(base_url=API, timeout=180)
login = c.post("/v1/auth/demo", json={"email": "demo@prospectos.local", "password": os.getenv("DEMO_PASSWORD") or "ProspectDemo!2026"})
login.raise_for_status()
c.headers["X-CSRF-Token"] = login.json()["csrf_token"]
ws = c.get("/v1/workspaces").json()["items"][0]["id"]
w = f"/v1/workspaces/{ws}"
print("budget:", c.put(f"{w}/usage/budget", json={"ai_budget_minor": int(os.getenv("BUDGET_MINOR", "1500"))}).status_code)


def wait(job_id, timeout=300):
    start = time.time()
    while time.time() - start < timeout:
        job = c.get(f"{w}/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "dead", "ambiguous"):
            return job
        time.sleep(2)
    return job


plan = c.post(
    f"{w}/content/plans",
    json={
        "name": "Nico · CleanStar · 6 Wochen",
        "goal": "Als verlässlicher Ansprechpartner für Büroreinigung in der Ortenau sichtbar werden und Gespräche mit Büro- und Praxisleitungen anstoßen",
        "audience": "Geschäftsführung, Büro- und Praxisleitungen kleiner und mittlerer Unternehmen im Ortenaukreis",
        "pillars": ["Saubere Arbeitsplätze & Gesundheit", "Blick hinter die Kulissen", "Unternehmertum in der Region", "Praktische Tipps fürs Büro"],
        "cadence": 2,
        "weeks": 6,
        "context": "Verfasser: Nico, Unternehmer, CleanStar Dienstleistungen, Offenburg. Leistung: Büro-Unterhaltsreinigung.",
    },
)
print("plan:", plan.status_code, plan.text[:200] if plan.status_code >= 300 else "")
plan.raise_for_status()
job = wait(plan.json()["job"]["id"])
print("plan job:", job["status"], job.get("last_error") or "")
p = c.get(f"{w}/content/plans/{plan.json()['id']}").json()
print("storyline:", p["storyline"])
for item in p["items"]:
    print(f"  W{item['week']} {item['day']} [{item['pillar']}] {item['topic']}")
for item in p["items"][:n_posts]:
    d = c.post(f"{w}/content/plans/{p['id']}/items/{item['id']}/draft")
    d.raise_for_status()
    dj = wait(d.json()["id"])
    print(f"\n### W{item['week']} {item['topic']}: draft {dj['status']} {dj.get('last_error') or ''}")
    if dj["status"] != "succeeded":
        continue
    post_id = dj["result"]["post_id"]
    print("A:", dj["result"]["a"][:600].replace("\n", " ⏎ "))
    print("B:", dj["result"]["b"][:300].replace("\n", " ⏎ "))
    idea = dj["result"].get("image_idea") or item["topic"]
    img = c.post(f"{w}/social/images/generate", json={"prompt": idea, "alt_text": idea[:200], "rights_confirmed": True, "post_context": item["topic"], "aspect_ratio": "square"})
    print("image request:", img.status_code, img.text[:150] if img.status_code >= 300 else "")
    if img.status_code >= 300:
        continue
    ij = wait(img.json()["id"])
    print("image job:", ij["status"], ij.get("last_error") or "")
    if ij["status"] == "succeeded":
        asset = c.post(f"{w}/social/images/{img.json()['id']}/save", json={"rights_confirmed": True}).json()
        applied = c.post(f"{w}/content/posts/{post_id}/apply", json={"asset_id": asset["id"], "alt_text": idea[:200]})
        print("image attached:", applied.status_code, "asset", asset["id"])
print("\nusage:", c.get(f"{w}/usage").json())
