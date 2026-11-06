"""Writing style from the user's own texts (``data/private/meine-texte.md``, gitignored).

The file holds 3–5 texts the user really wrote (LinkedIn posts, messages, e-mails),
separated by a line ``---`` or by Markdown headings. HTML comments are ignored, so the
file can carry instructions. From the samples a style profile is derived
deterministically (sentence length, greeting, sign-off, Du/Sie) and synced into a
regular voice profile; every text ProspectOS writes then follows these hard rules:

- no dash used as a pause (– — or a spaced hyphen), no typical AI phrasing,
- short direct sentences,
- Du or Sie as agreed (Heute: per workspace setting; posts: from the samples).

The samples are style references only: never facts, never copied verbatim.
"""

import os
import re
from pathlib import Path

from sqlalchemy import select

MIN_SAMPLE = 40
MAX_SAMPLES = 5
PROFILE_NAME = "Nico · meine-texte.md"

AI_PHRASES = (
    "ich hoffe, diese nachricht erreicht sie gut",
    "ich hoffe, diese nachricht erreicht dich gut",
    "in der heutigen schnelllebigen zeit",
    "in der heutigen zeit",
    "lassen sie uns gemeinsam",
    "lass uns gemeinsam",
    "ich freue mich darauf, von ihnen zu hören",
    "zögern sie nicht",
    "zögere nicht",
    "spannende reise",
    "auf das nächste level",
    "game changer",
    "gamechanger",
    "synergien",
    "maßgeschneiderte lösungen",
    "ganzheitlich",
)
REMOVABLE = [p for p in AI_PHRASES if p.startswith(("ich hoffe", "in der heutigen", "zöger"))]
RULES = [
    "Kein Gedankenstrich: weder – noch — noch ein Bindestrich mit Leerzeichen als Pause.",
    "Kein KI-Ton: keine Floskeln wie „in der heutigen schnelllebigen Zeit“, „Synergien“, "
    "„maßgeschneiderte Lösungen“, „zögern Sie nicht“, keine Aufzählungs-Kaskaden.",
    "Kurze, direkte Sätze. Ein Gedanke pro Satz.",
    "Nichts erfinden: keine Kunden, Zahlen, Zitate oder Erlebnisse.",
]


def samples_path() -> Path:
    configured = os.getenv("STYLE_SAMPLES_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "data" / "private" / "meine-texte.md"


def parse_samples(raw: str) -> list[str]:
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    chunks = re.split(r"(?m)^\s*(?:-{3,}|#{1,6}\s.*)\s*$", raw)
    out = []
    for chunk in chunks:
        text = "\n".join(line.rstrip() for line in chunk.strip().splitlines()).strip()
        if len(text) >= MIN_SAMPLE:
            out.append(text[:1500])
    return out[:MAX_SAMPLES]


def read_samples() -> tuple[str, list[str]]:
    """(state, samples) with state missing | empty | ok."""
    path = samples_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return "missing", []
    samples = parse_samples(raw)
    return ("ok" if samples else "empty"), samples


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.split()) >= 2]


def derive(samples: list[str]) -> dict:
    """Deterministic style statistics from the samples (no model call)."""
    sentences = [s for t in samples for s in _sentences(t)]
    words = [len(s.split()) for s in sentences] or [0]
    avg = round(sum(words) / len(words), 1)
    joined = " " + " ".join(samples) + " "
    du = len(re.findall(r"\b(du|dich|dir|dein\w*|euch|euer|eure\w*)\b", joined, re.I))
    sie = len(re.findall(r"\b(Sie|Ihnen|Ihr|Ihre\w*)\b", joined))
    formality = "Du" if du > sie else "Sie" if sie > du else "neutral"
    firsts = [t.splitlines()[0].strip() for t in samples if t.strip()]
    greeting = next(
        (
            re.match(r"^(Hallo|Hi|Hey|Moin|Servus|Guten Tag|Liebe\w*|Sehr geehrte\w*)\b", f).group(
                1
            )
            for f in firsts
            if re.match(r"^(Hallo|Hi|Hey|Moin|Servus|Guten Tag|Liebe\w*|Sehr geehrte\w*)\b", f)
        ),
        "",
    )
    lasts = [t.strip().splitlines()[-1].strip() for t in samples if t.strip()]
    signoff = next(
        (
            line
            for line in lasts
            if re.match(r"^(Viele Grüße|Beste Grüße|Liebe Grüße|Grüße|VG|LG|Gruß)\b", line)
        ),
        "",
    )
    emoji = len(re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", joined))
    dashes = len(re.findall(r"\s[–—-]\s|[–—]", joined))
    return {
        "samples": len(samples),
        "avg_words_per_sentence": avg,
        "formality": formality,
        "greeting": greeting,
        "signoff": signoff,
        "emoji_per_text": round(emoji / max(1, len(samples)), 1),
        "dashes_in_samples": dashes,
    }


def rules(stats: dict | None = None, address_form: str | None = None) -> list[str]:
    out = list(RULES)
    if stats and stats.get("avg_words_per_sentence"):
        target = min(14, max(6, round(stats["avg_words_per_sentence"])))
        out[2] = f"Kurze, direkte Sätze: im Schnitt etwa {target} Wörter wie in deinen Texten."
    form = address_form or (stats or {}).get("formality")
    if form in ("du", "Du"):
        out.append("Du-Form (so abgesprochen).")
    elif form in ("sie", "Sie"):
        out.append("Sie-Form (so abgesprochen).")
    if stats and stats.get("greeting"):
        out.append(f"Typische Begrüßung: „{stats['greeting']}“.")
    if stats and stats.get("signoff"):
        out.append(f"Typischer Gruß: „{stats['signoff']}“.")
    return out


def prompt_rules(stats: dict | None = None, address_form: str | None = None) -> str:
    return "Stilregeln (verbindlich):\n- " + "\n- ".join(rules(stats, address_form))


def clean(text: str) -> str:
    """Enforce the hard rules on any generated or templated text."""
    if not text:
        return text
    out = re.sub(r"(\d)\s*[–—]\s*(\d)", r"\1 bis \2", text)
    out = re.sub(r"\s+[–—]\s+(?=[a-zäöüß])", ", ", out)
    out = re.sub(r"\s+[–—]\s+", ". ", out)
    out = re.sub(r"\s+-\s+(?=[a-zäöüß])", ", ", out)
    out = re.sub(r"(?<=\w)\s+-\s+(?=[A-ZÄÖÜ])", ". ", out)
    out = out.replace("—", ", ").replace("–", "-")
    # Filler sentences are dropped entirely; other phrases are only reported (violations).
    for phrase in REMOVABLE:
        out = re.sub(rf"[^.!?\n]*{re.escape(phrase)}[^.!?\n]*[.!?]?[ \t]*", "", out, flags=re.I)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([,.!?])", r"\1", out)
    out = re.sub(r",\s*,", ",", out)
    return out.strip()


def violations(text: str) -> list[str]:
    found = []
    if re.search(r"[–—]|\s-\s", text or ""):
        found.append("Gedankenstrich")
    lowered = (text or "").casefold()
    found += [p for p in AI_PHRASES if p in lowered]
    return found


def voice_settings(samples: list[str], stats: dict) -> dict:
    formality = stats["formality"] if stats["formality"] != "neutral" else "Du"
    return {
        "name": PROFILE_NAME,
        "description": f"Automatisch aus data/private/meine-texte.md ({len(samples)} Texte)",
        "perspective": "Ich",
        "tone": "direkt, persönlich, bodenständig",
        "formality": formality,
        "emoji": "keine" if stats["emoji_per_text"] == 0 else "wenig",
        "sentence_style": "kurz",
        "cta": "Frage",
        "preferences": f"kurze direkte Sätze (Ø {stats['avg_words_per_sentence']} Wörter in den Beispielen), kurze Absätze",
        "banned_patterns": "kein Gedankenstrich, keine KI-Floskeln (Synergien, maßgeschneidert, ganzheitlich, schnelllebige Zeit)",
        "instructions": "keine erfundenen Fakten, Kunden, Zahlen oder Erlebnisse",
        "no_em_dash": True,
        "platform": "LinkedIn",
        "examples": [{"label": f"Text {i + 1}", "text": t} for i, t in enumerate(samples)],
        "derived": stats,
    }


def file_voice(db, ws: str):
    from app.studio import VoiceProfile

    return db.scalar(
        select(VoiceProfile).where(
            VoiceProfile.workspace_id == ws, VoiceProfile.name == PROFILE_NAME
        )
    )


def sync(db, ws: str, actor: str) -> dict:
    """Create/update the voice profile from the file. Returns status for the UI."""
    from app.studio import VoiceProfile

    state, samples = read_samples()
    item = file_voice(db, ws)
    if state != "ok":
        return status(db, ws)
    stats = derive(samples)
    settings = voice_settings(samples, stats)
    if item is None:
        item = VoiceProfile(workspace_id=ws, name=PROFILE_NAME, actor_id=actor, settings=settings)
        db.add(item)
    elif item.settings != settings:
        item.settings, item.version, item.actor_id = settings, item.version + 1, actor
    db.flush()
    return status(db, ws)


def status(db, ws: str) -> dict:
    state, samples = read_samples()
    item = file_voice(db, ws)
    stats = derive(samples) if samples else None
    return {
        "state": state,
        "path": "data/private/meine-texte.md",
        "samples": len(samples),
        "stats": stats,
        "rules": rules(stats),
        "voice_profile_id": item.id if item else None,
        "voice_version": item.version if item else None,
        "in_sync": bool(item and stats and item.settings.get("derived") == stats),
        "hint": None
        if state == "ok"
        else (
            "Lege die Datei data/private/meine-texte.md an (sie ist gitignored) und füge 3 bis 5 "
            "Texte ein, die du wirklich selbst geschrieben hast: LinkedIn-Posts, Nachrichten an "
            "Kunden oder E-Mails. Trenne die Texte mit einer Zeile ---. Danach hier "
            "„Aus Datei übernehmen“ klicken. Bis dahin gelten nur die festen Stilregeln."
        ),
    }


def register_style_routes(app, db_session, scope, audit):
    from fastapi import Depends, HTTPException

    @app.get("/v1/workspaces/{ws}/style")
    def style_status(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return status(db, ws)

    @app.post("/v1/workspaces/{ws}/style/sync")
    def style_sync(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Keine Berechtigung.")
        result = sync(db, ws, member.user_id)
        if result["state"] == "ok":
            audit(
                db,
                ws,
                member.user_id,
                "style_synced",
                f"Schreibprofil aus meine-texte.md übernommen ({result['samples']} Texte)",
            )
        return result
