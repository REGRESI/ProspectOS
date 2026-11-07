# ProspectOS implementation status — 2026-11-02

This extends `d103f23` on `feat/prospectos-local-pilot`; the original application was preserved. It is a substantially expanded MVP, **not a production release or a claim that paid providers have been connected**. The original supplied specification is retained as `CODEX_MASTER_PROMPT.md`.

| Area | Implemented | Verification / remaining boundary |
| --- | --- | --- |
| PostgreSQL | Additive Alembic 0001–0007, tenant RLS, composite FKs, runtime non-owner role, append-only audit/revisions | Fresh upgrade/downgrade/upgrade and regression suite; production backup/restore still needs operational validation |
| Identity | Supabase password exchange, verified RSA/EC JWKS, issuer/audience/expiry/email checks, provider-bound short opaque sessions, CSRF, durable login throttling | Signed-token and mocked HTTP tests. Real Supabase project, HTTPS, asymmetric signing configuration and delivery required. Signup/recovery/MFA/refresh UI not implemented |
| Team | Owner/admin/editor/approver/analyst checks, hashed expiring one-time invitations, email-bound acceptance, role/last-owner safeguards | API tests; invitations are manually delivered, team/roles and manual invitation issuance UI implemented; no invitation-email or acceptance UI |
| Imports/contacts | Existing mapping/preview, Unicode/BOM/delimiters, deduplication, rollback conflicts, CRUD/search/pagination; optional durable import queue | Original 773-row workflow retained. Bounded CSV only; XLSX, complete 14-field preservation, full company rollback and large streamed imports remain open |
| Companies/scoring | Exact provider/company identities, licensed-company provenance, configurable deterministic ICP factors and missing-evidence disclosure | No inferred emails, firm size or purchase intent. No fuzzy person merge or predictive scoring |
| Discovery | Structured provider search and natural-language briefing UI, durable jobs, synthetic fixtures, concrete licensed PDL company adapter, attributed import | PDL credentials, approved license/use case and egress required. Briefing is stored, not falsely interpreted as verified criteria. No licensed people search |
| Research | Exact reviewed-domain allowlist, robots, response/DNS checks, bounded text and source IDs | Disabled without terms approval AND an independently enforced private-IP egress guard; no arbitrary safe-crawling claim |
| AI | Configurable OpenAI-compatible structured text, source-ID validation, unverified-claim flags, usage ledger, USD-cent reservations/limits, explicit unavailable/errors | Real LLM key/model/current prices/egress required. No live provider output verified. Offline templates stay separately labelled |
| Media/brands | Private raster upload, pixel/byte limits, SVG rejection, metadata-stripping JPEG re-encode, tenant-authorized access, rights/alt text, brand profiles and composer selection | Local persistent private filesystem volume; real review-gated image generation adapter implemented; S3 and malware scanning remain open |
| Social | Existing editor/calendar/review retained; immutable revision snapshots, media approval invalidation; official OAuth and text/image adapters; capability-gated connect/publish UI; durable publication authorization and quota | LinkedIn app products/scopes, current API version, encrypted token key and egress required. Live OAuth/post/image delivery unverified; no fake receipts |
| Automation | Explicitly authorized approved revision jobs, configurable manual/authorized-auto policy, UTC daily limit, actor/policy/scope/revision checks at dispatch | Internal `/schedule` remains editorial only. Actual publishing requires separate authorization. No blind retry after uncertain side effects; manual reconciliation remains necessary |
| CRM/campaigns | Persisted pipeline, tasks, notes, selected audiences, campaign status, offline drafts and activity audit | Saved validated filters/segments, sequence planning and manual-handoff taxonomy implemented; automated sequence dispatch/reminders and full analytics remain incomplete |
| Email | Resend adapter, separately approved revisions, reviewed provenance, documented unexpired basis, suppression checks again at dispatch, durable job/idempotency | Provider/domain setup and explicit send enablement required; provider acceptance is not confirmed delivery. Email approval/send is API-only. No LinkedIn DM/connection automation |
| Billing | Stripe test checkout/portal adapters, raw-body signature and timestamp verification, unique event ledger, subscription-derived limits | Test credentials/prices/webhooks/egress required. No live payments. Production ordering/reconciliation, invoices remain open; test billing UI implemented |
| Limits/privacy | Contact/asset limits enforced server-side; AI budget; owner/admin export excluding credentials; subject deletion removes derived contact records and redacts associated job payloads | Export/deletion APIs are bounded synchronous workflows. Complete retention, workspace erasure, backup deletion, all historical free-text PII discovery and DPA processes remain open |
| Operations | Isolated migrator, unprivileged API/worker, private shared media volume, standalone web image, safe route-template/request-ID logs, durable job failures, deployment example and CI | Production configuration validated structurally, not deployed. No full observability platform, penetration test, DR proof or production certification |

## Product experience upgrade

The existing production MVP at `489e618` is incrementally extended on `feat/prospectos-experience-workflows`. [EXPERIENCE_UPGRADE.md](EXPERIENCE_UPGRADE.md) is the detailed current product matrix. Implemented additions include operational home, journey navigation, saved Discovery searches/confirmed query interpretation, selective attributed import, lead filters/segments/bulk actions, real company counts/details, structured reusable ICP profiles, campaign sequence planning/review inbox/manual handoffs, real AI variants/images with review gates, calendar revisions/rescheduling, manual engagement, CRM filtering/list/drag-drop/context, guided onboarding/team/test-billing/provider checks. All new customer tables use RLS. Existing functionality and tests are retained.

Company discovery has no licensed people search, radius or seniority support; unsupported filters are disclosed. Sequence delays are editorial planning, not automatic sends. Complete AI-to-campaign attachment, deal owner/close-date fields and full consent management UI remain unfinished. Provider-dependent behavior is implemented through adapters and transport-mocked tests; no live access is claimed.

## Integration truthfulness

No real external provider credentials were supplied. Official provider-owned GitHub SDK sources were available; several documentation sites returned policy-denied HTTP 403. Transport-mocked tests verify request/response handling, not provider approval, paid API access or live delivery. Missing credentials and scopes deny the operation. Synthetic discovery is restricted to development/test; existing scheduled editorial posts do not become live publication jobs.

## Highest-priority remaining work

1. Configure and verify Supabase, approved LinkedIn products, operator-owned provider credentials and exact egress domains in a controlled test environment. Exercise real OAuth, token expiry/revoke, official image processing and receipt reconciliation before enabling publication.
2. Production security/operations review: backup restore, migration permissions, retention/DPA, distributed fairness, metrics/alerts, full CSP and accessibility audit. Implement account signup/recovery/MFA and invitation acceptance flows.
3. S3-backed storage, malware scanning, provider invoice reconciliation, richer brand history, full consent revocation/suppression UI and scheduled email sequences.
4. Full XLSX/staged import journaling, large-data performance, research-to-company evidence normalization and licensed people data only if the contract permits it.
5. Stripe event ordering/reconciliation, privacy workflows across all free-text/history/backups, English message catalog and comprehensive analytics.

See TESTING.md for observed checks. No environment publication or production deployment was performed in this task. The new `feat/prospectos-experience-workflows` branch was pushed normally from `feat/prospectos-production-mvp` (implementation `0d4fe20`). Draft-PR creation against that base returned GitHub GraphQL Forbidden. The existing pilot Pages workflow was preserved and not triggered by this branch. Details: MASTER_AUDIT.md.

## Social Studio V2

`feat/social-studio-v2` extends the experience branch (`8b92928`) with reusable structured voice profiles and labeled examples, source-bound generation controls, distinct variant angles, inherited-context refinements and persistent comparison/history, all five image source modes, searchable private gallery thumbnails/metadata, transparent automatic/random selection, extended image prompt/format controls, provenance and preview, draft duplication/archive and responsive media controls. Additive migration `0008` preserves the existing RLS, composite tenant references, durable paid jobs, cost ledger and approval/publishing gates. Details and exact local commands: [SOCIAL_STUDIO_V2.md](SOCIAL_STUDIO_V2.md).

Real provider output and qualitative improvements remain credential-gated and unverified live. No simulated provider successes or automatic publication were added. Metadata matching is disclosed as lexical matching, not image understanding; no-match fallback is explicit. Voice examples (up to three) are style references only. Existing offline templates remain clearly labeled. Latest 30 text jobs are browsable; full retention/workspace erasure, unlimited history, visual embeddings, production provider validation and accessibility certification remain deferred. No public deployment is authorized or performed.

## Internal Sales Agent V1 slice — 2026-11-04

Branch `claude/inspiring-meitner-vf8sut` (fast-forwarded from `feat/social-studio-v2` `56f14d9`). Detailed log: [CLAUDE_WORK_LOG.md](CLAUDE_WORK_LOG.md). Migrations `0009`–`0011` are additive with RLS and composite tenant FKs.

### Implemented and tested locally

| Area | What works | Verification |
| --- | --- | --- |
| OSM discovery | Nominatim geocode (per-workspace cache), Overpass radius search over 18 curated sales categories, keyword name filter, ODbL attribution + object URL per result, node/way merge, no person/phone/e-mail data | Transport-mocked unit + API tests; UI E2E for source disclosure |
| Deduplication | Existing companies matched by provider identity, website domain, normalized name + place, each with a reason; import links probable duplicates instead of creating new records | API tests |
| Company ICP fit | Radius distance, category, unknown size disclosed; role factor excluded (no contact person) and disclosed | API tests |
| Evidence | Cited company facts (OSM/provider on import, manual with HTTPS source, verbatim website excerpts bound to the company domain) | API + E2E |
| Drafts | Evidence-template personalization (≤ 2 ranked facts, citation snapshot); AI personalization jobs with budget reservation and citation-ID validation; contacts without evidence skipped | API tests (AI with injected generation result), E2E for evidence path |
| LinkedIn workflow | Approval-gated connection/message actions with suppression, enrollment, one-use drafts, connect-before-message, no repeat after decline, daily/weekly pacing; CRM updates (contact status, follow-up task, conversation deal); per-contact sequence progress with next due step | API + E2E |

### Demo / simulated

- **LinkedIn simulator**: synthetic personas only (accept+reply, accept, decline, ignore), resolved by the durable worker after `LINKEDIN_SIM_DELAY_SECONDS`. Nothing is sent to LinkedIn; DB constraint ties `simulated` to the simulator channel. Enabled by default only in development/test.
- **Manual handoff**: real contacts get a handoff package; outcomes are self-reported and audited, not provider-confirmed.

### Disabled / gated

- OSM discovery requires `OSM_DISCOVERY_ENABLED=true` and an operator `OSM_CONTACT`. **Not verified live:** `nominatim.openstreetmap.org` / `overpass-api.de` were blocked by this environment's network policy (HTTP 403 at the proxy). Public instances have strict usage policies; heavy use needs a self-hosted or commercial endpoint (`OSM_NOMINATIM_URL`, `OSM_OVERPASS_URL`).
- AI personalization requires LLM credentials and token prices; no live model output was verified.
- Website research remains fail-closed without terms approval and an independent egress guard.
- **Official LinkedIn connection/DM sending is refused.** LinkedIn provides no generally available API for member invitations or messages; no unofficial endpoints, scraping or browser automation exist.

### Deferred

Automatic dispatch of due sequence steps (due dates are planning only), withdrawing stale simulated/manual requests, OSM result caching across runs, map view, contact-person discovery (not available from OSM), fuzzy company merge UI, evidence review queue across companies, reply ingestion from real channels.

## CleanStar round — 2026-11-04 (branch `claude/cleanstar-sales-v2`)

Legend: **live** = verified with real provider data in this round · **built** = implemented and tested against transport-mocked responses, not live confirmed · **open** = not implemented.

| Milestone | State | Evidence / gap |
| --- | --- | --- |
| M0 Baseline | live | Backend 150 passed (hermetic env), frontend 22 unit, E2E 12/15 (3 env-dependent failures). See CLAUDE_WORK_LOG.md |
| M2 Company discovery | **live (OSM)** · built (North Data) | 2026-11-04: CleanStar search Offenburg 30 km → 200 real OSM results, **197 companies imported with source (OSM URL, ODbL), 3 probable duplicates linked, 0 duplicated**. Data: Geofabrik extract `freiburg-regbez` dated 2026-11-03 (public Overpass refused automated use that day). North Data: no key |
| M3 Website/Impressum research | **live** | 65 real company websites researched: 51 succeeded, 14 failed (8 unreachable, 2 DNS, 2 robots.txt refusal, 2 redirect to foreign domain). **50 companies with Impressum data.** Sample of 10 (seed 20261104): 58/60 values literally on the live page (2 = mailto-only e-mails); semantic review ≈ 7/60 wrong/unclean (1 wrong entity via OSM website tag → county site, 2 label prefixes in company name, 1 technical mailbox) → label-prefix and technical-mailbox fixes added afterwards |
| M4 Qualification & ranking | **live** | Ranking over the 208 real companies with reason per company (e.g. "Übereinstimmung mit ICP-Region: Offenburg; Branche passt: Steuerberatung / office=tax_advisor"), factors, gaps, missing facts, sources. Weakness: OSM categories are coarse (office=company → "Büro", craft=electronics_repair → IT) |
| M5 LinkedIn "Heute" | **partly live** | Real queue built from the real companies (20 requests = daily limit, contacts from Impressum). Brave profile matching live on 10 real contacts: 6 with candidates (4 at confidence 0.85–1.0, 2 name-only at 0.55 → user must check), 4 → LinkedIn search link. Open: the user sends 5 real requests and the measured time per contact (<30 s target) is read from "Ø s pro Kontakt" |
| M7 LinkedIn content | **live** (plan + 4 posts with GPT-Image) | `infra/scripts/live_content.py`: real 6-week plan (12 items, 4 pillars, storyline) and 4 posts with two variants each and a real GPT-Image image attached; ledger 208 → 615 US cents (images booked at cap). Writing profile from Nico's own 3–5 texts not done (no samples supplied); 1 of 4 variants contained an unsupported "Studien zeigen" claim → human approval stays mandatory. Official LinkedIn publishing not live (no app credentials); "Kopieren & LinkedIn öffnen" + `published_manually` |
| M8 Job agent | **live** | Instruction "Finde 40 Firmen im Umkreis von 15 km um Lahr, recherchiere sie, priorisiere sie, bereite eine Kampagne vor und fülle die Tagesliste" ran with confirmation only: 40 hits, 37 new companies, 3 duplicates, 112 cited facts, 40 sites researched (19 with result), ranking, contacts, campaign, in 3:16 min. Found and fixed during live runs: worker lacked import hooks; 'Lahr' geocoded to Lahr/Eifel (now city + ICP region); ranking now focuses on the run's companies |
| M9 Design | built | Flow navigation (Heute, Leads, Kampagnen, Content, CRM, Einstellungen), tokens incl. spacing/radius/type, system dark mode + persisted theme, large files split (largest component now ~1.2k lines; CSS in 9 ordered files). Screenshots via `tests/e2e/cleanstar.spec.ts` |
| M6 E-mail outreach | built | SMTP/IMAP mailboxes (app password) with connection test, DNS assistant, ramp-up/rotation/window, legal basis per contact + country rules, bulk approval, one-click unsubscribe, IMAP reply/bounce/complaint detection, auto-pause, real-event metrics. No mailbox credentials → not live. OAuth (Google/Microsoft) and external warm-up service deferred |
| M1 Integrations page | **live (OpenAI, LinkedIn OAuth)** · built (Brave, OSM, North Data tests) | OpenAI: real text + GPT-Image via workspace credentials, ledger booked. LinkedIn: connection established by the user on 2026-11-06 (scopes openid, profile, w_member_social); callback routing fixed, app-credential check verified live (see below). Posting via API not yet exercised |

### Integrations (M1)
- Settings → Integrationen: per-workspace credentials for OpenAI, LinkedIn app, OSM contact, Brave Search, North Data. Fernet-encrypted (`TOKEN_ENCRYPTION_KEY`), masked display, source shown (workspace/environment/missing), status gekoppelt/fehlt/Fehler/nicht geprüft, "Speichern und testen", "Verbindung testen", "Entfernen". Owner/admin only. Environment remains fallback; operator switches (approvals, enable flags, base URLs, cost caps) are environment-only by design.
- Connection tests are read-only: OpenAI `/models/{id}` (text + image model), LinkedIn app probe (invalid code exchange distinguishes `invalid_client`; no token issued), Nominatim `/status`, Brave 1 web query, North Data `suggest` (not billed).
- LinkedIn OAuth callback now redirects to `/settings/integrations?linkedin_connected=1` or `?linkedin_error=…` (cancel) instead of returning JSON.
- `LINKEDIN_API_VERSION=202610` = latest per learn.microsoft.com/linkedin/marketing/versioning (checked 2026-11-04). LinkedIn's official sample app registers `http://localhost:8080/login`; a local `http://localhost:3000/v1/integrations/linkedin/callback` redirect is accepted, no tunnel needed locally.
- Known weakness: image jobs are booked at the configured cap (`IMAGE_MAX_COST_USD_CENTS`), not the actual provider price.

### Company discovery (M2)
- Sources behind one candidate shape (`external_key, company, address, distance_km, source, source_url, license, observed_at, tags`): OSM (Nominatim+Overpass), North Data (register data), PDL, synthetic. A new source only has to emit that shape and declare whether it filters place/radius/category upstream (`upstream_geo`).
- Per run up to 200 results for OSM/North Data (previously 50). Overpass calls back off exponentially on 429/502/503/504 as the public instance requests; Nominatim geocodes are cached per workspace and shared by both sources.
- North Data (`app/providers/northdata.py`): power search with `address` + `maxDistanceKm`, curated WZ codes per category, paging via `nextPos`, one concurrent search, `censor=true`, `blocked` records/persons dropped, only `register.uniqueKey` stored (internal id never). Import adds cited facts Rechtsform, Handelsregister, Vertretung (Registerangabe), Adresse with the North Data URL. Gated by key + `NORTHDATA_ENABLED=true` + `NORTHDATA_LICENSE_APPROVED=true` (no public licence/pricing page retrievable; operator must attest the contract). Billing per unique company per month (user guide, Appendix I).
- Dedup unchanged: provider identity → domain → normalized name + place; probable duplicates are linked, never duplicated.
- Coverage script: `infra/scripts/osm_coverage.py Offenburg 30` (one `out count` per category).

### Website & Impressum research (M3)
- `app/providers/web_guard.py`: own egress guard as httpx transport — http/https on default ports only, no IP literals/credentials, DNS resolved in-process and every address must be globally routable (private, loopback, link-local, metadata, CGNAT, multicast, reserved rejected), connection pinned to the validated IP with TLS verified against the hostname (SNI), environment proxies ignored. Live checked: wrong-IP pin fails TLS; `127.0.0.1`, `localhost`, `169.254.169.254`, `10.0.0.1.nip.io` blocked.
- `app/providers/site_research.py`: only the company's own host (www/apex); one cross-domain redirect of the homepage re-binds to the new domain (e.g. .de → .com); robots.txt per host for UA `ProspectOSResearch/1.0 (+OSM_CONTACT)`; ≤4 pages, ≤2 MB read per page (hard cap, prefix evaluated), 10 s timeout, ≥1 s per host. Impressum found via link text/href or common paths (incl. language prefix).
- Extraction is deterministic (no AI): company + legal form, Geschäftsführung/Inhaber/Vorstand/persönlich haftende Gesellschafter (titles stripped, Aufsichtsrat excluded), address, phone, general e-mail (incl. `(at)`/`(dot)`), HRB/HRA, Registergericht, USt-IdNr. Each value keeps source URL + the exact line; stored as company facts `source_kind=website_impressum`, `confidence=extracted`.
- `POST …/companies/research-batch` (≤200, skips researched), `POST …/companies/{id}/research` (site mode when `RESEARCH_ENABLED=true`; legacy single-page path unchanged), `POST …/companies/{id}/profile`: AI profile from stored page texts as numbered sources; only lines citing valid source IDs are stored (`ai_profile`, `ai_summary_cited`, unverified), budget reserved/settled in the ledger.
- UI: "Websites recherchieren (50)" on Unternehmen, "Website & Impressum recherchieren" and "KI-Profil erstellen" in the company evidence panel.

### Ranking (M4)
- Priority = 0.8 × ICP fit (existing deterministic `company_fit_score`: region by municipality/PLZ text match or search radius, industry; unknown = 0 points) + 0.2 × data completeness (Geschäftsführung, Telefon, E-Mail, Adresse, Website, KI-Profil). Existing customers (`is_customer`) and excluded industries (competitors) are removed; `include_excluded=true` shows them with priority 0.
- Each candidate returns a plain-language reason, the factor list, gaps, known/missing facts and up to 6 source URLs. No purchase probability.
- New OSM/WZ categories "Agentur / Marketing" (office=advertising_agency/graphic_design, WZ 73.11/73.12/74.10) and "Öffentliche Verwaltung" (office=government, amenity=townhall, WZ 84.11). ICP locations limit raised 30 → 80.

### LinkedIn day view (M5)
- `POST …/today/build` fills the day from (1) due steps — message after a reported acceptance, follow-up after N days without reply — and (2) new connection requests from the ranking, capped by `LINKEDIN_DAILY/WEEKLY_CONNECTION_LIMIT` minus actual sends; unfinished items carry over. Contacts come from Impressum/register managers (`POST …/contacts/from-impressum`).
- Note ≤ 200 characters (current LinkedIn limit for personalised invitations per several 2026 sources; 300 is outdated), message after acceptance and follow-up are composed only from cited facts (AI profile hooks, industry/location) with sources shown.
- Profile matching: `GET …/contacts/{id}/linkedin-candidates` queries the official Brave Search API (`site:linkedin.com/in "Name" Firma`) and scores name/company/place. **Brave terms (1 Sep 2026, §3(b)(i)) forbid storing results**, so candidates live only in a 10-minute in-memory cache; only the URL the user confirms is stored. Fallback: prefilled LinkedIn people search link.
- "Kopieren & öffnen" copies the text and opens the profile; "Gesendet" (or key G) creates a *manual* LinkedIn action (self-reported, `simulated=false`, never a provider action), sets the contact to contacted, creates the next task and records the user's time per contact. ProspectOS never contacts LinkedIn.
- Checks list "angenommen?"/"geantwortet?" uses the existing manual outcome endpoint; pasted replies are analysed by the LLM into classification, next step (Termin/Besichtigung/Angebot) and a reply suggestion — nothing is sent.

### E-mail outreach (M6)
- Not via Resend (its policy forbids cold outreach and purchased/scraped lists; Resend stays for system mail). Mailboxes: SMTP (465 SSL / 587 STARTTLS) + IMAP 993 with app password, tested on save, encrypted; hosts must resolve to public IPs and connections are pinned (no SSRF).
- Legal basis per contact (`POST …/legal-bases`: consent, existing customer §7 Abs. 3 UWG, recipient request, other) with evidence, optional HTTPS proof URL, country and expiry; allowed types per country in `EMAIL_COUNTRY_RULES` (default DE/AT/fallback). Checked when scheduling and again at dispatch; blocked contacts stay in the campaign with the reason shown. "Vermutete" addresses (source `guessed…`) are never sendable.
- Sending: per-mailbox ramp-up (start limit + daily step up to max), rotation across active mailboxes, Mon–Fri window with random 4–11 min gaps, plain-text body with signature and mandatory sender footer, unsubscribe link plus `List-Unsubscribe` (https + mailto) and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058). Dispatch is marked before SMTP; failures after DATA are ambiguous and never retried.
- IMAP sync classifies replies (In-Reply-To/References), DSN bounces (hard 5.x.x → suppression) and ARF complaints; any of them stops the contact's sequence; mailboxes auto-pause above 5 % bounces or 0.3 % complaints over the last 100 sends. Metrics only from these real events.
- Domain assistant: MX, SPF (exactly one), DKIM (common selectors), DMARC with the missing records shown.
- Deferred: OAuth (Google Workspace/Microsoft 365), external warm-up service API, registrar API for domains.

### LinkedIn content (M7)
- `POST …/content/plans` (goal, audience, 3–4 pillars, posts/week, weeks, optional voice profile): the LLM returns strictly formatted lines; parser enforces pillars, weeks and cadence and keeps the storyline ("roter Faden").
- Per item `POST …/content/plans/{id}/items/{item}/draft`: two variants in the voice profile (settings + up to 5 style examples, raised from 3) and an image idea → Social Studio post draft. `POST …/content/posts/{id}/apply` picks a variant or attaches a reviewed GPT-Image asset (approval reset).
- Publishing: official Posts API path unchanged and capability-gated; otherwise "Kopieren & LinkedIn öffnen" and `POST …/social/posts/{id}/mark-published` → state `published_manually` (self-reported, `provider_post_id` stays empty).

### Job agent and autopilot (M8)
- `POST …/agent/plan` parses an instruction deterministically (count, place or ICP region, radius, steps) and returns steps with cost estimate; `…/confirm` starts a chain of durable `agent_step` jobs (discovery → import → research → AI profiles → ranking → Impressum contacts → campaign → today queue); `…/cancel`; progress and cited results via `GET …/agent/runs/{id}`.
- Morning autopilot `PUT …/agent/autopilot` (owner/admin): the worker checks every 10 min and starts one run per day after the configured hour (Europe/Berlin), only internal steps.
- The agent never sends LinkedIn requests, e-mails or posts; those keep their approvals.

### Design (M9)
- Navigation follows the workflow. Tokens: colours (existing), `--space-1..6` (4/8 px grid), `--radius-*`, `--font-*`; dark mode follows the OS until the user toggles (persisted per browser). New styles use tokens only.
- Files: `journey-workspaces.tsx` → `journey-shared`, `discovery-workbench`, `lead-database`, `company-directory`, `outreach-workbench` (re-exported); `workspace-app.tsx` → shell + `workspace-nav`, `workspace-contacts`, `workspace-modules`; `globals.css` → `app/styles/*.css` imported in the original order.
- Accessibility rules of DESIGN_SYSTEM.md kept (labels, real buttons, focus, reduced motion for the new spinner). No full audit performed.

### LinkedIn OAuth callback and app check — 2026-11-06
- Redirect URL (unchanged, must match LinkedIn "Authorized redirect URLs" and `LINKEDIN_REDIRECT_URI` exactly): `http://localhost:3000/v1/integrations/linkedin/callback`. Previously the web server only proxied `/api/*`, so this URL hit a Next.js 404; `apps/web/next.config.ts` now rewrites exactly this path to the API.
- Every callback outcome redirects to `/settings/integrations` with `linkedin_connected=1` or `linkedin_error=<code>` (cancelled, not signed in, expired/used state, missing role, token exchange rejected, encryption key missing); the page shows a German message. No JSON is returned to the browser; the state is consumed before the token exchange.
- The app must be opened under the same host as the redirect URL (`localhost:3000`, not `127.0.0.1:3000`), because the session cookie is host-bound; the Integrations page warns when the hosts differ.
- App-credential check: the old probe (exchange of an invalid authorization code) was meaningless — live, LinkedIn answers correct and wrong Client ID/Secret identically with `401 invalid_request "authorization code not found"`, and the check treated every 401 as invalid credentials. It now uses token introspection with a dummy token (no token issued, nothing posted): valid → `invalid_access_token` (= client authenticated), wrong secret → `invalid_client`, wrong client id → `invalid_client_id` (all verified live). It also checks that the redirect URL ends with `/v1/integrations/linkedin/callback`.
- Tests: callback success/state reuse/token error/signed out/cancel, rewrite present in `next.config.ts`, probe responses as recorded live, E2E "LinkedIn OAuth return shows a clear message".

## LinkedIn pilot round — 2026-11-06 (branch `claude/cleanstar-sales-v2`)

E-mail excluded. Handover: docs/HANDOVER_2026-11-06.md.

| Item | State | Evidence |
|---|---|---|
| Production workspace | **live** | Migration 0017 `workspaces.kind`; former working workspace promoted to "CleanStar" (production, login default), synthetic rows removed; fresh synthetic demo labelled and banner-marked; demo never resolves stored/env provider credentials, credential save/test, LinkedIn OAuth and publishing refused there |
| Data quality | **live** | `app/data_quality.py`: name ↔ domain ↔ Impressum check stored as fact "Website-Abgleich"; mismatch → Impressum facts "unbestätigt" (no contacts, no completeness). Segments A/B/C/X for office cleaning; ranking 0.5 × Zielgruppe + 0.3 × ICP-Fit + 0.2 × Datenlage (−15 mismatch); X hidden with reason. Live: 116 passt / 6 unstimmig / 9 unklar / 103 ohne Website |
| Heute routine | **live** | Migration 0018: `contacts.outreach_stage`, `outreach_settings` (daily limit 5–10, Du/Sie, sender), queue kind `followup2`. Follow-ups day 3 and day 7; rebuild re-checks unapproved items (hidden companies/closed contacts skipped, texts recomposed, overflow skipped) |
| Writing style | built (no samples yet) | `app/style.py`: samples from `data/private/meine-texte.md` (read-only mount), derived profile synced into a voice profile; hard rules in prompts and enforced on Heute texts, post variants, reply drafts; hint box when empty |
| Content | **live** | 2-week plan, 3 posts/week, 6 posts with 2 variants and a real image, all `needs_review`. Probe-Post + publish readiness (all 6 checks green live). Official API publish not exercised |
| Autopilot Ortenaukreis | **live** | Town rotation (12 km), per-run budget + workspace budget cap paid steps, ledger costs per run; live run Lahr: 30 hits, 8 new companies (7 Kitas). Research skips sites failed in the last 30 days (3 days for transient errors) and hidden companies |
| Setup-Check | **live** | `/settings/setup`: LinkedIn, KI-Text, KI-Bilder, OSM, Brave, Mailbox ("noch nicht verbunden"), Schreibstil, each with one next step |
| Tests | — | Backend 210 passed; frontend lint/typecheck/unit 22; `cleanstar.spec.ts` 6/6 |

Disabled/deferred: mailbox and e-mail sending (Google account pending); North Data (no key); API publishing waits for the user's first probe post.

## Costs, test isolation, design — 2026-11-07 (branch `claude/cleanstar-costs-design`)

Implemented:
- **Actual AI costs:**
  - Reservations (cost caps) are held only while a call runs. Afterwards the ledger books the actual cost in micro-USD, from the response's `usage` field and the price table.
  - Image prices are new env settings: `IMAGE_TEXT_INPUT_USD_PER_MILLION`, `IMAGE_IMAGE_INPUT_USD_PER_MILLION`, `IMAGE_OUTPUT_USD_PER_MILLION`.
  - Unknown outcomes and missing usage are booked as `estimated`.
  - Old bookings were corrected with `python -m app.costs --apply`: November went from 12.22 to 0.16 USD; 16 bookings remain estimated.
  - The UI shows "Verbraucht" and "Reserviert" separately.
  - Migration 0019.
- **Isolated browser tests:**
  - `docker-compose.e2e.yml` runs as its own compose project with a tmpfs database and no provider keys, torn down after each run.
  - `infra/scripts/e2e.sh` starts it; Playwright refuses to run against the dev stack.
  - 86 test workspaces were deleted from the real database (after a dump). Only "CleanStar" and "Demo" remain.
- **Workspace lifecycle:**
  - Rename, archive, and delete (typed name; not the open or the last workspace).
  - The purge function is tenant-bound (migration 0020).
  - Archived workspaces get no autopilot runs.
  - The demo opens only via the Demo switch.
- **Design system and navigation:**
  - Five areas with tabs; Heute is the start page.
  - Firmen and Kontakte are tables with server-side sort.
  - Plain German copy.
  - Report: `docs/design/README.md`.

Demo-only: synthetic discovery, raw-data views, legacy modules (menu "Mehr (Demo)").
Not reworked yet: studio editor, Zielgruppe and Mein Angebot forms, campaign and company detail layouts (they inherit the design tokens only).

## Profiles, content strategy, writing profile, team — 2026-11-07 (branch `claude/cleanstar-linkedin-content`)

Implemented:
- **Verified LinkedIn profiles** (`app/profile_check.py`, migration 0021):
  - Search through the official Brave Search API only; linkedin.com is never called.
  - A hit counts when every name token matches AND the company or the place appears in the hit.
  - Several matching profiles, or a name-only match, count as "unsicher" and are not used.
  - Role search (Facility/Office Manager, Praxismanager, Leitung Verwaltung, Büroleitung) runs for companies without a verified contact. A hit becomes a contact only when the company AND the role appear.
  - Stored are only the profile URL and a reason in ProspectOS' own words. Brave titles and snippets are never stored (decision 2026-11-07; Brave terms §3(b)(i)).
  - Heute takes only contacts with a verified, user-confirmed or user-imported profile. The button copies the note and opens that profile.
  - LinkedIn limits count per user.
- **Email list and data quality:**
  - The email list holds companies without a verified profile that have an address. Each row shows the source (Impressum link or contact) and whether the address is personal or general.
  - Sending stays locked: there is no send button.
  - The data quality page shows counts and a random sample of 20 companies.
- **Content strategy** (`app/content_strategy.py`):
  - Goal, audience and pillar are chosen per post and per plan.
  - Versions A (thesis), B (story) and C (tip with numbers), each with a why sentence.
  - Campaigns have dated slots.
  - Metrics are entered by hand 48 h after posting. Averages per pillar, approach and goal feed into new prompts.
  - Campaign "Die neue CleanStar-Website" exists in CleanStar: 7 slots from 10.11.2026, texts pending.
- **Brand templates** (web only):
  - Number card, quote card, carousel, website in a device frame, before/after.
  - Built from CleanStar fonts, colours and logo (copied from `cleanstar-rebrand`, OFL fonts).
  - Rendered as HTML through SVG foreignObject; export as PNG, or as PDF for the carousel. Templates can be saved to the media library.
  - AI images only on an explicit button.
- **Writing profile per user** (`app/voice_learning.py`):
  - Every draft edit (posts and Heute texts) is stored as original vs. user version.
  - Feedback buttons: "Klingt nach mir" and "Klingt nicht nach mir".
  - Rules are derived deterministically. They are editable, can be switched off, and dismissed rules stay dismissed.
  - Style references are other people's posts, used for rhythm only.
  - Rules and references go into every new prompt of that user.
- **Team** (`app/team.py`):
  - Invite as Inhaber or Mitglied via a one-time link (7 days). There is no system mailing yet, so the link is copied by hand.
  - New users register on `/einladung` (local demo auth only).
  - One LinkedIn connection per user. Contacts get the owner who sent the first request; posts belong to their author.

Not built / deferred:
- Sending invitation emails: no system mailer exists.
- Separate "Heute" lists per user: the queue is shared, and the limits are counted per user.
- Website screenshots are uploaded by hand; ProspectOS does not capture them.
