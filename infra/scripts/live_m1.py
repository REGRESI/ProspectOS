"""M1 live acceptance against the local stack (development only).

Stores the operator's OpenAI settings from the process environment into the demo
workspace via the Integrations API, tests the connection, generates one real text job
and one real GPT-Image job, then prints job states and the usage ledger.
Secrets are read from env and never printed.

  uv run --env-file ../../.env python ../../infra/scripts/live_m1.py
"""

import os
import sys
import time

import httpx

API = os.getenv("API_URL", "http://127.0.0.1:8000")
if os.getenv("APP_ENV", "development") != "development":
    sys.exit("development only")

c = httpx.Client(base_url=API, timeout=120)
login = c.post(
    "/v1/auth/demo",
    json={"email": "demo@prospectos.local", "password": os.getenv("DEMO_PASSWORD") or "ProspectDemo!2026"},
)
login.raise_for_status()
c.headers["X-CSRF-Token"] = login.json()["csrf_token"]
ws = c.get("/v1/workspaces").json()["items"][0]["id"]
w = f"/v1/workspaces/{ws}"

values = {
    k: os.environ[k]
    for k in ("LLM_API_KEY", "LLM_MODEL", "IMAGE_MODEL", "LLM_INPUT_USD_PER_MILLION", "LLM_OUTPUT_USD_PER_MILLION")
    if os.getenv(k)
}
saved = c.put(f"{w}/integrations/credentials/openai", json={"values": values, "test": True})
saved.raise_for_status()
item = saved.json()["item"]
print("openai status:", item["status"], "|", saved.json()["test"]["message"])
print("sources:", {f["name"]: f["source"] for f in item["fields"]})
before = c.get(f"{w}/usage").json()
print("usage before:", before)


def wait(job_id):
    for _ in range(90):
        job = c.get(f"{w}/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed", "ambiguous", "dead"):
            return job
        time.sleep(2)
    return job


text = c.post(
    f"{w}/social/generate",
    json={
        "topic": "Warum regelmäßige Büroreinigung die Mitarbeiterzufriedenheit beeinflusst",
        "audience": "Büroleitungen in Offenburg",
        "objective": "Gespräch anstoßen",
    },
)
print("text request:", text.status_code)
text.raise_for_status()
tj = wait(text.json()["id"])
print("text job:", tj["status"], tj.get("error"))
if tj["status"] == "succeeded":
    result = tj.get("result") or {}
    sample = str(result)[:400]
    print("text sample:", sample)

image = c.post(
    f"{w}/social/images/generate",
    json={
        "prompt": "Helles, aufgeräumtes modernes Büro am Morgen, Reinigungswagen dezent im Hintergrund",
        "alt_text": "Aufgeräumtes Büro am Morgen",
        "rights_confirmed": True,
        "aspect_ratio": "square",
    },
)
print("image request:", image.status_code, image.text[:200] if image.status_code >= 400 else "")
image.raise_for_status()
ij = wait(image.json()["id"])
print("image job:", ij["status"], ij.get("error"))
print("usage after:", c.get(f"{w}/usage").json())
