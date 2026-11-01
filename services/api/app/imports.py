import csv
import hashlib
import io
import json
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException

HEADERS = [
    "First Name",
    "Last Name",
    "Company Name",
    "Job title",
    "Email",
    "Email deliverability",
    "Phone",
    "Gender",
    "Company Location",
    "Company domain",
    "Linkedin Profile Url",
    "Linkedin Company Url",
    "Open?",
    "Premium?",
]
DEFAULT_MAPPING = {
    "first_name": "First Name",
    "last_name": "Last Name",
    "company": "Company Name",
    "job_title": "Job title",
    "email": "Email",
    "phone": "Phone",
    "location": "Company Location",
    "linkedin_url": "Linkedin Profile Url",
    "company_url": "Linkedin Company Url",
}


def normalize_url(value, company=False):
    if not value:
        return None
    p = urlsplit(value.strip())
    prefix = "/company/" if company else "/in/"
    if (
        p.scheme not in ("http", "https")
        or p.hostname not in ("linkedin.com", "www.linkedin.com")
        or p.username
        or p.password
        or p.port
        or not p.path.startswith(prefix)
        or len(p.path.rstrip("/")) <= len(prefix)
    ):
        raise ValueError("Ungültige LinkedIn-URL")
    return urlunsplit(("https", "www.linkedin.com", p.path.rstrip("/"), "", ""))


def parse_csv(payload, mapping=None):
    if len(payload) > 3 * 1024 * 1024:
        raise HTTPException(413, "CSV-Datei darf höchstens 3 MB groß sein.")
    try:
        source = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "Bitte CSV als UTF-8 exportieren.") from None
    try:
        dialect = csv.Sniffer().sniff(source[:8192], delimiters=",;\t")
        reader = csv.DictReader(io.StringIO(source), dialect=dialect)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or len(headers) > 60:
            raise ValueError("Doppelte oder zu viele Spalten")
        used_mapping = DEFAULT_MAPPING | (mapping or {})
        if used_mapping["first_name"] not in headers:
            raise ValueError("Spalte für Vorname fehlt. Bitte Zuordnung anpassen.")
        rows = []
        seen = set()
        for index, raw in enumerate(reader, 2):
            if len(rows) >= 5000:
                raise ValueError("Höchstens 5.000 Zeilen pro Import")
            errors = []
            row = {
                key: unicodedata.normalize("NFC", (raw.get(column) or "").strip())
                for key, column in used_mapping.items()
            }
            limits = {
                "first_name": 120,
                "last_name": 120,
                "company": 240,
                "job_title": 240,
                "location": 240,
                "email": 254,
                "phone": 80,
                "linkedin_url": 500,
                "company_url": 500,
            }
            for key, maximum in limits.items():
                if len(row.get(key, "")) > maximum:
                    errors.append(f"{key}: zu lang (max. {maximum})")
            if not row["first_name"]:
                errors.append("Vorname fehlt")
            for key in ("linkedin_url", "company_url"):
                try:
                    row[key] = normalize_url(row.get(key), key == "company_url")
                except ValueError:
                    errors.append(f"{key}: ungültige LinkedIn-URL")
            if row.get("email") and ("@" not in row["email"] or " " in row["email"]):
                errors.append("Ungültige E-Mail")
            identity = row.get("linkedin_url")
            row["duplicate"] = bool(identity and identity in seen)
            if identity:
                seen.add(identity)
            row["import_key"] = hashlib.sha256(
                json.dumps(row, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            row.update(row=index, errors=errors)
            rows.append(row)
        if not rows:
            raise ValueError("CSV enthält keine Datenzeilen")
        return headers, used_mapping, rows
    except (csv.Error, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None
