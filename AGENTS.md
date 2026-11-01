# ProspectOS engineering rules

- Use this existing checkout. Every cloud task is already isolated; do not create a worktree unless the user requests it.
- Keep tenant authorization server-side. Scope all customer reads and writes, test forged tenant/object IDs, and preserve PostgreSQL RLS and composite tenant foreign keys.
- Keep local authentication development-only. Do not claim production identity or external provider support before it is implemented and verified.
- CSVs with real contacts, secrets, session cookies, provider tokens and private assets must never enter Git. Synthetic fixtures must be clearly labeled.
- No LinkedIn scraping, browser bots, auto-connect or DM sending. Message drafts have no sending side effects. A publish action requires real approved API capability.
- Prefer complete, tested vertical workflows. Document implemented, demo, disabled and deferred behavior separately in docs/STATUS.md.
- Frontend: apps/web, Next.js/TypeScript. Backend: services/api, FastAPI/SQLAlchemy/PostgreSQL. Infrastructure: infra/ and docker-compose.yml.
- Run relevant root pnpm quality scripts and services/api Python checks before handoff. Consult README.md for working directories.
- Work on the task branch and make coherent commits. Never push to main without explicit authorization.
