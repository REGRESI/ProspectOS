"""Resolve Compose without starting services; verify privilege separation.

Production uses deliberately synthetic configuration, never real credentials.
Resolved config is captured in memory and never printed.
"""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVILEGED = {
    "DATABASE_ADMIN_URL",
    "DB_APP_PASSWORD",
    "POSTGRES_PASSWORD",
    "DEMO_PASSWORD",
}


def resolve(file, environment):
    result = subprocess.run(
        ["docker", "compose", "-f", file, "config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)["services"]


def check(services, production=False):
    assert "DATABASE_ADMIN_URL" in services["migrate"]["environment"]
    assert services["migrate"]["command"] == ["python", "-m", "app.migrate"]
    for name in ("api", "worker"):
        service = services[name]
        assert not PRIVILEGED.intersection(service["environment"]), name
        assert "DATABASE_URL" in service["environment"]
        assert (
            service["depends_on"]["migrate"]["condition"]
            == "service_completed_successfully"
        )
        assert any(
            v["target"] == "/var/lib/prospectos/assets" for v in service["volumes"]
        )
        if production:
            assert service["environment"]["APP_ENV"] == "production"
            assert service["environment"]["AUTH_PROVIDER"] == "supabase"
            assert service["environment"]["COOKIE_SECURE"] == "true"
    assert services["worker"]["command"] == ["python", "-m", "app.worker"]
    assert not services["web"].get("volumes"), "Web must not mount private assets"


def main():
    environment = os.environ.copy()
    check(resolve("docker-compose.yml", environment))
    environment.update(
        {
            "DATABASE_ADMIN_URL": "postgresql+psycopg://test_owner:synthetic@db/test",
            "DATABASE_URL": "postgresql+psycopg://test_app:synthetic@db/test",
            "APP_BASE_URL": "https://app.example.invalid",
            "SUPABASE_URL": "https://auth.example.invalid",
            "SUPABASE_ANON_KEY": "synthetic-public-config",
            "SUPABASE_JWT_ISSUER": "https://auth.example.invalid/auth/v1",
            "TOKEN_ENCRYPTION_KEY": "synthetic-config-validation-only",
        }
    )
    check(resolve("infra/docker/production.compose.yml", environment), production=True)
    print(
        "Compose configuration passed: isolated migrator, unprivileged runtime environments, private asset mounts, production auth settings."
    )


if __name__ == "__main__":
    main()
