# Social Studio V2

Implemented on `feat/social-studio-v2`, based on `feat/prospectos-experience-workflows` at `8b92928e4af5a7ba6896d2330638da4a7137a94b`. This extends the existing application; it does not deploy or enable publication.

## Implemented

- Workspace voice profiles: create, edit with optimistic version checks, delete, choose; structured perspective, tone, address/formality, emojis, sentence style, CTA, preferences, banned patterns, instructions, LinkedIn focus and an explicit no-dash rule. Up to three labeled example posts (1,500 characters each). Examples are style references only, never reusable copy or evidence.
- Three provider-backed LinkedIn variants with personal, direct/opinionated and practical/expert angles. Audience, brand, business context, goal, style, length, emojis, CTA, hook, final question, avoidances and user factual notes are included in the job snapshot. Supplied facts use source IDs; example posts do not become factual sources.
- Sixteen refinement actions, including “mehr wie ich”, with current text, selected voice and brand. A source generation job carries facts and writing constraints through subsequent refinements. Jobs persist the original and revised suggestions; accepting a suggestion edits the local composer. Saving creates the existing immutable post revision and invalidates any previous approval/schedule. AI never silently overwrites or approves a saved post.
- Reloadable generation/refinement history (latest 30 jobs), original/result comparison, draft revision history, manual save, duplicate and archive. Existing review, approval and internal calendar scheduling remain available. Internal scheduling does not authorize LinkedIn publication.
- All five image modes: no image, real provider generation, manual library choice, metadata matching and random choice. Gallery thumbnails, title/description/tag search over the loaded library, manual override, remove/replace, rights-aware private media, editable title/description/alt text/tags/rights note, uploader and date.
- Automatic selection ranks up to 1,000 recent reviewed workspace assets by shared terms across topic, brand, voice preferences and media metadata. It explicitly discloses metadata matching, and discloses a newest-image fallback when no terms match. Random selection uses the same authorized/rights-reviewed pool. Neither is visual AI analysis.
- Image prompt builder: concept, visual style, mood, brand palette, optional post context, square/landscape/portrait presets, and explicit permission for text overlays. Actual provider bytes must be decoded and privately stored before success. Images require human review before library/post use. Provenance records actor, model, format, job and the configured maximum cost reservation, which is not a provider invoice.
- Text/image preview switching, desktop/mobile cards, image source labels and controls available on narrow screens. German remains the default UI language and the existing design is preserved.

## Persistence and isolation

Alembic `0008` adds `voice_profiles` with forced PostgreSQL RLS, media metadata columns and a backwards-compatible JSON studio context on existing posts. Voice examples are embedded structured JSON, not a separate table. Existing `jobs`, `post_revisions`, `post_media`, `asset_origins` and the usage ledger remain the authoritative workflows.

All profile, asset, brand, post, generation and parent-job references are checked server-side within the selected workspace. Existing composite tenant foreign keys remain intact. Post snapshots retain selected voice/job IDs and image mode; jobs retain versioned voice settings and generation parameters. Deleted profiles do not prevent editing an already attributed saved draft. New references must still resolve in the same workspace. Voice profiles are included in the existing privileged privacy export. Full workspace erasure and retention remain the previously documented open work.

The worker continues to recheck the actor and configuration, reserve/settle budgets and persist dispatch markers. Unknown paid outcomes must be reconciled; no automatic blind paid retry was added. Explicit no-dash constraints are applied deterministically to all returned variants/refinements. Emoji-free selections are also filtered. Tone, rhythm, length and other stylistic requirements are prompt guidance and need editorial review.

## Credential-gated and deferred

No live LLM, image provider or LinkedIn credentials were supplied. Transport-mocked tests verify the integration workflow, not live authorization, real charges or writing quality. Text requires `LLM_API_KEY`, `LLM_MODEL` and explicit input/output token prices. Images require `IMAGE_MODEL`, `IMAGE_MAX_COST_USD_CENTS` and `IMAGE_API_KEY` (or the configured LLM key fallback). API/worker need the same provider settings and allowed provider egress. The existing OpenAI-compatible text/images adapters are extended; arbitrary provider protocols are not newly implemented.

Provider requirements/errors, durable failure/ambiguous states and review gates are shown. Missing configuration never becomes a generated success. A user may request another generation after resolving a definitive failure; ambiguous outcomes require provider/cost reconciliation first. Offline templates remain explicitly labeled and separate from real AI output.

Live voice-quality evaluation, visual embedding search, automatic style learning, additional provider adapters, provider invoice reconciliation, unlimited examples/history browsing, S3/malware scanning and a full accessibility audit are not delivered here. Generation controls use prompt guidance, not a claim of guaranteed factual truth or guaranteed prose quality. No public deployment, external post, email or LinkedIn action was performed.

## Local update and start

From the repository root, preserving an existing `.env`:

```sh
git fetch origin
git switch feat/social-studio-v2
git pull --ff-only origin feat/social-studio-v2
pnpm install --frozen-lockfile
docker compose up -d db
cd services/api
UV_CACHE_DIR=/tmp/prospectos-uv uv sync --frozen
UV_CACHE_DIR=/tmp/prospectos-uv uv run --env-file ../../.env python -m app.migrate
UV_CACHE_DIR=/tmp/prospectos-uv uv run --env-file ../../.env python -m app.seed
```

On a first install, copy `.env.example` to `.env` before these commands; do not overwrite an existing configuration. Run API and worker in separate terminals from `services/api`. Strip migrator credentials after loading the file, as required by the runtime startup guard:

```sh
UV_CACHE_DIR=/tmp/prospectos-uv uv run --env-file ../../.env env -u DATABASE_ADMIN_URL -u DB_APP_PASSWORD -u POSTGRES_PASSWORD -u DEMO_PASSWORD uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```sh
UV_CACHE_DIR=/tmp/prospectos-uv uv run --env-file ../../.env env -u DATABASE_ADMIN_URL -u DB_APP_PASSWORD -u POSTGRES_PASSWORD -u DEMO_PASSWORD python -m app.worker
```

In a third terminal from the root:

```sh
pnpm dev
```

Open `http://localhost:3000`. Provider-backed generation needs the worker. Configure optional provider values in your private `.env` and restart both API and worker; never commit credentials. Existing seed credentials and local requirements are in README.md. Public deployment is not part of these commands.

## Verification

See TESTING.md for the observed final results and commands. Browser screenshots use only explicitly synthetic workspaces and an original synthetic PNG fixture; they do not depict live AI output.
