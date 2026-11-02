# Architecture

Browser → Next.js App Router/TypeScript → same-origin `/api` proxy → FastAPI/Pydantic → PostgreSQL. The existing modular-monolith topology is preserved. New domain modules separate identity, platform routes/models, jobs, social, commercial policy and typed provider adapters. Shared UI/data hooks and Social/Growth modules are extracted from the original large client component.

The database is the source of truth for tenants, contacts, content, durable job state, usage and audit. Membership verification establishes transaction-local tenant context; FORCE RLS and composite FKs add database isolation. Both API and worker reject table ownership/superuser/BYPASSRLS. An isolated owner-level migrator runs first and exits; runtime processes do not receive its DSN.

A PostgreSQL queue provides atomic enqueue/idempotency, SKIP LOCKED claims, lease recovery, attempts/backoff, persistent results and explicit external-dispatch markers. Critical actions reload policy/membership/revision before dispatch. Unknown paid/external outcomes are ambiguous and cannot be blindly repeated. This is not an exactly-once provider guarantee or a fully fair distributed scheduler.

Private raster storage is a persistent, tenant-authorized volume shared only by API/worker. Image bytes are validated and re-encoded; the browser receives same-origin authenticated asset routes. S3/malware scanning/multihost storage is not implemented. Provider tokens are encrypted; no credentials enter jobs/browser payloads. Provider adapters have typed limits and safe error surfaces, remain unconnected without operator credentials and never manufacture successful receipts.

See STATUS.md for exact tested scope and remaining production release gates. Local builds, configuration structure, remote Git pushes and cloud publication are separate facts.
