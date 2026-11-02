"""Licensed People Data Labs company search, opt-in per operator contract.

Request shape verified against official peopledatalabs-python Company.search and
Elasticsearch README example (2026-11-01). This is not a personal-data scraping API.
"""

import os
from datetime import UTC, datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.providers.ai import ProviderError, configured, request_json


class CompanySearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    country: str = Field(default="germany", min_length=2, max_length=100)
    city: str = Field(default="", max_length=100)
    industry: str = Field(default="", max_length=120)
    min_employees: int | None = Field(default=None, ge=0, le=10_000_000)
    max_employees: int | None = Field(default=None, ge=1, le=10_000_000)

    @model_validator(mode="after")
    def ordered_range(self):
        if (
            self.min_employees is not None
            and self.max_employees is not None
            and self.min_employees > self.max_employees
        ):
            raise ValueError("Invalid employee range")
        return self


class CompanyCandidate(BaseModel):
    external_key: str
    company: str
    location: str
    industry: str = ""
    website: str | None = None
    source_url: str = "https://www.peopledatalabs.com/"
    source: str = "people_data_labs"
    license: str
    observed_at: str
    confidence: str = "provider_reported"
    allowed_uses: str = "Subject to configured license; no marketing consent inferred"


def search_companies(
    criteria: CompanySearchFilters, limit: int = 10, *, client=None
) -> list[CompanyCandidate]:
    if os.getenv("PDL_LICENSE_APPROVED", "false").lower() != "true":
        raise ProviderError("license_not_approved")
    key, license_reference = configured("PDL_API_KEY"), configured("PDL_LICENSE_REFERENCE")
    if not 1 <= limit <= 50:
        raise ProviderError("input_limit_exceeded")
    terms = [{"term": {"location.country": criteria.country.lower()}}]
    if criteria.city:
        terms.append({"term": {"location.locality": criteria.city.lower()}})
    if criteria.industry:
        terms.append({"term": {"industry": criteria.industry.lower()}})
    if criteria.min_employees is not None or criteria.max_employees is not None:
        employee_range = {}
        if criteria.min_employees is not None:
            employee_range["gte"] = criteria.min_employees
        if criteria.max_employees is not None:
            employee_range["lte"] = criteria.max_employees
        terms.append({"range": {"employee_count": employee_range}})
    try:
        payload, _ = request_json(
            "POST",
            "https://api.peopledatalabs.com/v5/company/search",
            client=client,
            side_effect=True,
            headers={"X-Api-Key": key},
            json={"query": {"query": {"bool": {"must": terms}}}, "size": limit},
        )
    except ProviderError as exc:
        if exc.code == "not_found":
            return []
        raise
    records = payload.get("data")
    if not isinstance(records, list) or len(records) > limit:
        raise ProviderError("invalid_provider_response")
    output = []
    for record in records:
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("id"), str)
            or not isinstance(record.get("name"), str)
            or not record["name"].strip()
        ):
            raise ProviderError("invalid_provider_response")
        location = record.get("location") or {}
        if not isinstance(location, dict):
            location = {}
        website = record.get("website")
        if isinstance(website, str) and website:
            website = website if "://" in website else "https://" + website
            parsed = urlsplit(website)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                website = None
        else:
            website = None
        output.append(
            CompanyCandidate(
                external_key=record["id"][:200],
                company=record["name"][:240],
                location=str(location.get("name") or location.get("locality") or "")[:240],
                industry=str(record.get("industry") or "")[:120],
                website=website,
                license=license_reference[:500],
                observed_at=datetime.now(UTC).isoformat(),
            )
        )
    return output
