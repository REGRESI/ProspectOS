# PROSPECTOS — MASTER BUILD PROMPT FOR CODEX

**Paste the entire document below into a Codex task with the new `Prospect OS` GitHub repository selected.**

**Project:** ProspectOS (repository may be named `Prospect OS`; derive actual repository name from checkout).\
**Version:** Master implementation brief v1.0 — 2026-11-01\
**Audience:** Autonomous coding agent and engineering reviewers.\
**Primary UI language:** German (`de-DE`), with i18n-ready English translation support.\
**Objective:** Implement as much of a real, testable, beautifully designed, multi-tenant LinkedIn-first B2B SaaS as possible in the current coding task. Not a mockup.

---

## 0 — YOUR MISSION AND EXECUTION RULES (READ FIRST)

You are acting as the founding principal engineer, full-stack implementation team, product designer, QA engineer, security engineer, and technical writer for **ProspectOS**, an ambitious commercial SaaS product.

**Your task is to BUILD, not merely advise.** Make the changes directly in the checked-out Git repository, install dependencies if allowed, run migrations and tests, build the frontend and backend, and leave behind a working application plus truthful documentation. Do not answer with only a proposed plan, diagrams, pseudocode, screenshots, or an empty scaffold. Code must be committed on a task branch / made available as an inspectable pull request, according to the actual Codex environment permissions. Never push to protected `main` without explicit repository authorization.

### 0.1 Repository and environment reconnaissance

1. Inspect current working directory, repository status, current branch, existing files, available secrets **by key presence only**, toolchain versions, network restrictions and available package managers.
2. Preserve existing useful code and settings; do not delete or overwrite existing work without need. If repository is empty, initialize it cleanly.
3. Read any existing `AGENTS.md`, README, docs, CI workflows and architecture conventions. Reconcile them with this brief; if conflict, follow security and the most recent explicit project specification, document decisions.
4. Check current stable, supported framework releases and provider API documentation **if external network access is available**; do not invent API endpoints, scopes, exact version values, SDK capabilities, or pricing. Pin chosen versions in lockfiles and document source/version. If offline, select widely supported versions already available, avoid guessing unsupported APIs and document follow-up verification.
5. Identify which required integrations have real credentials, which are missing, and which require provider approval. NEVER print secret values or ask the user to paste private credentials into source files.
6. Write `docs/IMPLEMENTATION_PLAN.md` with prioritized phases and status; then immediately implement. Do not stop for approval or clarifying questions. Choose safe defaults and record decisions in `docs/DECISIONS.md`.
7. Read `docs/` and any attached product specification if it exists. This master prompt is sufficient even if no other files exist.

### 0.2 Definition of success

A developer should be able to clone the repository, use `.env.example`, follow a documented local setup, start the stack, and demonstrate these **real vertical workflows**:

- Sign in to a local development/demo environment, switch between workspaces with secure authorization, open a polished dashboard.
- Import the sample **773-row CleanStar CSV** if locally supplied, map fields, preview errors/duplicates, commit to Postgres, re-import safely, browse/edit/search/filter leads and companies. Include synthetic fixture generation if the real file is absent; do **not** commit the real lead CSV or personally identifiable lead data to the repository.
- Configure an Ideal Customer Profile (ICP), run explainable deterministic lead scoring, view score breakdowns and evidence.
- Create a discovery query, run at least one **genuine legal data-discovery adapter** when configured, or a transparent local sample adapter with **obviously labelled synthetic records**; inspect source provenance and import discovered companies/contacts.
- Set up brand identity, content pillars, generate caption suggestions via an AI provider if configured, or via an honestly labeled deterministic offline provider, create/upload/select image assets and alt text, edit posts, approve them, and schedule them in a calendar.
- Connect a LinkedIn personal profile via genuine official OAuth when configured; in local no-key mode use a strict fake provider **only for tests and explicitly labeled demo UI**. Publish only through approved official APIs with scopes actually granted. Handle unconnected/unauthorized states cleanly.
- Build a sales campaign using saved leads, generate message **drafts**, record manual LinkedIn handoffs and contact outcomes, and track opportunities in CRM. A draft creation is NEVER permission to send.
- Review activities, audit history, usage, job failures and access controls. Prove cross-tenant access fails.
- Run `lint`, `typecheck`, backend unit/integration tests, frontend tests and at least core Playwright E2E flows. Document what passed and did not pass.

Aim to go beyond this minimum if time and environment permit, but maintain end-to-end correctness. **Never pretend an integration is working if it lacks credentials, permission, network access or approval.**

### 0.3 Prioritization when execution resources are finite

**Build in vertical slices rather than half-finished horizontal scaffolding.** Finish one usable slice before adding complexity:

- S0: app shell + workspace/auth + API + DB + Docker + CI + quality setup.
- S1: import/contacts/companies + ICP/scoring + saved leads.
- S2: brand/social composer + assets + review/approval + scheduling + adapter with safe demo behavior.
- S3: lead discovery/enrichment provenance + campaigns/outreach drafts + deals/activity tracking.
- S4: real permitted OAuth publishing, optional email integration, billing, analytics and hardening.

At the end, leave an explicit completed/partial/not-started feature inventory. No misleading 100%-done claims. If hitting a context/compute limit, make the repository usable, commit work, create precise follow-up tasks, and prioritize passing checks. Never substitute hundreds of dead-end placeholder buttons for functional screens.

### 0.4 Non-negotiable integrity, legal and provider constraints

- This is a **LinkedIn-first UX**, not permission to violate LinkedIn contracts. Do **not** implement unauthorized LinkedIn crawling, Selenium/Playwright-based logged-in automation, cookie/session stealing, captcha bypass, headless profile harvesting, fake engagement, automated connection requests, or automated LinkedIn DMs without authorized APIs. LinkedIn's official docs prohibit unauthorized bots and scrapers. Lead Discovery must use independent, **licensed B2B data providers**, permitted public company websites, customer-authorized data and user-provided files.
- Do not call a public profile URL or a search query a verified lead. Respect robots/terms/licensing, source attribution, retention and suppression. Do not infer that available data implies lawful permission to market.
- **Germany/EU marketing rules:** promotional email and LinkedIn DMs are not generally lawful merely because an email/profile is public or because the person accepted a connection. Design an explicit policy gate requiring documented applicable consent or a verified statutory exception before the app sends marketing messages. Drafts and manual handoffs are useful even when send is blocked. Legal advice/review still required before production.
- Do not use official LinkedIn API content to build/augment a lead database unless the specific applicable contract explicitly allows that purpose; assume **no** such permission for MVP.
- Differentiate personal publishing (`w_member_social` where available), company page community operations (additional approved access/scopes), and reading the feed/third-party posts (typically restricted). Feature flags must reflect **actual** grants, not optimistic capability assumptions.
- Do not promise exact external API functionality, provider access, automatic image generation or pricing without configuration/verification.
- Never add hardcoded production secrets, private OAuth credentials, real imported contacts, deceptive testimonials, falsified traction, fake analytics or fake integrations.
- Avoid vendor lock-in in domain logic: provider adapters for LLM, image generation, lead discovery, email, storage and social channels.

---

## 1 — PRODUCT VISION AND TARGET MARKET

Product name: **ProspectOS**. Short tagline: **Find the right leads. Start better conversations. Grow your LinkedIn presence.** The software is a multi-tenant, AI-native B2B Sales & Growth platform with a **LinkedIn-first commercial positioning** and a channel-neutral backend. New platforms (Instagram, Facebook, X, etc.) may be added in future without redesigning the database or workflow engine.

### 1.1 Major pillars

1. **Discover** — automatically find potential customer companies, and where legally licensed, individual decision-makers; import from CSV/Excel; audit provenance.
2. **Understand** — enrich, resolve, classify, deduplicate, score by configurable ICP and show verifiable reasons.
3. **Engage** — create tailored outreach drafts, queue legally permitted actions, human approval, campaign timelines, suppression checks, capture replies/outcomes.
4. **Publish** — generate brand-consistent LinkedIn text, visuals, alt text, content strategies, calendar, approval workflows, official API publishing when authorized.
5. **Convert** — contacts → pipeline → follow-up tasks → deals, with simple reporting and attribution.
6. **Learn** — reliable analytics, content and lead quality metrics, transparent AI costs; no fabricated metrics.

### 1.2 Personas

- **Founder/Owner:** small B2B services business; wants quick setup, lead discovery, high-quality posting, meetings.
- **Salesperson/SDR:** segment leads, research, prepare personal outreach, track pipeline.
- **Marketing Manager:** brand kit, content calendar, post publishing, content review.
- **Agency/Operator:** multiple client workspaces with strict isolation (cross-workspace support access is never implicit).
- **Approver/Compliance Officer:** ensure quality, consent, scope and publishing review.
- **Analyst:** read-only insight access.

### 1.3 Use case for initial pilot — CleanStar

CleanStar is a commercial building/office cleaning business based near Offenburg, Germany. A sample externally provided CSV has **773 records and 14 fields**:

`First Name`, `Last Name`, `Company Name`, `Job title`, `Email`, `Email deliverability`, `Phone`, `Gender`, `Company Location`, `Company domain`, `Linkedin Profile Url`, `Linkedin Company Url`, `Open?`, `Premium?`.

Sample dataset has complete LinkedIn profile URLs for 773 rows and **no email, phone, gender or company domain values**. 772 rows have company names and job titles, 773 have first and last names, locations and LinkedIn company URLs. `Open?` / `Premium?` are **not** proof of connection acceptance, consent or email deliverability. Parsing needs Unicode, BOM, different delimiters, apostrophes, umlauts, blank fields, and URLs. Design the import process to handle such data faithfully. Do not infer or invent unavailable emails, domains or “verified buyer intent.” Real CSV must only be loaded in a secure user-controlled workspace after lawful-data-source assessment.

Example ICP: companies near Offenburg, 10–250 employees where evidenced, e.g. offices, agencies, law firms, engineering firms, practices, coworking locations. Relevant roles could be management, facility management, office management, procurement. **Firm size and need are unknown unless verified**. Scores represent fit priority, not empirical probability of purchase.

### 1.4 Hard MVP scope

- Auth, onboarding, workspaces, team invitations and role permissions.
- Dashboard with real database-driven values and appropriate empty states.
- Lead Database: import, mapping/preview, dedup, manual add/edit, list/grid, filters, saved views, bulk selection, tags, activity timeline, company pages.
- Lead Discovery: query builder, background search jobs, multi-provider interface, permitted website research, source evidence, import selected results. Offline demo mode for local development; real-provider integration with documented API/licensing checks.
- Company Intelligence: source-cited research, basic firm metadata, ICP profile builder, rule-based score, manual overrides marked as such.
- Campaign Studio: segmented audiences, outreach templates, AI draft generation, review, sequences as planned actions, per-contact journey, manual LinkedIn action handoff, suppression/consent gate.
- CRM: company/contact detail, customizable limited stage pipeline, kanban, deals, tasks, notes, activity history.
- LinkedIn-first Social: brand profiles, content pillars, idea generator, post editor, caption variants, image upload and optional real AI image generation, assets, alt text, calendar, revision-aware approvals, scheduler, official publishing adapter.
- Engagement: own-content feedback only where authorized; otherwise manual note + suggestion UX; no scraping or bot interactions.
- Integrations status, configurable capability checks, credential connect/disconnect.
- Basic usage/AI cost ledgers, privacy/export/delete UI and audit log, billing groundwork.
- Responsive desktop/tablet/mobile UX, first-class keyboard support, accessibility and loading/error/empty states.

**Explicitly phase-2, not pretend-MVP:** unauthorized automated LinkedIn outreach, full external feed crawling, global social sentiment scraping, automatically commenting/liking arbitrary posts, company-page analytics without approved access, advanced ML predictive lead scores, bulk deliverability verification without provider, real Stripe billing without keys, fully managed autopilot outreach to unconsenting leads.

---

## 2 — TECHNICAL ARCHITECTURE AND IMPLEMENTATION CHOICES

### 2.1 High-level topology

```
Browser (responsive Next.js web, TypeScript)
    |
    | session-bound BFF calls / HTTPS
    v
FastAPI /v1 (Pydantic, workspace context, RBAC, validation)
    |---- PostgreSQL 16+ (source of truth, migrations, tenant isolation)
    |---- S3-compatible object storage (local MinIO for dev)
    |---- Redis (job broker/cache/short-term locks; never sole source of truth)
    |---- Python worker (durable jobs, import, research, AI, schedule, publishing)
    |---- Adapter interfaces:
            |-- AI text (OpenAI or other configured provider; explicit offline mock)
            |-- AI image (provider API and local template fallback)
            |-- Lead intelligence (licensed vendor, website research)
            |-- LinkedIn official API (per verified OAuth scopes)
            |-- Email (configured OAuth/provider; drafts first)
            |-- Billing (Stripe when configured)
```

Use **modular monolith**; do not over-engineer microservices, Kubernetes or Kafka. No hard reliance on the eventual addition of another social channel.

### 2.2 Chosen stack — make coherent choices and pin them

- **Monorepo:** `pnpm` workspaces + Turborepo (optional if simpler), Python project under `services/api` using `uv` or Poetry; choose a stable simple toolchain.
- **Frontend:** supported Next.js App Router release, React, TypeScript `strict`, Tailwind CSS, shadcn/ui/Radix primitives, Lucide icons, TanStack Query, React Hook Form + Zod; full i18n foundation (use `next-intl` or comparable).
- **Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 async or sync consistently, Alembic migrations, PostgreSQL driver, `httpx`, typed service/repository layers.
- **Auth:** Supabase Auth + verified backend JWT/JWKS and workspace-scoped RBAC in production; use a clearly **development-only local auth strategy** for automated local smoke tests without requiring external SaaS. If implementing a local auth provider, secure password hashing (Argon2id), short-lived signed tokens, HttpOnly cookies, CSRF/XSS protections and hard disable dev bypass in production. Simpler alternative: boot local Supabase Auth with its official CLI and document setup; DO NOT fake authenticated requests in production.
- **Jobs:** Python worker queue backed by Redis (e.g. Dramatiq/RQ/Celery; pick one), but track durable job lifecycle and idempotency in Postgres. Cron/periodic scheduler with distributed lease or advisory locks; clear retry semantics. Avoid Trigger.dev if it complicates Python ownership; document trade-off.
- **Object storage:** S3-compatible with MinIO local, private buckets and presigned short-lived access.
- **Tests:** pytest + pytest-asyncio (if async), Vitest + Testing Library, Playwright E2E, test DB and docker-compose integration.
- **CI:** GitHub Actions with Python and pnpm caching, static checks, tests, basic security scans, artifact build.
- **Observability:** structured JSON logs with request/job IDs, safe redaction, Sentry optional, health/readiness endpoints, OpenTelemetry hook optional.
- **Deployment:** Dockerfiles and local compose; frontend ready for Vercel/Node hosting, backend EU-hosting ready; actual production infrastructure/deployment only when credentials provided.

### 2.3 Suggested directory structure

```
.
├── apps/
│   └── web/
│       ├── app/[locale]/(auth)/
│       ├── app/[locale]/(app)/w/[workspaceSlug]/
│       ├── components/{shell,dashboard,leads,discovery,campaigns,crm,social,settings,shared}/
│       ├── lib/{api,auth,i18n,formatting,permissions}/
│       └── tests/
├── services/
│   └── api/
│       ├── app/
│       │   ├── main.py
│       │   ├── core/{config,security,db,logging,errors,policies}/
│       │   ├── modules/{auth,workspaces,leads,imports,companies,
│       │   │   discovery,research,scoring,campaigns,outreach,crm,
│       │   │   brands,social,integrations,compliance,billing,analytics}/
│       │   ├── providers/{ai,images,discovery,social,email,storage}/
│       │   └── workers/
│       ├── alembic/
│       └── tests/{unit,integration,security}/
├── packages/{ui,contracts,config}/
├── infra/{docker,scripts}/
├── docs/{architecture,api,design,security,decisions,implementation}/
├── .github/workflows/
├── AGENTS.md
├── .env.example
├── docker-compose.yml
└── README.md
```

Adapt to current tooling but preserve clear domain modules. Shared API typings generated from backend OpenAPI if feasible; avoid manually drifting duplicate DTOs. Use a consistent base URL and URL-safe encoding; proper pagination, filters and errors.

### 2.4 Operational contracts

- Every write service validates authenticated `user_id`, `workspace_id`, role, object ownership, current state and policy.
- All records that belong to a customer must have `workspace_id`, and tenant-specific FKs prevent cross-workspace association.
- `X-Workspace-Id` must not be trusted blindly; workspace context derived from authenticated user's membership and route selected workspace; BFF adds no magic security.
- API errors use standardized `application/problem+json` or a documented uniform shape `{code,message,details,request_id}` with safe messages.
- All list endpoints paginated and filtered server-side; default limit 25 or 50, maximum 100; avoid unbounded queries.
- Timestamp in UTC, display in workspace timezone (default `Europe/Berlin`), DST-safe scheduling.
- Monetary values integer minor units + currency ISO; never floats for financial ledgers.
- Application-level and DB-level unique/idempotency keys for critical actions.
- Health endpoints `/health/live` and `/health/ready`; readiness probes DB and required local dependencies.

---

## 3 — DESIGN SYSTEM: PREMIUM AND PRODUCTIVE

Make it look like a serious 2026 venture-backed B2B SaaS, not a generic Tailwind admin template. Prioritize clarity, performance, coherent information density and delightful details over flashy animation.

### 3.1 Brand/visual direction

- Working product brand **ProspectOS**, display name exactly spelled. Text logo + minimalist geometric mark (SVG authored directly by code; no assumed trademark asset).
- Style inspiration: precision and density of **Linear**, relationship-oriented polish of **Attio**, clear SaaS UX of **Stripe**, but create original branding, UI and layout (do not copy copyrighted designs/assets).
- Palette: sophisticated off-white background (`#F7F8FA`), white cards, graphite/navy text (`#111827`), understated blue-indigo accent (`#4F46E5` or comparable), slate secondary copy, green success, amber warning, red destructive. Dark theme also supported with its own coherent tokens.
- UI fonts: system/available open web font with solid typography; sensible hierarchy and no oversized decorative text in app screens. Use CSS variables, consistent 4/8px rhythm, 12–16px radii, subtle borders/shadows.
- Persistent sidebar (desktop), compact topbar with workspace switcher + quick search, accessible mobile navigation/drawer.
- Data tables with sticky headers where helpful, selectable rows, search, filter chips, column customization where feasible, bulk actions with confirmation.
- Form validation inline, explicit saving states, toast feedback, undo for safe operations, clear skeletons, helpful empty states, contextual CTA.
- Content Calendar with month/week/list modes, schedule drawer, post status chips, timezone indicator.
- Visually rich but realistic lead detail panels: score breakdown, company, evidence/source, contact, activity, outreach draft.
- Avoid excessive animations and scroll-jacking. Reduced motion support, stable layout (CLS near zero), smooth laptop/mobile scroll, target WCAG 2.2 AA.
- SVG/chart visuals generated from real data. Never hardcode fake business KPIs as if live.

### 3.2 App navigation

Main sections in German:

- **Übersicht** `/overview`
- **Lead Discovery** `/discover`
- **Kontakte** `/contacts`
- **Unternehmen** `/companies`
- **Zielgruppen / ICP** `/audiences`
- **Kampagnen** `/campaigns`
- **Outreach** `/outreach`
- **CRM / Pipeline** `/pipeline`
- **Social Studio** `/social/studio`
- **Content-Kalender** `/social/calendar`
- **Content-Bibliothek** `/social/library`
- **Engagement** `/social/engagement`
- **Analytics** `/analytics`
- **Integrationen** `/settings/integrations`
- **Team & Rollen** `/settings/team`
- **Workspace-Einstellungen** `/settings/workspace`
- **Datenschutz & Compliance** `/settings/compliance`
- **Abrechnung** `/settings/billing`

Use actual route groups and a unified shell. Hide or gracefully gate unavailable features with honest copy; do not show clickable controls that silently do nothing.

### 3.3 Screen-specific UX requirements

**Onboarding wizard** — (1) create workspace, (2) business category/offer/region, (3) ICP starter, (4) define brand voice, (5) optionally connect LinkedIn, (6) import contacts or start discovery, (7) dashboard. Allow skipping optional steps and resuming.

**Overview** — real counters (`contacts`, `companies`, `active_campaigns`, `scheduled_posts`, `open_deals`, `pending_approvals`), trends only when data exists; recent activities, setup progress, next-best-actions, provider connection health.

**Contacts** — paginated table with name, company, role, location, source, fit score, status, last interaction; CSV import button, add lead, saved views, bulk tagging, dedup suggestions; row opens drawer/detail page.

**Company Detail** — website/domain, city, industry, estimated size only with evidence, sources, contacts, notes, deals, research facts, last verified date.

**Discovery** — natural-language goal + structured fields (`country`, `region`, `city`, `radius_km`, `industry`, `min/max employees`, `target job titles`, `company types`, `keywords`, `exclusions`, `max results`, `provider`); estimate costs where known; start/cancel search, progress/result table, per-result sources and license, add selected to workspace. Empty/unavailable states not faked.

**ICP Builder** — criteria, allow/deny lists, geographic fit, role seniority, optional company size, weighted factors summing to 100, editable profile and version history, scoring preview on sample lead.

**Campaigns** — create name, goal, saved audience, sequence stages, channel, templates, start/pause/stop, counts; show legal readiness and approval status before any send.

**Outreach Workbench** — lead context, cited personalization facts, editable message drafts and variants, quality check, manual open LinkedIn profile, copy text, user records connection/request/response status manually, follow-up reminder; channel clearly indicates `manual_handoff`, not `auto_sent`.

**Pipeline** — columns `New`, `Qualified`, `Contacted`, `In Conversation`, `Proposal`, `Won`, `Lost`; cards draggable where stable, per-deal value/owner/next task, stage transitions persisted and logged; filter.

**Social Studio** — 3-column workspace (ideas/strategy; caption editor with variants; post preview/assets), brand profile selector, specific “Generate captions” and “Generate image” actions, text editor, source notes, alt text, media upload, LinkedIn preview, save draft, request approval, approve, schedule. Show exact linked account and permissions.

**Calendar** — week/month/list, status/author/image thumbnail, timezone, conflict handling, reschedule/cancel, post detail drawer, empty-slot quick create.

**Engagement** — own posts/comments only when actual API allows; otherwise manual inbox notes/suggestion mode. External comment suggestions cannot trigger network actions without permissions and review.

**Analytics** — funnel breakdown, chart date filters, transparent data provenance; distinguish `manual_outreach`, `api_published`, `imported_lead`, `actual_deal`; never interpret views/likes as proven sales attribution.

**Settings** — actual provider connection status, scopes, test/refresh/reconnect, policy toggles, team, retention, credits/usage, privacy export/delete.

---

## 4 — DATA MODEL: TABLES, RELATIONSHIPS, INDEXES AND RULES

Use SQLAlchemy 2 typed models and Alembic migrations. Prefer UUID PK, `created_at`, `updated_at`, `created_by` where appropriate, tenant id and soft delete only where justified. Explicit composite FKs `(workspace_id, object_id)` for cross-tenant relationships. Add robust indexes for `(workspace_id, created_at)`, status/schedule, normalized domains, contact names, unique external identity and text search. All migrations must be reproducible from clean DB.

### 4.1 Authentication, tenants and staff

- `users`: `id`, `auth_subject UNIQUE`, `email`, `display_name`, `avatar_url`, `locale`, created/updated; do not duplicate auth credentials when using hosted auth.
- `workspaces`: `id`, `name`, `slug UNIQUE`, `legal_country`, `locale`, `timezone`, `status`, `created_by`.
- `memberships`: `(workspace_id,user_id) UNIQUE`, `role ENUM(owner,admin,editor,approver,analyst)`, `status`, `invited_at`, `joined_at`; only owners may transfer ownership.
- `invites`: `workspace_id`, `email`, `role`, opaque hashed invite token, expiry, used/revoked timestamps; prevent accidental public invite escalation.
- `workspace_settings`: defaults, features, AI budgets, privacy/retention config, local rules.
- `audit_events`: append-only `workspace_id`, `actor_user_id`, `event_type`, `subject_type/id`, `ip_hash` optional, `request_id`, safe metadata json, timestamp; do not store secrets or full sensitive prompts.

### 4.2 Companies, contacts, sources, import

- `companies`: `id`, `workspace_id`, `name`, `normalized_name`, `domain_nullable`, `website_url`, `linkedin_company_url`, `industry`, `subindustry`, `city`, `region`, `country`, `employee_count_min/max_nullable`, `description_nullable`, `last_verified_at`, `source_status`, `deleted_at_nullable`.
- `contacts`: `id`, `workspace_id`, `company_id_nullable`, `first_name`, `last_name`, `display_name`, `job_title_nullable`, `seniority_nullable`, `email_nullable`, `phone_nullable`, `linkedin_profile_url_nullable`, `city_nullable`, `country_nullable`, `connection_status ENUM(unknown,not_connected,request_sent,connected,declined) DEFAULT unknown`, `lifecycle_status`, `owner_user_id_nullable`, `last_contacted_at_nullable`, `source_id_nullable`, `deleted_at_nullable`.
- `contact_identifiers`: `workspace_id`, `contact_id`, `provider`, `identifier_normalized`, optional confidence, verified flag; never assume LinkedIn profile ownership from scraped data.
- `tags` / `contact_tags` / `company_tags` with uniqueness.
- `saved_segments`: `workspace_id`, `name`, `entity_type`, `filter_json` validated against safe filter DSL, `created_by`.
- `data_sources`: `workspace_id`, `source_type ENUM(csv_upload,licensed_vendor,company_website,user_entry,other)`, `provider`, `source_uri`, `license_reference`, `collection_timestamp`, `usage_restrictions_json`, `imported_by`, `privacy_review_status`. Source per imported lead/field when possible.
- `source_evidence`: `workspace_id`, `company_id_nullable`, `contact_id_nullable`, `field_name`, `value_excerpt`, `source_uri`, `observed_at`, `license_usage`, `confidence ENUM(verified,likely,unverified)`, `hash`; do not persist entire scraped pages unnecessarily.
- `import_jobs`: status (`uploaded`, `mapping`, `validated`, `committing`, `completed`, `failed`, `rolled_back`), file storage key, filename, type, mapping JSON, counters, error, owner, batch size, idempotency key.
- `import_rows`: import id, row_number, row_hash, raw_json with sensitive-retention policy, validation_errors_json, resolution (`new`,`merged`,`ignored`,`failed`), target company/contact ID.
- `import_entity_links`: import id + entity type + ID + created_by_import boolean + before/after snapshot or change journal; required for **safe rollback** that does not delete shared/modified records.
- `duplicate_candidates`: candidate pair, method, similarity score, status, reviewer and resolution. Hard unique only on **high-confidence normalized identity** per tenant (e.g. verified exact LinkedIn URL), not weak name/company matching.

Normalization: canonicalize URLs, strip tracking parameters only safely, lowercase domains, IDNA, trim whitespace and Unicode normalization. Do not merge common names solely by fuzzy similarity. Company matching priority: verified domain > precise external company URI licensed source > normalized name + country/city (candidate only). Person matching priority: exact normalized LinkedIn URL > verified email > name+company as candidate only. Empty email is valid.

### 4.3 Discovery, research, scoring

- `discovery_queries`: `workspace_id`, `name`, natural-language goal, validated `criteria_json`, provider choice, status, created_by.
- `discovery_runs`: query, status, started/completed, total/pages processed, token/cost counts, error, cancel flag, idempotency.
- `discovery_results`: run, `entity_kind`, normalized company/person fields, source provider, external provider record key, source URL, license/allowed-use metadata, confidence, duplicate link and selection status, `observed_at`; uniqueness by `(workspace_id, run_id, provider, external_key)`.
- `enrichment_jobs`: workspace, target company/contact, requested fields, state, budget, attempt, created_at.
- `research_facts`: workspace, target type/id, `claim`, `field_name`, `value_json`, `source_url`, `observed_at`, `valid_until`, extraction method/model version, confidence, reviewed_by, risk label. Facts with no source cannot be `verified`.
- `icp_profiles`: workspace, name, description, `criteria_json`, `weights_json`, `version`, active, created_by.
- `lead_scores`: workspace, contact ID nullable, company ID nullable, icp profile, score CHECK 0..100, factors json, missing_data json, calculated_at, scorer_version, manual_override nullable; exactly one target required.

Score weighted deterministic v1 example: industry fit 0–30, geographic proximity 0–25, decision-maker role 0–25, verified need/change signal 0–20. **Missing evidence is unknown, not negative or positive**, and do not fake intent. Configurable per ICP. All score factors have rationale and source IDs.

### 4.4 Outreach, campaigns and consent

- `campaigns`: workspace, title, goal, channel (`linkedin_manual`, `email`, `other_future`), status (`draft`,`active`,`paused`,`completed`,`archived`), segment ID, policy_id, created_by.
- `campaign_enrollments`: workspace, campaign, contact, status, current step, next action, last action; unique campaign+contact.
- `campaign_steps`: ordered sequence, delay in hours, channel, template, requires approval true, allowed stage transitions; use sane follow-up minimums and avoid spam design.
- `message_drafts`: workspace, campaign, enrollment, contact, author, channel, content, subject nullable, revision, origin (ai/manual), cited_fact_ids, approval_state, generated_at, edited_at, proposed_send_at; no sending side effects on draft create.
- `message_approvals`: resource/version, decision, approver, timestamp, comment. Changes after approval invalidate prior approval.
- `outbound_attempts`: workspace, draft id, provider, idempotency key, state, provider message ID nullable, created/sent/failed timestamps, last error. Only actual authorized deliveries create `sent`.
- `manual_outreach_activities`: user-marked `profile_opened`,`connection_requested`,`connected`,`message_sent_manually`,`replied`,`declined`,`followup_due`; manually recorded, not claimed as auto-verified.
- `consent_records`: channel, individual, `legal_basis`, `scope`, jurisdiction, consent_capture_method, evidence_uri, recorded_at, expiry, revoked_at; legal basis is not auto-guessed by AI.
- `suppression_entries`: workspace and global user-specific suppression if applicable, contact/email normalized hash, channel, reason, time; enforced at last possible moment before sending.
- `contact_preferences`: allowed channels, opt out flags and timestamps.
- `policy_evaluations`: requested action, result (`allow`,`deny`,`needs_review`), rule versions, snapshot, reasons, actor and timestamp.

**No unauthorized LinkedIn connection-request or DM send endpoint in MVP.** Only manual handoff via user's browser and status capture. Optional email sends must be behind policy validation, final approval and valid provider authorization; keep disabled by default unless fully implemented.

### 4.5 CRM

- `pipelines`: workspace, name, is_default, archived_at.
- `pipeline_stages`: workspace, pipeline, label, order, probability optional, color token, is_closed_won/lost.
- `deals`: workspace, pipeline/stage, title, company, primary contact nullable, amount minor units, currency, owner, expected close date, origin/campaign attribution nullable, reason_lost nullable, created/updated.
- `activities`: workspace, deal/contact/company, kind, description, actor, metadata, occurred_at; audit-compatible but not substitute for audit log.
- `tasks`: workspace, title, assignee, related company/contact/deal, due_at, state, priority, completed_at; reminders in UI.
- `notes`: workspace, author, entity reference, body, created/updated; sanitized and permission controlled.

### 4.6 Social content, approval, publishing and engagement

- `social_integrations`: workspace, provider, connection id, actor member/page, external account urn, display name, `granted_scopes_json`, `capabilities_json`, connection status, last checked, token secret ref, token expiration; never plain token in DB or UI.
- `brands`: workspace, name, target audience, value proposition, voice descriptors, banned phrases/topics, default language, CTA style, visual identity JSON (fonts/colors/optional logo asset), version.
- `content_pillars`: workspace, brand id, name, purpose, priority, active.
- `content_ideas`: workspace, brand/pillar id, title, angle, notes, source links, status.
- `social_posts`: workspace, account nullable, brand, idea nullable, platform (`linkedin` for v1), caption text, alt text, current_revision, approved_revision nullable, state (`draft`,`needs_review`,`approved`,`scheduled`,`publishing`,`published`,`failed`,`cancelled`), scheduled_at UTC nullable, published_at UTC nullable, provider_post_id nullable, idempotency key, created_by.
- `social_post_versions`: workspace, social_post, revision, caption snapshot, asset reference snapshots, brand version, edited_by, created_at; immutable revision history.
- `social_assets`: workspace, kind (`uploaded`,`generated`,`templated`), private storage key, content type, media byte size, width/height, sha256, alt text, prompt/version, creator, usage license/rights attestation, moderation status, derived thumbnails.
- `post_assets`: workspace, post, asset, sort position, media purpose.
- `social_approvals`: workspace, post, revision, status, approver, timestamp, reason; approval revision must equal current revision at publish time.
- `publishing_jobs`: workspace, social_post id, attempt count, state, scheduled_at, idempotency_key UNIQUE, lock/lease owner, retry_after, provider receipt JSON, error; check one job per post/revision.
- `published_events`: workspace, post, provider, external post urn, published_at, raw receipt summary.
- `engagement_threads`: workspace, account, provider post urn, owned/external, source method, last synced, access status.
- `engagement_comments`: workspace, thread, provider comment id, excerpt, author public ref, observed time, classification; only fetched when authorized.
- `engagement_suggestions`: workspace, thread/comment, action (`reply`,`react`,`skip`), proposed text, evidence, review status, risk flag; default no automatic external action.
- `social_metrics_daily`: workspace, social_account, post, metric date, metric name, integer/numeric value, source, freshness; mark unavailable permissions rather than 0.
- `content_policies`: workspace, brand, autopublish enabled (default false), allowed accounts, approval mode, max posts/day, blackout windows, sensitive topics, compliance settings, version.

**Publishing FSM:** `draft -> needs_review -> approved -> scheduled -> publishing -> published`; `failed -> approved` via deliberate retry/review (not endless blind retry); cancellation allowed before publishing. Editing content/asset/alt text after approval increments revision and reverts to `needs_review`. Provider response unknown after timeout => **ambiguous**; do not blindly retry and risk double-posts; reconcile provider receipt before retry or require manual operator intervention.

### 4.7 Integrations, jobs, payments, usage, privacy

- `provider_connections`: workspace, provider, account id, encrypted or secret-reference token, granted scopes, refresh metadata, status, capabilities, timestamps.
- `job_runs`: workspace, job type, unique idempotency key, requested_by, status, arguments hash/metadata, retry count, error code, timestamps.
- `outbox_events`: workspace, aggregate, event type, payload, status and attempts, created/processed; transactional outbox for critical side effects.
- `usage_events`: workspace, resource kind (`ai_input_tokens`,`ai_output_tokens`,`image_generation`,`discovery_records`,`research_pages`,`publish_attempts`), quantity, estimated cost minor units, provider, timestamp.
- `billing_customers` / `subscriptions` / `entitlements`: workspace, Stripe IDs nullable, plan, limits, state, billing cycle, webhook idempotency.
- `webhook_events`: provider, event ID UNIQUE, payload signature verified, status, processed_at, error; prevent replay.
- `privacy_requests`: workspace, subject identifier, kind (`export`,`delete`,`access`,`rectification`), status, requested/fulfilled, evidence and handling notes.
- `data_retention_policies`: workspace, kind, retention interval, enabled; exclude legal holds appropriately.
- `system_feature_flags`: provider/plan/workspace feature flags with explicit denial defaults.

### 4.8 DB isolation mechanics

- Prefer Postgres RLS as defense in depth for all tenant-owned tables. Backend sets transaction-local `app.workspace_id` from a **verified** identity and membership, never from a raw header or user-provided ID. Ensure session pooling does not leak context. DB app role must not have `BYPASSRLS` and should not own tables. Test no tenant context, mismatched context, query/insert/update/delete/FK violations.
- Business logic also applies RBAC. No direct client DB service-role access.
- Enforce per-workspace composite FK on contacts-to-companies and campaigns-to-contacts, etc.; tests should attempt cross-tenant linkage.
- Deterministic migration with clean DB; seed only synthetic data.
- Build optional `fts`/trigram indexes for search. Use keyset/cursor pagination where sensible.
- API should expose `created_at`/`updated_at` consistently; encrypt truly sensitive fields and honor deletion workflow.

---

## 5 — BACKEND MODULES AND API CONTRACTS

Implement real REST endpoints with OpenAPI schemas, error responses, RBAC, pagination and unit tests. Names below are baseline; adjust only with documented reason. Every endpoint requiring workspace uses `/v1/workspaces/{workspace_id}/...` (or equivalent consistent workspace-scoped routing), validated against membership. Use UUIDs, safe filter DSL, strict Pydantic models.

### 5.1 Identity/workspaces

```
GET    /v1/me
GET    /v1/workspaces
POST   /v1/workspaces
GET    /v1/workspaces/{ws}
PATCH  /v1/workspaces/{ws}
GET    /v1/workspaces/{ws}/members
POST   /v1/workspaces/{ws}/invites
POST   /v1/invites/{token}/accept
PATCH  /v1/workspaces/{ws}/members/{user}
DELETE /v1/workspaces/{ws}/members/{user}
GET    /v1/workspaces/{ws}/dashboard
```

### 5.2 Imports, contacts, companies

```
POST   /v1/workspaces/{ws}/imports/upload        (multipart, file constraints)
GET    /v1/workspaces/{ws}/imports/{id}
POST   /v1/workspaces/{ws}/imports/{id}/mapping
POST   /v1/workspaces/{ws}/imports/{id}/validate
GET    /v1/workspaces/{ws}/imports/{id}/preview
POST   /v1/workspaces/{ws}/imports/{id}/commit
POST   /v1/workspaces/{ws}/imports/{id}/rollback
GET    /v1/workspaces/{ws}/imports/{id}/errors
GET    /v1/workspaces/{ws}/contacts
POST   /v1/workspaces/{ws}/contacts
GET    /v1/workspaces/{ws}/contacts/{id}
PATCH  /v1/workspaces/{ws}/contacts/{id}
DELETE /v1/workspaces/{ws}/contacts/{id}
POST   /v1/workspaces/{ws}/contacts/bulk-tags
GET    /v1/workspaces/{ws}/companies
POST   /v1/workspaces/{ws}/companies
GET    /v1/workspaces/{ws}/companies/{id}
PATCH  /v1/workspaces/{ws}/companies/{id}
GET    /v1/workspaces/{ws}/segments
POST   /v1/workspaces/{ws}/segments
```

Imports support CSV (UTF-8 BOM, semicolon/comma/tab auto-detection), XLSX via openpyxl, max file bytes and row count configurable, malicious spreadsheet formula neutralization on exports, no trusting uploaded MIME. Preview includes source column mapping, validation issues, duplicates and expected totals. `commit` uses durable chunk processing and staging, idempotency and summary. Rollback handles only safe creations/changes based on journal; if records since edited outside the import, report conflicts and do not erase users' work.

### 5.3 Discovery and research

```
POST   /v1/workspaces/{ws}/discovery/queries
GET    /v1/workspaces/{ws}/discovery/queries
POST   /v1/workspaces/{ws}/discovery/queries/{id}/run
GET    /v1/workspaces/{ws}/discovery/runs/{id}
POST   /v1/workspaces/{ws}/discovery/runs/{id}/cancel
GET    /v1/workspaces/{ws}/discovery/runs/{id}/results
POST   /v1/workspaces/{ws}/discovery/runs/{id}/import-selected
POST   /v1/workspaces/{ws}/companies/{id}/enrich
GET    /v1/workspaces/{ws}/companies/{id}/research
POST   /v1/workspaces/{ws}/icp-profiles
GET    /v1/workspaces/{ws}/icp-profiles
PATCH  /v1/workspaces/{ws}/icp-profiles/{id}
POST   /v1/workspaces/{ws}/lead-scores/compute
GET    /v1/workspaces/{ws}/lead-scores?contact_id=...
```

### 5.4 Campaigns, drafts, CRM

```
GET    /v1/workspaces/{ws}/campaigns
POST   /v1/workspaces/{ws}/campaigns
GET    /v1/workspaces/{ws}/campaigns/{id}
PATCH  /v1/workspaces/{ws}/campaigns/{id}
POST   /v1/workspaces/{ws}/campaigns/{id}/enroll
POST   /v1/workspaces/{ws}/campaigns/{id}/pause
POST   /v1/workspaces/{ws}/outreach/drafts/generate
GET    /v1/workspaces/{ws}/outreach/drafts
PATCH  /v1/workspaces/{ws}/outreach/drafts/{id}
POST   /v1/workspaces/{ws}/outreach/drafts/{id}/request-approval
POST   /v1/workspaces/{ws}/outreach/drafts/{id}/approve
POST   /v1/workspaces/{ws}/outreach/manual-activity
GET    /v1/workspaces/{ws}/pipelines
GET    /v1/workspaces/{ws}/deals
POST   /v1/workspaces/{ws}/deals
PATCH  /v1/workspaces/{ws}/deals/{id}
GET    /v1/workspaces/{ws}/tasks
POST   /v1/workspaces/{ws}/tasks
PATCH  /v1/workspaces/{ws}/tasks/{id}
```

### 5.5 Social/brand/publishing

```
GET    /v1/workspaces/{ws}/brands
POST   /v1/workspaces/{ws}/brands
PATCH  /v1/workspaces/{ws}/brands/{id}
GET    /v1/workspaces/{ws}/social/ideas
POST   /v1/workspaces/{ws}/social/ideas/generate
POST   /v1/workspaces/{ws}/social/captions/generate
POST   /v1/workspaces/{ws}/social/assets/upload
POST   /v1/workspaces/{ws}/social/assets/generate
GET    /v1/workspaces/{ws}/social/assets
GET    /v1/workspaces/{ws}/social/posts
POST   /v1/workspaces/{ws}/social/posts
GET    /v1/workspaces/{ws}/social/posts/{id}
PATCH  /v1/workspaces/{ws}/social/posts/{id}
POST   /v1/workspaces/{ws}/social/posts/{id}/submit-review
POST   /v1/workspaces/{ws}/social/posts/{id}/approve
POST   /v1/workspaces/{ws}/social/posts/{id}/reject
POST   /v1/workspaces/{ws}/social/posts/{id}/schedule
POST   /v1/workspaces/{ws}/social/posts/{id}/cancel
POST   /v1/workspaces/{ws}/social/posts/{id}/publish-now
GET    /v1/workspaces/{ws}/social/calendar
GET    /v1/workspaces/{ws}/social/engagement
GET    /v1/workspaces/{ws}/social/accounts
```

Provider side effects are worker tasks, not directly in HTTP request; HTTP action validates and enqueues durable job. Enforce publish approval revision matching the queued revision, owner permission, authorized account and granted capability, legal/brand policy, rate limit, scheduled time and image rights before every attempt.

### 5.6 Integrations, privacy, monitoring, billing

```
GET    /v1/workspaces/{ws}/integrations
POST   /v1/workspaces/{ws}/integrations/linkedin/start
GET    /v1/integrations/linkedin/callback
POST   /v1/workspaces/{ws}/integrations/linkedin/disconnect
GET    /v1/workspaces/{ws}/integrations/linkedin/capabilities
GET    /v1/workspaces/{ws}/usage
GET    /v1/workspaces/{ws}/audit
POST   /v1/workspaces/{ws}/privacy/export
POST   /v1/workspaces/{ws}/privacy/delete-request
GET    /v1/workspaces/{ws}/privacy/requests
GET    /v1/workspaces/{ws}/billing
POST   /v1/workspaces/{ws}/billing/checkout
POST   /v1/webhooks/stripe
GET    /v1/workspaces/{ws}/analytics/overview
GET    /health/live
GET    /health/ready
```

- OAuth callback validates `state`, `nonce` as applicable, redirect allowlist, PKCE if supported, token exchange and granted scopes, error/revocation handling. Tokens stored in secrets provider/encrypted field, never browser localStorage, never logged.
- If LinkedIn credentials missing: UI shows `Noch nicht konfiguriert`, CTA to setup instructions, optional manual handoff; do not show green "Connected".
- Billing without keys may show clearly-labeled development test plan but cannot collect charges. Stripe webhook signatures must be validated, events idempotent.

---

## 6 — LEAD DISCOVERY: MAKE IT USEFUL WITHOUT LINKEDIN SCRAPING

This is a CORE feature, not deferred. Implement modular ingestion from contractually authorized sources plus cautious public company research. Users should be able to input ICP and find high-fit companies without uploading existing leads. Deliver at least one legal operational path configured via API credentials and a deterministic sample path for offline E2E.

### 6.1 Provider abstraction

Define typed interfaces, e.g.:

```
LeadDiscoveryProvider.search_companies(criteria, cursor, page_size, budget)
  -> ProviderPage[CompanyCandidate]
LeadDiscoveryProvider.search_people(company_keys, role_filters, cursor, budget)
  -> ProviderPage[ContactCandidate]
WebsiteResearchProvider.research_company(verified_domain, permitted_sources)
  -> EvidenceBackedResearch
```

Each candidate has `source`, `external_key`, `license`, `allowed_uses`, `observed_at`, `confidence`, `company`, optional `contacts`, and nullable fields. Errors distinguish `missing_credentials`, `provider_forbidden`, `rate_limited`, `license_not_approved`, `not_found`, `transient_failure`.

Create a **provider registry** and at least:

1. `ManualCsvProvider` / CSV import (fully functional).
2. `SyntheticDemoDiscoveryProvider` for development only; stable fake company/contact data clearly labeled and never shipped as real contacts or business metrics.
3. `LicensedB2BProvider` adapter interface with concrete implementation for an available provider whose **current official docs and contract/license permit the actual use** (e.g. an Apollo or People Data Labs integration **only after verification**). If no verification/credentials, keep integration off and provide documented configuration, proper error state; do not invent working API calls.
4. `PermittedCompanyWebsiteResearch` using explicitly supplied/verified company URLs, robots/terms-compliant request fetching (never LinkedIn logged-in pages), content type/time/size limitations, SSRF protections, rate limits, caching/retention, stable source citations, and anti-prompt-injection boundaries. If compliance cannot be determined automatically, require user permission/data source review before fetch.

Do **not** create a Google/LinkedIn scraping bypass or route through proxies to evade limits. Do not try to scrape search-result pages that prohibit it. Optional use licensed search APIs for discovery; only when contractual right supports it. Where public data cannot be automatically fetched, allow customers to enter URLs and manually verify records.

### 6.2 Discovery process

- Input: natural language brief and structured query; preview derived filters and allow user to correct.
- Validate geographic search, sector mapping, employee ranges, titles, company types, excludes.
- Compute provider availability and expected cost/rate before running, require confirmation if nontrivial costs.
- Async fanout by provider, throttle, paginated cursors, cancel support, checkpoints; persist partial results on errors and show results quality.
- Normalize/dedupe and enrich where permitted; retain provenance per result.
- Heuristic ICP score with evidential reasons; unknowns surfaced.
- Result screen lets users `Import selected`, `Save search`, `Export eligible data` (respect license), `Find relevant roles` (only from authorized provider), `Create audience`.
- Do not resell pooled personal data across tenants unless explicit contract and data protection basis; per-tenant data never automatically shared.
- Add scheduled saved-search groundwork, but do not run repeated quota-consuming discovery without explicit user activation/budget.

### 6.3 Lead source legality

Add per-provider source and license metadata. Company business information and personal contact information have different privacy/usage rules. An importer must record uploader attestation and origin for third-party lead lists (including the CleanStar CSV). Unverified source means data may be stored in quarantined/limited mode, but **must not be automatically used in outbound campaigns** until appropriate review. A public LinkedIn URL is not consent.

---

## 7 — AI ARCHITECTURE AND GENERATION QUALITY

### 7.1 Provider abstractions and fallback

Implement an `LLMGateway` with structured JSON schema responses, strong timeout handling, token/cost metrics, prompt versioning, per-tenant budgets and rate limiting. Use an OpenAI-compatible provider (e.g. official OpenAI API) only when configured. Avoid hardwiring a model identifier that may not exist. Use env-configurable supported model. Offline deterministic **demo** service returns realistic, clearly watermarked/text-labeled test suggestions; it must not claim a real AI provider was called.

Image generation through `ImageProvider.generate` where supported; if missing credentials, allow **real asset upload** and deterministic local brand template generation (SVG/Canvas rendered on server or browser, with license-safe fonts) and clearly label it as template, not generative AI. Ensure generated image byte output is actually stored, not merely remote placeholder links. For v1, testable upload+template may precede external image AI.

### 7.2 Agents and outputs

- **Company Research:** valid verified domain, locate public official website content, extract structured evidence, discard embedded instructions (web content is untrusted), summarize with citations and uncertainty.
- **ICP Scorer:** deterministic/weighted, safe defaults, transparent factor sources and unknowns. No hallucinated purchase intent.
- **Outreach Writer:** input lead, company verified facts, user offer, campaign goal, tone, language, legal status; output 2–3 personalized variants with citation IDs, reason and unsupported-claim flags. Do not mention facts without evidence.
- **Content Strategist:** content pillars, persona, market, factual source suggestions, publication ideas, 1/2/4-week proposed schedules without fabricated customer stories.
- **Caption Writer:** 3 distinct variants with hook/body/CTA/optional hashtags, length count, tone, platform fit, supporting facts; German-first, natural and not spammy.
- **Visual Agent:** brief, style consistency, composition, aspect ratio e.g. 1:1 and 4:5, alt text, license/rights notes, multiple choices when provider supports; no fake company workers/customers or fictional case studies represented as actual photos.
- **Content Reviewer:** fact checks against stored evidence, prohibited-phrases, spam/duplicate check, brand profile, accessibility (alt text), AI-generated image disclosures as appropriate, content safety.
- **Engagement Copilot:** if authorized access to comments on owned posts, triage and generate response drafts; otherwise manually supplied comment text/links may be analyzed with clear source label. External automatic comments and likes disabled.
- **Analytics Advisor:** evidence-based reporting, missing data warnings; not causal claims without attribution.

### 7.3 Structured generation and injection resistance

For every generation:

- Use typed request and response schemas, model/provider name, prompt version, temperature/settings and result id; validate/repair JSON safely.
- Content from websites, source leads and imported documents remains **data**, never system instructions. Strip executable content, limit context sizes, delimit untrusted passages and never execute directives embedded in them.
- Differentiate verified fact, model suggestion, marketing copy, unverified inference and human-authored content.
- Never auto-trigger a network posting/messaging action as a side effect of LLM response.
- Track requests per workspace with quotas, budgets, retries and cancellation.
- Keep raw PII out of development telemetry and provider logs where possible; document processor configuration.

---

## 8 — LINKEDIN CONNECTOR AND SOCIAL PUBLISHING

### 8.1 Provider contract

Create `SocialProvider` interface with `start_oauth`, `complete_oauth`, `get_authorized_accounts`, `get_capabilities`, `upload_image`, `publish_post`, `get_post_receipt`, `disconnect`, optional `list_owned_posts`, `list_owned_comments`, `create_comment`, `create_reaction`.

- Implement `LinkedInOfficialProvider` with actual endpoints/scopes/version headers verified from docs available in environment. For personal posts use appropriate Share on LinkedIn / Posts APIs and `w_member_social` where authorized; image media requires proper register/upload/finalize lifecycle depending on current API. Do not use deprecated endpoints blindly; keep adapter version configurable and documented.
- OAuth customers connect **their** account to **our** approved application; customers do not create their own developer app. The **software operator** must register an app, configure redirect URIs, obtain necessary app product permissions and possibly apply for extended/vetted API access.
- Page/community API requires separate product approval/verified admin rights; do not claim all members get it automatically.
- Read access to arbitrary personal feeds, third-party comments and profile databases is not assumed.
- Build per-account capability matrix from actual scopes/API availability; every UI/worker action honors it.

### 8.2 Posting lifecycle and publisher worker

1. User creates post draft with caption, image asset(s), alt text, brand.
2. User submits review; approver explicitly approves exact revision.
3. User schedules at local date/time, validate DST ambiguity with timezone.
4. Publishing worker loads latest DB state and verifies: workspace membership/owner policy, account auth/scopes, latest revision == approved, media rights, content quality, kill switches, schedule, rate limit, idempotency key.
5. Upload media to official LinkedIn media API using short-lived token loaded server-side; create post with correct payload.
6. Save provider receipt/URN and `published_at` transactionally; audit and update UI.
7. On 401/403, disable capability and surface reconnect/scope guidance. On 429, backoff and preserve state. On ambiguous network timeout, **do not blindly resend**: reconcile where possible, otherwise mark ambiguous/manual review.
8. Editing a queued or approved post invalidates approval; cancellation before post dispatch is honored.
9. Workspace and platform kill switches immediately stop new dispatches.
10. Concurrency test proves two workers cannot dispatch same post simultaneously; if LinkedIn doesn't offer idempotency keys, use database claim/leases + reconciliation to minimize risk and admit exact-once cannot be guaranteed under unknown provider outcomes.

### 8.3 Engagement

MVP shows a **capability-driven** engagement center. If provider grants own comment read/write: display and draft responses for review. For absent scopes: show honest unavailable state plus manual comment paste/reply preparation. No automatic mass liking/commenting, no scraping feed, no fake interactions.

### 8.4 Platform extensibility

Use `platform` enums/registry plus provider interfaces; implement only LinkedIn UI flows in v1. Leave clean insertion points for Instagram/Facebook without dead features.

---

## 9 — LEGAL/COMPLIANCE ENGINE

**Do not automate marketing communication merely because contact data exists.** Build a deterministic side-effect policy engine independent of LLM.

- `ActionContext`: workspace, actor, contact, channel, purpose, message revision, provider capabilities, consent/legal basis evidence, suppression status, quotas, country, timestamp.
- `PolicyGate.evaluate(action)` returns typed `allow/deny/needs_review` with stable machine codes and human readable German reasons.
- Before send: enforce suppression, lawful basis for marketing channel and jurisdiction, valid account scopes, recipient/source restrictions, approvals and quota. Deny by default on ambiguous or missing requirements.
- Manual LinkedIn handoff creates no automated send; user retains responsibility for their independent behavior. UI should not encourage unlawful mass marketing.
- Provide easy opt out and suppression management; stop campaign enrollments when opt out/objection recorded.
- Source provenance, per-record retention and deletion/export requests.
- DPA/GDPR/ToS production review remains a legal release gate; application UI must not present compliance as certified.
- Deleting a contact should cascade/anonymize derived notes, scores, drafts, queued jobs and assets appropriately; audit retention subject to legal basis and minimality.
- SSRF protection for website fetches: block loopback, link-local, RFC1918/private networks and cloud metadata endpoints, validate redirects, DNS rebinding and response limits.
- File uploads: size/mime checks, malware scanning hook, avoid path traversal, signed retrieval.
- Logging: redaction for tokens, PII, private message body unless explicitly required.

---

## 10 — JOB ORCHESTRATION, BILLING, ANALYTICS AND RELIABILITY

### 10.1 Background tasks

Implement durable job runners for:

- CSV validation/commit and rollback.
- Discovery provider queries, cancellation, result normalization.
- Company enrichment/research and scoring.
- AI generation, image generation and asset thumbnailing.
- Scheduling/publishing approved posts.
- Periodic token health checks and capability refresh (only if permitted).
- Privacy exports/deletions and retention cleanup.
- Analytics aggregation and safe notifications.

Every job requires persisted status/progress, clear failures, max retries, exponential backoff/jitter, tenant-aware budgets, idempotency, trace ID, and retry-safe actor checks. Distinguish retryable network failures from permanent permission/compliance errors. Do not put PII in queue payload if ID lookup suffices.

### 10.2 Subscription / entitlements

Design plans: `Trial`, `Starter`, `Growth`, `Agency` as configurable entitlements, not hardcoded fabricated live prices. Define limits for member seats, active campaigns, records, monthly credits, AI text/image calls, provider connections, workspace count. In dev offer accessible demo plan; in production Stripe checkout/webhook when secrets set. Billing invoices and real collection are **out of scope until Stripe fully configured and verified**. Avoid blocking pilot users because billing is not connected.

### 10.3 Analytics event taxonomy

Track `lead_imported`, `lead_discovered`, `lead_scored`, `draft_generated`, `manual_handoff_opened`, `connection_status_recorded`, `reply_recorded`, `deal_created`, `deal_won`, `post_approved`, `post_scheduled`, `post_published`, `post_failed`, `content_engaged` (only verified authorized source). Every event includes workspace, timestamp, source, actor, related entity. Report separate **confirmed**, **self-reported**, **estimated**, **unavailable** data. Do not show fabricated benchmarks.

### 10.4 Performance and cost

- Contact listing and common dashboard endpoints should feel responsive at 10k leads/workspace. Paginate and index.
- Large uploads and external fetches must never block request threads.
- Avoid N+1 ORM queries; use request-scoped DB sessions and eager loading.
- Provider rates/budgets per workspace and per third-party account; circuit breakers when rate-limited.
- Monthly AI budget and cost breakdown, hard limits configurable.
- Prepared for 100 tenants x 10k contacts without architectural changes; performance targets documented as goals, not claims.

---

## 11 — AUTHORIZATION AND SECURITY REQUIREMENTS

### 11.1 RBAC matrix

Roles: `owner`, `admin`, `editor`, `approver`, `analyst`.

- Owner: all workspace operations, billing, transfer, delete, integrations.
- Admin: team invitations except owner grants/transfers, policies, integration setup, manage campaigns and brands.
- Editor: manage contacts, companies, research, campaigns, content drafts, own tasks; cannot approve own regulated action unless policy explicitly permits and role includes approver.
- Approver: view content and grant/deny approval, can view underlying context; editing permissions separate.
- Analyst: read-only dashboards, permitted leads/analytics, no modifications or posting.

Use code-centered permission policy definitions and authorization tests. Role checks not just on UI. Enforce least privilege for uploaded files and job workers.

### 11.2 Required security checks

- CSRF and OAuth state safety, `SameSite`, HttpOnly secure cookie config, CSP, XSS escaping, no unsafe HTML rendering from LLM/web data, SQL injection prevention with ORM/params.
- Token storage encryption or managed secret reference; rotate/refresh/revoke with minimal logs.
- Rate limits on auth, uploads, AI, search and outbound; queue cost limits.
- RLS tenant isolation even for background jobs, no `BYPASSRLS` app role.
- User initiated export/delete with proof of authentication and processing status.
- Tests for malicious SVG/file upload, unauthorized asset access and prompt injection.
- No analytics SDK sending user contact data without conscious configuration.
- Secrets only `.env` ignored; complete `.env.example` with nonsecret placeholders.

---

## 12 — QUALITY GATES, TEST PLAN, SEED AND E2E

### 12.1 Full CI quality suite

At minimum implement and run:

- `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build` (or documented equivalents).
- Python formatting/lint, typing (mypy/pyright if feasible), `pytest` unit/integration.
- Alembic upgrade on fresh PostgreSQL and downgrade sanity if relevant.
- Docker Compose smoke: start DB/Redis/storage/backend/frontend, `/health/ready` succeeds, UI renders.
- Playwright e2e with local synthetic data and dev auth; screenshots or traces retained only in CI artifacts.
- GitHub Actions protecting PR quality (not assuming permission to set branch protection).

### 12.2 Critical test cases (implement, not only describe)

1. **Cross-tenant contact leak:** tenant A user cannot read/update/delete tenant B contact via forged route/ID.
2. **Cross-tenant FK:** tenant A campaign cannot enroll tenant B contact even via direct DB insert.
3. **No workspace auth:** tenant tables fail closed if session variable/context missing.
4. **CSV sample shape:** 773 test records with exact headers and empty email/phone/domain import cleanly (generate synthetic names/data; no PII copied); proper errors for malformed URLs, duplicate URLs, missing company, encodings; re-import idempotent.
5. **Rollback safe:** revert own new entities but not other users' edits; conflicts surfaced.
6. **AI output:** valid schema, omitted/unknown facts not falsely reported, provider unavailable returns transparent state, no unbounded cost.
7. **Scoring:** deterministic score factors, correct missing evidence handling.
8. **Discovery:** cancel, rate limit, source metadata, dedup; synthetic results clearly tagged.
9. **Outreach:** draft generation does not send; missing consent/suppression denies sending; manual status not counted as provider-verified.
10. **Social approval invalidation:** edit post/media after approval reverts review status.
11. **Scheduler timezones:** Europe/Berlin DST transition safe handling.
12. **No duplicate publishing:** concurrency mock and retry test; ambiguous result requires reconciliation/manual review.
13. **Scope failure:** `publish` unavailable without granted `w_member_social` or provider-specific rights; UI reflects unavailable.
14. **OAuth CSRF:** invalid/expired state rejected, callback does not leak tokens.
15. **Image upload:** unauthorized tenant read denied, invalid file rejected; alt text present.
16. **Billing:** duplicate Stripe webhook event processed once (if integration implemented).
17. **A11y:** keyboard navigating sidebar, modal focus trap, button labels, contrast checks for primary screens.
18. **Responsive:** 375px mobile, 768px tablet, 1440px desktop; no horizontal overflow, no stuck/wobbly scroll.

### 12.3 E2E product flows

**Flow A:** Demo login → create CleanStar-like workspace → upload CSV (synthetic test dataset if original not supplied) → map header columns → preview → commit → inspect 773 contacts → filter near target area → inspect score and notes.

**Flow B:** Build ICP → discovery query (synthetic provider clear label) → view deduped candidate companies and evidence → import approved results → campaign audience → generate outreach draft → edit/copy/open LinkedIn profile (manual) → record follow-up task → add deal.

**Flow C:** Create brand → generate caption ideas → upload/generate template image → edit → submit review → approve → schedule → fake provider in explicitly test mode records publish receipt once → UI updates, audit event recorded; real LinkedIn only used when genuine secrets and verified auth exist.

**Flow D:** Create workspace B; prove A-user cannot see B's contacts, posts, assets, integration tokens or job output.

### 12.4 Demo mode must be honest

Demo seed: a handful of **fictional businesses and names** with obvious `Demo-Daten` labeling, localized to a representative region. No production dashboard counters if zero; show a helpful empty state. Real CSV is optional and must not be committed to the repo. Do not ship auto-login bypass when `APP_ENV=production`. Demo provider never performs real outbound network posting and never reports simulated activity as real.

---

## 13 — DESIGN AND PRODUCT ACCEPTANCE (DETAILS)

### 13.1 Micro-interactions and desktop/mobile polish

- Sidebar collapsible and stable, overlay drawer on mobile, persistent search/filter behavior.
- Tables have correct row-height, ellipsis with accessible tooltip, column alignment, sticky head on large lists without clipping.
- Empty/error/loading states are custom and informative; every visible button either works or is clearly disabled with explanation.
- User actions show appropriate optimistic UI only with rollback on server failure.
- Network failures show retry controls; authorization failures show precise error and remediation.
- `prefers-reduced-motion` respected; subtle CSS transitions, no scroll-trigger gimmicks or parallax.
- Light/dark theme variables with contrast compliance; avoid color-only statuses.
- Dashboard charts use live database values or intentional demo fixture; source/measurement type indicated.
- Accessibility: focus visibility, keyboard shortcuts where helpful, screen reader names, modal focus restore, native controls.

### 13.2 German copy examples

- Empty Leads: `Noch keine Kontakte. Importiere eine CSV-Datei oder starte deine erste Lead Discovery.`
- Missing LinkedIn: `LinkedIn ist noch nicht verbunden. Verbinde dein Profil, um freigegebene Beiträge zu veröffentlichen.`
- Missing scope: `Diese Funktion ist mit den aktuell gewährten LinkedIn-Berechtigungen nicht verfügbar.`
- Blocked outreach: `Versand gesperrt: Es fehlt ein dokumentierter zulässiger Werbekontakt-Nachweis.`
- AI offline: `Demo-Vorschlag: Kein KI-Anbieter verbunden. Verbinde einen API-Schlüssel für echte KI-Generierung.`
- Discovery demo: `Beispieldaten: Diese Unternehmen sind synthetisch und wurden nicht recherchiert.`
- Need approval: `Dieser Beitrag wurde nach der Freigabe bearbeitet und muss erneut geprüft werden.`
- Import missing domain: `Keine Domain vorhanden – der Kontakt kann trotzdem importiert werden.`

### 13.3 UX for the commercial product

- Fast first-time value: a small business can import leads or create a social post within minutes.
- Explanatory tooltips for ICP scores and unknown data.
- Clear source provenance and compliance states instead of obscure developer terminology.
- Setup page with missing provider credentials, connection status and instructions; no red stack traces to end users.
- Usage meters to prevent surprises; avoid manipulative dark patterns.

---

## 14 — IMPLEMENTATION STEPS / BACKLOG WITH ACCEPTANCE CRITERIA

Commit work in coherent stages with descriptive messages. If Codex can run subagents/parallel tasks safely, delegate independent bounded modules, but keep central schema/API contracts and perform integration review. Do not run multiple independent agents editing the same files simultaneously without coordination.

### EPIC 0: Project bootstrap (P0)

- `PRO-001` Initialize monorepo, scripts and pinned dependencies.
- `PRO-002` Local stack Docker Compose (Postgres, Redis, MinIO, backend, frontend, worker), health checks, named volumes.
- `PRO-003` ESLint/Prettier, Ruff, Pytest/Vitest/Playwright, Husky/pre-commit if useful, CI.
- `PRO-004` README onboarding in German, architecture docs, `.env.example`, no committed secrets.
- **Gate:** `docker compose up --build` starts core stack, health checks green; frontend loads.

### EPIC 1: Identity, tenant and security (P0)

- `PRO-010` Supabase-ready auth/local dev auth with secure production separation.
- `PRO-011` Workspace onboarding, membership, invites, role checks.
- `PRO-012` Database schema migrations, DB session scope and RLS, cross-tenant tests.
- `PRO-013` Audit, user preferences, policy framework.
- **Gate:** tenant A cannot access tenant B under API, ORM or DB, including assets and jobs.

### EPIC 2: Leads, data and CRM (P0)

- `PRO-020` CSV/XLSX upload, intelligent header mapping, preview/error report.
- `PRO-021` Commit/dedupe/idempotency, safe rollback journal.
- `PRO-022` Contact/company table/detail forms and search, filter, bulk tags.
- `PRO-023` Segments, ICP builder and deterministic scoring.
- `PRO-024` Pipeline/activities/tasks and basic deal analytics.
- **Gate:** synthetic 773-row fixture imports with no email, displays properly, reimport avoids duplicates.

### EPIC 3: Discovery & evidence (P0)

- `PRO-030` Typed discovery query and provider abstractions.
- `PRO-031` Licensed provider integration where verified and configured; otherwise clearly disabled.
- `PRO-032` Synthetic demo provider and UI; separate test env only.
- `PRO-033` Company website research with restrictions, evidence persistence, source review.
- `PRO-034` Async discovery execution, cancel/retry, import selected, source metadata.
- **Gate:** search → results → choose → import → score, with honest provider state.

### EPIC 4: AI and outreach (P0)

- `PRO-040` LLM Gateway, schemas, budgets and prompt registry.
- `PRO-041` Research summaries, outreach draft variants with citations.
- `PRO-042` Campaign builder, enrollment, steps and approvals.
- `PRO-043` Manual LinkedIn handoff, copy draft, timeline and follow-up tasks.
- `PRO-044` Consent/suppression/policy gates; no send from draft creation.
- **Gate:** personalized draft from proven facts, manual action tracked, unlawful send blocked.

### EPIC 5: Social Studio (P0)

- `PRO-050` Brand kit, voice, content pillars and idea management.
- `PRO-051` Caption generation: 3 variants, rewrite, save/edit.
- `PRO-052` Asset upload/private storage + template visual generation + optional AI image provider.
- `PRO-053` Social post editor with image, alt text and LinkedIn preview.
- `PRO-054` Content calendar with schedule, state, timezone and approval revisions.
- **Gate:** create professional post+real asset, approve and schedule, visible in calendar.

### EPIC 6: LinkedIn official publishing (P1, API access conditional)

- `PRO-060` OAuth flow with safe callbacks, encryption and capability negotiation.
- `PRO-061` Official media upload + post publishing adapter using verified current API.
- `PRO-062` Job dispatch/lease/idempotency/ambiguous result handling, audit.
- `PRO-063` Capability-driven content/engagement UI and reconnect handling.
- **Gate:** real post only if official access configured; test fake provider proves full publish cycle without external credentials.

### EPIC 7: SaaS hardening (P1)

- `PRO-070` Billing models, usage plans, optional Stripe if configured; safe free test mode.
- `PRO-071` Analytics from real events, source labels, cost/credits.
- `PRO-072` Privacy export/deletion and retention cleanup.
- `PRO-073` Monitoring, runbooks, security/readiness check.
- **Gate:** external pilot readiness checklist with pass/fail and blockers.

### EPIC 8: QA polish (P0 continuous)

- `PRO-080` Fix flaky/test errors, E2E major flows, mobile/a11y/performance review.
- `PRO-081` Audit that no visible control is fake/broken; every route useful.
- `PRO-082` README and handover `docs/STATUS.md` generated from actual code and test observations.

---

## 15 — REPOSITORY DOCUMENTS YOU MUST CREATE

1. `README.md` — concise overview, local bootstrap commands, architecture, screenshots only if generated from actual running app, dev mode behavior, real integration setup, deployment notes.
2. `AGENTS.md` — repo agent rules, module boundaries, standards, commands, safety constraints and branch workflow.
3. `docs/IMPLEMENTATION_PLAN.md` — phase execution and acceptance gate status.
4. `docs/ARCHITECTURE.md` — components, data flow, tenant isolation, job architecture, trade-offs.
5. `docs/DATA_MODEL.md` — tables, relationships, unique constraints, indexes, RLS and migration strategy.
6. `docs/API.md` — endpoint list, auth, errors, pagination, example payloads, generated OpenAPI reference.
7. `docs/DESIGN_SYSTEM.md` — token palette, typography, component guidelines, interaction/accessibility requirements.
8. `docs/LINKEDIN_INTEGRATION.md` — developer app setup, OAuth redirect, products/scopes, limitations, current API versions, required approvals, token security, rate limits and exact missing prerequisites.
9. `docs/LEAD_DISCOVERY.md` — providers, data-license checklist, compliant sources, attribution, search cost and privacy.
10. `docs/AI_AND_PROMPTS.md` — model abstraction, prompt registry, eval examples, output schemas, costs, hallucination policy.
11. `docs/COMPLIANCE_CHECKLIST.md` — GDPR/UWG/ToS operational controls, legal review gates, limitations.
12. `docs/SECURITY.md` — auth, RBAC, RLS, encryption, threat model, incident and retention policies.
13. `docs/TESTING.md` — test matrix, commands, seed data policy, documented pass/fail.
14. `docs/OPERATIONS.md` — deployment, backup/restore, cron, worker failures, token/key rotation, health and alerts.
15. `docs/STATUS.md` — honest completion matrix; actual implemented / mock/demo only / blocked by keys / blocked by provider approval / known bugs; prioritized next tickets.
16. `docs/DECISIONS.md` — architecture decision log, including any deviation from this master brief.
17. `.env.example` — complete variable names and descriptions, no real secret values.
18. `Makefile` or root scripts — `dev`, `test`, `lint`, `typecheck`, `build`, `seed:demo`, `db:migrate`, `smoke`.

Use current official documentation for external integrations when possible, and put URLs/dates in docs. Useful reference starting points (verify current state):

- LinkedIn prohibited automation: `https://www.linkedin.com/help/linkedin/answer/a1341387`
- LinkedIn Share on LinkedIn: `https://learn.microsoft.com/linkedin/consumer/integrations/self-serve/share-on-linkedin`
- LinkedIn official developer API terms: `https://developer.linkedin.com/legal`
- LinkedIn Marketing Posts API: `https://learn.microsoft.com/linkedin/marketing/community-management/shares/posts-api`
- OpenAI Codex cloud/agent setup: `https://help.openai.com/en/articles/20001545-using-codex-cloud`

---

## 16 — FIRST-RUN REQUIREMENTS AND DELIVERABLE REPORT

### 16.1 Initial environment commands (adjust to repo)

- Establish lockfiles; ensure supported Node/Python versions.
- Create database migrations before serving APIs.
- Create local compose and sample `.env.example`.
- Run `docker compose up --build -d` if Docker is available. If Docker not available in agent environment, run component-level checks and report precisely.
- Run migrations, synthetic seed, unit tests, build, E2E if supported.
- Record exact command outputs summaries: passed / failed / not run with reasons. Do not claim pass without executing.

### 16.2 Optional real CleanStar CSV

If the user later supplies a local file in the repository or uploads it into the Codex environment, import through the app. **Never commit the CSV, contact rows or copies of personally identifying lead data into Git.** Keep it under ignored `data/private/` only as temporary dev file after explicit user action and lawful provenance review. For tests use **synthetic 773-row fixture** with matching columns and intentional blanks.

### 16.3 Expected final Codex response

When your code modifications are complete, respond with:

1. **What actually works** (screens, APIs and sample flows, brief).
2. **Repository changes** (major paths/components and migrations).
3. **How to run** (exact commands and URL).
4. **Tests executed** (numbers, pass/fail and environment limitations).
5. **Which integrations are real vs demo/disabled** (especially LinkedIn, paid discovery provider, AI image generator, Stripe).
6. **Security/compliance caveats and blockers** (specific, no vague claims).
7. **Remaining backlog** ranked by impact and feasibility.
8. **Branch/commit/PR reference** if generated.

Do not announce completion of items not built. Do not merely claim a working SaaS because static webpages render. Code, tests and honest state matter more than marketing copy.

---

## 17 — FINAL DIRECTIVE: START IMPLEMENTING NOW

**Proceed immediately.** Inspect the repository, create the implementation plan and then execute the work in priority order. Make reasonable technical decisions without repeatedly asking questions. Treat this prompt as the authoritative product specification for an initial build. Aim to deliver the most polished **functioning** product surface and the deepest real backend integration reasonably possible within one Codex session. Every external integration must degrade gracefully and transparently when credentials or approvals are missing. Favor a deployable, testable, secure vertical-slice application over superficial breadth.

**BUILD PROSPECTOS.**
