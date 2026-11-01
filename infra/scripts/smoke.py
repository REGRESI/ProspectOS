"""Read-only local functional smoke. Does not print session/CSRF tokens or contacts."""

import http.cookiejar
import json
import os
import urllib.request


def main():
    api = os.getenv("SMOKE_API_URL", "http://127.0.0.1:8000").rstrip("/")
    web = os.getenv("SMOKE_WEB_URL", "http://127.0.0.1:3000").rstrip("/")
    client = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )

    def get(path):
        with client.open(api + path, timeout=15) as response:
            return json.load(response)

    ready = get("/health/ready")
    assert ready["status"] == "ready" and ready["database"] == "connected"
    assert ready["role"] == "prospectos_app"
    with client.open(web, timeout=30) as response:
        assert response.status == 200 and b"ProspectOS" in response.read()
    request = urllib.request.Request(
        api + "/v1/auth/demo",
        data=json.dumps(
            {
                "email": "demo@prospectos.local",
                "password": os.getenv("DEMO_PASSWORD", "ProspectDemo!2026"),
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with client.open(request, timeout=15) as response:
        session = json.load(response)
    me = get("/v1/me")
    assert me["user"]["id"] == session["user"]["id"]
    assert me["workspaces"], "Seed a local demo workspace before smoke validation"
    workspace = me["workspaces"][0]["id"]
    base = "/v1/workspaces/" + workspace
    dashboard = get(base + "/dashboard")
    contacts = get(base + "/contacts?limit=1")
    assert contacts["total"] == dashboard["contacts"]
    assert len(contacts["items"]) <= 1
    print(
        "Smoke passed: web render, restricted DB role, authenticated workspace, consistent contact totals."
    )


if __name__ == "__main__":
    main()
