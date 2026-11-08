# ProspectOS engineering rules

- Use this existing checkout. Every cloud task is already isolated; do not create a worktree unless the user requests it.
- Keep tenant authorization server-side. Scope all customer reads and writes, test forged tenant/object IDs, and preserve PostgreSQL RLS and composite tenant foreign keys.
- Keep local authentication development-only. Do not claim production identity or external provider support before it is implemented and verified.
- CSVs with real contacts, secrets, session cookies, provider tokens and private assets must never enter Git. Synthetic fixtures must be clearly labeled.
- No LinkedIn scraping, browser bots, auto-connect or DM sending. Message drafts have no sending side effects. A publish action requires real approved API capability.
- ProspectOS itself never automates LinkedIn: no own invitations or messages, no access to LinkedIn sessions or cookies, no emulation, no proxies, no scraping of linkedin.com. External outreach tools (M9, `app/connectors.py`) are reached only through the official APIs of third-party vendors where the user has their own account, behind `EXTERNAL_OUTREACH_TOOLS_ENABLED` and an owner-confirmed risk acknowledgment per workspace.
- No scrapers for North Data, Gelbe Seiten, Das Örtliche, Google Maps or other data providers (including Apify actors); only official, licensed interfaces. Professional registers are linked as pre-filled searches unless their terms allow automated queries.
- The LinkedIn simulator (`app/linkedin_channel.py`) may only target its own synthetic accounts and never contacts LinkedIn. The `official` connection/DM channel stays refused until a real approved partner API exists.
- Prefer complete, tested vertical workflows. Document implemented, demo, disabled and deferred behavior separately in docs/STATUS.md.
- Frontend: apps/web, Next.js/TypeScript. Backend: services/api, FastAPI/SQLAlchemy/PostgreSQL. Infrastructure: infra/ and docker-compose.yml.
- Run relevant root pnpm quality scripts and services/api Python checks before handoff. Consult README.md for working directories.
- Work on the task branch and make coherent commits. Never push to main without explicit authorization.

- Run database suites with `cd services/api && uv run python ../../infra/scripts/validate_database.py`; this isolates fixtures from a running development worker. Never point destructive fixtures at production.
- Keep the privileged migrator separate from API/worker environments. Both runtime processes must use shared role/config startup checks.
- Recheck actor, revision, source/consent/suppression and provider capabilities at dispatch. Unknown external outcomes require reconciliation; never clear dispatch markers or blindly retry.
- Preserve operator/user changes on remote branches. The pilot branch has a Pages deployment workflow; use a review branch when deployment is not authorized.
