from typing import Literal, Protocol

from pydantic import BaseModel

from app.db import now


class Candidate(BaseModel):
    external_key: str
    company: str
    first_name: str
    last_name: str
    job_title: str
    location: str
    source: Literal["synthetic_demo"] = "synthetic_demo"
    license: str = "Synthetic development fixture"
    confidence: Literal["unverified"] = "unverified"
    observed_at: str


class DiscoveryProvider(Protocol):
    def search(self, query: str, limit: int) -> list[Candidate]: ...


class SyntheticDemoProvider:
    """Fixed sample candidates, not researched matches to the submitted query."""

    def search(self, query: str, limit: int = 5) -> list[Candidate]:
        return [
            Candidate(
                external_key=f"synthetic-{i}",
                company=f"Demo-Unternehmen {i} (synthetisch)",
                first_name=f"Demo{i}",
                last_name="Beispiel",
                job_title="Office Management",
                location="Offenburg",
                observed_at=now().isoformat(),
            )
            for i in range(1, min(limit, 5) + 1)
        ]
