# Claude Code work log

Continuation of ProspectOS after an interrupted Codex session. Entries are appended per milestone with exact commits and observed test results. Nothing here claims live provider verification unless stated.

## 2026-11-03 — Takeover audit

### Repository state found

- Task branch `claude/inspiring-meitner-vf8sut` was at `d166d55` (pilot + Pages workflow), clean tree, no stashes.
- Remote branches: `feat/prospectos-local-pilot` (`d166d55`), `feat/prospectos-production-mvp` (`489e618`), `feat/social-studio-v2` (`56f14d9`, newest; contains the production MVP, experience workflows `0d4fe20`/`8b92928` and Social Studio V2).
- The task branch was **fast-forwarded** to `56f14d9` so Social Studio V2 and all previous work are preserved. No history was rewritten; `main` untouched.
- **Missing inputs:** `CLAUDE.md`, `docs/CLAUDE_CODE_HANDOFF_2026-11-03.md`, `docs/INTERNAL_SALES_AGENT_V1_ORIGINAL_SPEC.md`, `docs/CLAUDE_SPRINT_PLAN_2026-11-03.md` and `docs/CLAUDE_WORK_LOG.md` exist on no branch in the remote repository. Any uncommitted Codex work from the interrupted session was not pushed and is not recoverable from this checkout. The retained specification is `CODEX_MASTER_PROMPT.md`; status is in `docs/STATUS.md`, `docs/EXPERIENCE_UPGRADE.md`, `docs/SOCIAL_STUDIO_V2.md`. This log was created new.

### Verified baseline (before any change, at `56f14d9`)

- Local PostgreSQL 16 cluster (no Docker daemon in this container). Dev owner role given superuser locally to match the Compose `POSTGRES_USER` semantics the seed relies on; runtime role `prospectos_app` remains NOSUPERUSER/NOBYPASSRLS.
- `uv run python ../../infra/scripts/validate_database.py`: migrate → downgrade base → migrate → seed ×2 → **130 passed**.
- `pnpm lint`, `pnpm typecheck`: pass. `pnpm test`: **19 passed** (5 files).

### Implemented before takeover (verified by reading code + tests)

Tenant RLS/composite FKs (migrations 0001–0008), identity, team, CSV import, contacts/companies, saved searches with deterministic briefing interpretation, durable job queue, synthetic + licensed PDL company discovery (credential-gated), reviewed-domain research adapter (fail-closed), configurable ICP profiles with explainable known/unknown factors, campaigns with sequence planning, offline template drafts, approval inbox, manual LinkedIn handoff events, CRM board, Social Studio V2, official LinkedIn posting adapter (credential-gated), email/billing adapters (credential-gated).

### Gaps identified for Internal Sales Agent V1

1. No free/open company discovery path that works without paid licences; no radius/geocoding (explicitly disclosed as unsupported).
2. Discovery deduplication is exact provider identity only; no domain/name+place duplicate detection against existing companies.
3. ICP scoring of *company* results uses contact-oriented factors (role always "unknown"); no distance factor.
4. Research output is never normalized into cited company evidence; drafts cannot cite evidence.
5. Campaign drafts are template-only; AI output is not attached to sequence drafts.
6. LinkedIn connection/DM workflow is only self-reported manual events; no simulator, no per-channel capability model.

### Environment blockers

- `overpass-api.de` and `nominatim.openstreetmap.org` are denied by this environment's network policy (proxy HTTP 403). OSM adapters can therefore only be verified with transport-mocked responses here. Allowing these hosts in the environment's network settings would permit a live check.
- No provider credentials (LLM, PDL, LinkedIn) are present; those paths stay gated.

## Milestone 1 — OSM discovery, dedup, company fit (`ab824fe`)

- `app/providers/osm.py`: Nominatim geocode + Overpass `around:` search; 18 curated categories → documented OSM tags; keyword name filter with strict charset + regex escaping; ODbL licence, attribution and `openstreetmap.org/{type}/{id}` per row; phone/e-mail tags dropped; ≥1.1 s per-process spacing; fail-closed unless `OSM_DISCOVERY_ENABLED=true` and `OSM_CONTACT` set.
- `app/prospecting.py`: `DuplicateIndex` (identity → domain → normalized name+place) and `company_fit_score` (radius distance, category, unknown size; role excluded and disclosed).
- Import: probable duplicates are linked (evidence attached, no new company); new companies get cited `company_facts`.
- Migration `0009` (discovery criteria/meta, RLS `geocode_cache`, fact source kind/id/actor with composite FK). `GET …/discovery/providers`.
- Tests: `tests/test_osm_discovery.py` 8 new (transport-mocked, synthetic fixtures). Full `validate_database.py`: **138 passed**. Ruff clean. Compose validation passed.
- Not verified live: OSM hosts blocked by environment network policy.
- Next: M2 evidence review endpoints and evidence-cited drafts.

## Milestone 2 — Evidence and cited drafts (`b1eaf96`)

- `app/sales_agent.py`: `GET/POST/DELETE …/companies/{id}/facts`, `POST …/companies/{id}/research`, `POST …/campaigns/{id}/personalize` (`evidence` | `ai`), `GET …/outreach/drafts/{id}/evidence`.
- Research excerpts are accepted only verbatim from a succeeded research job of that company on the company's own domain.
- Evidence drafts use at most two ranked facts (website excerpt > provider > manual; website/opening-hours/tag facts are not used as message content). AI drafts reserve budget, run via the existing durable worker, and store only citations whose IDs match supplied facts.
- Migration `0010` (`draft_evidence`, RLS). Security fix: draft edit role check.
- Tests: `tests/test_sales_agent.py` 6 new. Full suite **144 passed**; ruff clean.
- Not verified live: no LLM credentials; website research remains operator-gated.
- Next: M3 LinkedIn channel simulator/manual/official gate.
