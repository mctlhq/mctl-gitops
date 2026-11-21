# Design: issue-127-spike-media-competitive-landscape-and-mc

This is a research design. Sections marked RESEARCH describe what the spike produces. Sections marked FUTURE describe what an implementation would look like after an explicit owner GO. Nothing here is built by this proposal.

## Current state

### SeerrSense code and interface inventory (read in the clone, v1.14.4)
- Entry and transports: `src/index.ts` selects stdio or HTTP. `src/api/server.ts` is the Fastify app. It serves `/mcp` (Streamable HTTP, per-session `McpServer`), `GET /api/v1/search` (REST), `/health`/`/healthz`/`/ready`/`/readyz`, and the static pages under `public/`.
- MCP tools (`src/mcp/server.ts`, `createSeerrSenseMcpServer`):
  - `whoami`: identity only.
  - `search_media`: READ_ONLY.
  - `resolve_media`: READ_ONLY, with LLM fallback through `src/api/resolver/intent.ts` (`NebiusIntentExtractor`), capped per subject by `src/api/resolver/budget.ts`.
  - `get_media`: READ_ONLY.
  - `request_media`: WRITE, `readOnlyHint:false`, gated by scope `seerr:request`.

  The issue says "four tools". The four media tools are search/resolve/get/request, and `whoami` is a fifth, identity-only tool used by the aggregate portal (mctlhq/.github#44). Output schemas are deliberately `z.looseObject` so that fields can be added compatibly (mctlhq/.github#64).
- Write path: `src/api/service.ts` `MediaRequestService.requestMediaSafely` re-reads the canonical record (`SeerrClient.getMedia`), refuses unless the status is UNKNOWN, PARTIALLY_AVAILABLE or DELETED, and then calls `POST /api/v1/request`. There is no plan/confirm token. Confirmation relies on the client honouring `readOnlyHint:false`.
- Canonical IDs: `src/core/media.ts` (`MediaCandidateSchema`, TMDB id plus media type and status). `src/core/search.ts` and `src/core/query.ts` handle title normalisation and year parsing. The LLM never produces IDs; candidates are verified through Seerr (README "Core principle").
- Provider: `src/providers/seerr/client.ts` `SeerrClient`. A trusted (household) connection uses `fetchTrusted`. An untrusted (per-user) connection uses `fetchUntrusted` with a pinned DNS dispatcher (`pinnedLookup`), a body size cap and redirect refusal. `src/providers/seerr/guard.ts` blocks private/metadata addresses at submit and at dial time; this is the SSRF protection. Logs carry only the path template (`operationOf`).
- Tenancy: `src/providers/seerr/tenants.ts` `TenantResolver` maps an OAuth subject to `own`, `household` or `none`, with a 60 s cache. On the household Seerr, requests are attributed through `attributedUserId` (`findUserIdByEmail`). Per-user credentials are encrypted (`src/auth/crypto.ts`).
- Auth: `src/auth/routes.ts` (`/oauth/authorize`, `/oauth/token`, `/oauth/revoke`, `/oauth/consent`, DCR client registration) with Google as the IdP (`src/auth/google.ts`). JWT access tokens come from `src/auth/tokens.ts`. Scopes are `seerr:read`, `seerr:request` and `offline_access` (`src/auth/config.ts`). PostgreSQL tables live in `src/auth/store-pg.ts`: oauth_pending_auth, oauth_auth_codes, oauth_refresh_tokens, user_connections, resolve_usage, revoked_sessions, revoked_subjects, oauth_registered_clients.
- Observability: one `mcp_tool_call` record per invocation (`ToolCallRecord`, `instrument`, `recordRejectedArguments`) carries identifiers only and never query text.
- Packaging: `Dockerfile` (node:22-slim, multi-stage, non-root 1000:1000, read-only root FS, no disk writes). `.github/workflows/release-binaries.yml` exists. Licensing is inconsistent: `LICENSE` is MIT while `package.json` says `"license": "ISC"`.
- What SeerrSense does not do today: quality profiles, release selection, indexers, download clients, import/rename, hardlinks, monitoring, or upgrades. All of that lives in Seerr -> Radarr/Sonarr.

### Deployed state checked
- `$MCTL_GITOPS_ROOT/services/labs/seerrsense/values.yaml`:
  - Tenant `labs`, image `ghcr.io/mctlhq/seerrsense:1.14.4` (digest pinned).
  - Hosts `seerrsense.mctl.ai` and `labs-seerrsense.mctl.ai`.
  - Requests 200m/256Mi, limits 500m/512Mi.
  - `SEERR_URL=https://media.mctl.ai` (household Seerr), `SEERRSENSE_LOCALE=ru-RU`, `NEBIUS_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507`, `SEERRSENSE_OPEN_SIGNUP=true`.
  - OAuth client `cloudflare-portal-mcp`, plus DCR redirect URIs for mcp.mctl.ai and the Cloudflare dashboard.
  - DB credentials come from `labs-seerrsense-db-creds`, and a CF Access client id is configured.
- `mctl_get_service_status(labs, seerrsense)`: ArgoCD `labs-seerrsense` is Healthy and Synced, image 1.14.4, `hasDatabase: true`.
- Not observed: the owner's Mac mini, where the household Seerr/Radarr/Sonarr/qBittorrent/Jellyfin run, and their resource use. SeerrSense itself runs in the cluster, not on the Mac mini. Any saving from replacing the *arr stack applies to whatever host runs that stack, and that host is unobserved. See Open questions in requirements.md.

## Proposed solution

### 1. RESEARCH: competitor matrix (initial evidence, 2026-11-21)
Evidence classes: R = released (seen in a tag or release), G = gated (shipped behind a setting or flag), P = planned, U = unknown. "Secondary" means the claim came from an article, an aggregator or a search summary and must be re-verified at a tag or commit (task 1).

| Project | Canonical repo (as found) | License | Lang | Version seen | MCP status | Notes / caveats |
|---|---|---|---|---|---|---|
| HolyArrs | github.com/HolyArrs/HolyArrs | AGPL-3.0 + CLA | Go (go.mod) | Inconsistent: 1.1.0 (12 Nov 2026, secondary), 1.1.3/1.1.4 in docs, "1.2.0" announcement in README; Releases section empty | 1.x guides (bitdoze) say "no MCP". The README 1.2.0 note says "Connect apps over MCP with keys you control". The exact flag is unverified, so G/U | Mostly one maintainer. Claims (secondary) one container replacing Sonarr/Radarr/Lidarr/Bazarr/Prowlarr/Seerr, about 15 MB image, about 140 MiB RAM at 10k titles, port 6262. Uses a maintainer-operated metadata server (XDA 2026-11-19 says it may retain request data). Read-only import from *arr with undo. Says "Seerr ... keep working" (compatibility claim, unverified). Public since 9 Nov 2026, so very young. |
| MediaManager | github.com/maxdorninger/MediaManager | AGPL-3.0 | Python | v1.9.0 tag exists | U (none found) | Covers TV and movies. Replaces Sonarr/Radarr/Overseerr/Jellyseerr. Integrates Prowlarr/Jackett and uses TMDB/TVDB metadata. OIDC/OAuth login. Docker-first, with an API. |
| Mediarium | github.com/rdborg/Mediarium | U | U | 3.3.0 (owner comment in issue #97, 2026-10-21) | G: "Let AI assistants connect (MCP)" setting; admin API key header, no OAuth (open issue) | API-key-only MCP does not fit SeerrSense's OAuth/PKCE model. |
| MovieClaw | github.com/movieclaw/MovieClaw (many mirrors/forks) | MIT up to v0.27.0. After that, a custom "MovieClaw License" (Apache-2.0 plus conditions): non-commercial free, commercial needs written authorization. Source-available, not OSI | Python backend + Node frontend (stated) | Releases not visible | R (stated): every feature via `mclaw` CLI and MCP; per-endpoint revocable tokens; capability selection | Includes a built-in indexer search (Prowlarr replacement) and speaks the Jellyfin playback API. The UI and logs are in Chinese. The commercial restriction is a governance blocker for C. |
| Reelix | ambiguous; likely github.com/demonzoned/Reelix (forks zhu327, TheMightyTRex; unrelated 4444zyf/Reelix "agent-native") | GPL-3.0-or-later | Rust (`target/release/reelix`) | U | U | Covers movies, TV, books and music. Single mount for hardlinks. A Linux installer verifies SHA256SUMS. |
| arr-mcp (family) | bardesss/arr-mcp (probable origin; forks ghostintherack, mathieuletyrant, davidgibbons) and sandraschi/arr-mcp (Python FastMCP), aplaceforallmystuff/mcp-arr (npm `mcp-arr-server`), fx/mcp-arr, CT4nk3r/arrstack-mcp | U per repo | TS (mathieuletyrant: MCP TS SDK, Hono, Zod), Python (sandraschi) | U | R: MCP is the product | These are federated wrappers over the existing *arr APIs, the same pattern as option A. Tool counts reach 131 (davidgibbons/mcp-arr). Typically one API key for the whole stack and no per-person OAuth. |
| Streamline | not found as a media manager (only unrelated streamline-mcp repos for tasks and icons) | n/a | n/a | n/a | n/a | Owner to supply a URL. |
| MediaStack MCP | not found | n/a | n/a | n/a | n/a | Owner to supply a URL. |
| Mediabox MCP | not found | n/a | n/a | n/a | n/a | Owner to supply a URL. |

Primary links used:
- https://github.com/HolyArrs/HolyArrs, https://holyarrs.com/, https://www.bitdoze.com/holyarrs-docker-guide/
- https://www.xda-developers.com/i-replaced-sonarr-radarr-and-lidarr-with-a-single-claude-built-app-and-it-changed-how-i-manage-my-media-server/
- https://github.com/maxdorninger/MediaManager (and /tree/v1.9.0)
- https://github.com/rdborg/Mediarium/issues/97
- https://github.com/movieclaw/MovieClaw
- https://github.com/demonzoned/Reelix
- https://github.com/ghostintherack/arr-mcp, https://github.com/mathieuletyrant/arr-mcp, https://github.com/davidgibbons/arr-mcp, https://github.com/sandraschi/arr-mcp, https://github.com/aplaceforallmystuff/mcp-arr, https://github.com/fx/mcp-arr, https://github.com/CT4nk3r/arrstack-mcp

Gaps: no tag- or commit-level verification was possible in this run (no clone of the competitors). Release cadence, CVE/security-advisory history and SPDX files were not inspected. Task 1 closes these.

Observations that shape the decision:
- Every serious unified backend is copyleft (AGPL-3.0 or GPL-3.0) or source-available (MovieClaw).
- Using one unmodified over its network API (option B) creates no source obligations for SeerrSense. Forking one (option C) and offering it as a network service triggers AGPL section 13.
- None of the unified backends offers OAuth/PKCE per-person MCP with scope separation comparable to SeerrSense. That is SeerrSense's defensible layer in every option.

### 2. RESEARCH: weighted decision matrix (provisional)
Scores run from 1 (poor) to 5 (best). Footprint scores are provisional until the task 4 benchmark runs. No numbers were measured in this run.

| Criterion (weight) | Baseline (do nothing) | A: extend SeerrSense federated | B: integrate unified backend via API | C: fork | D: clean-room engine |
|---|---|---|---|---|---|
| Functional fit (25%) | 2 | 3 | 4 | 4 | 4 (after years) |
| Safety/operability (20%) | 4 | 4 | 2 | 2 | 3 |
| Developer effort (20%, higher = less) | 5 | 4 | 3 | 2 | 1 |
| Resource footprint (15%) | 2 | 2 | 4 (claimed) | 3 | 4 (unmeasured) |
| License/governance (10%) | 5 | 5 | 3 | 2 | 5 |
| Migration/reversibility (10%) | 5 | 5 | 4 | 3 | 3 |
| Weighted total | 3.60 | 3.65 | 3.30 | 2.75 | 3.20 |

Rationale:
- A reuses `SeerrClient`, `guard.ts`, `TenantResolver` and the OAuth stack. It adds read-only adapters (queue, disk and library status from Radarr/Sonarr/qBittorrent/Jellyfin) behind the same per-person binding. It does not reduce the footprint.
- B scores highest on fit and footprint, but HolyArrs is weeks old, has one maintainer, uses a maintainer-operated metadata server and has inconsistent version docs. All of that drags safety and governance down.
- C inherits copyleft and maintenance debt with no upstream path.
- D is the most controllable but costs the most. It re-implements release parsing, quality/upgrade logic and import semantics that Radarr/Sonarr have matured over a decade.

Sensitivity:
- (s1) Doubling the footprint weight to 30% (taking 5 from fit, 5 from effort, 5 from migration) puts B and D level with or slightly above A. The footprint benchmark is therefore the pivotal unknown.
- (s2) Raising safety to 30% makes A and the baseline dominant.
- (s3) If HolyArrs MCP turns out to be gated behind admin API keys only, B's safety drops to 1 (total 3.10).

Verdicts (provisional, for owner review):
- Baseline: acceptable fallback.
- A: GO as the low-risk next step (read-only status adapters first).
- B: CONDITIONAL GO for isolated evaluation only (benchmark plus API/compatibility probe on fixtures). NO-GO for production until it is 6 months or more old, has more than one maintainer or an equivalent governance signal, and a self-hostable or opt-out metadata path is verified.
- C: NO-GO.
- D: NO-GO now. Revisit only if A shows the *arr stack is the binding constraint and B fails its conditions.

### 3. RESEARCH: native replacement scope and complexity (input for D or B)
- Movie lifecycle (Radarr): monitor, search, grab, import, upgrade.
- TV (Sonarr): series/season/episode monitoring, season packs vs single episodes, absolute vs scene numbering, specials.
- Indexers (Prowlarr): Torznab/Newznab caps, categories, rate limits, credential storage.
- Download client: qBittorrent WebAPI v2 adapter (add with category/savepath, poll, ratio/seed handling).
- Library: the Jellyfin API for items, library refresh and watch history.
- Hard parts, each rated high complexity:
  - release normalisation (title/year/edition/resolution/codec/source/group parsing; Russian-language titles and audio labels such as "MVO", "DUB" and "Rus+Eng"; size sanity; seed counts);
  - metadata matching across TMDB/TVDB/IMDb;
  - upgrade policy and cutoff;
  - duplicate detection;
  - retries and backoff with stalled-download handling;
  - disk-space preflight;
  - import via hardlink with cross-device fallback to copy (requires a shared volume path mapping between the downloader and the library, a common failure source);
  - scheduled monitoring (RSS sync);
  - reconciliation after crash (download exists but no DB row, and the reverse).
- Deferred: music, subtitles, playback, transcoding, and a native torrent client.

### 4. FUTURE: component and adapter boundaries
- SeerrSense remains the front door: OAuth, tenants, resolver, MCP tool catalogue, audit records.
- The new `MediaBackend` port in SeerrSense (`src/providers/<backend>/`) has these methods: `search`, `getMedia`, `planAcquisition`, `executePlan`, `getStatus`. `SeerrClient` becomes the first implementation, unchanged in behaviour.
- The engine (option D only, or a HolyArrs adapter for B) sits behind that port. Internal adapters: `IndexerAdapter` (Torznab/Newznab), `DownloadClientAdapter` (qBittorrent), `LibraryAdapter` (Jellyfin), `MetadataAdapter` (TMDB).
- Deployment alternatives:
  - T1 (default): the hosted MCP control plane (the existing labs/seerrsense) plus a locally deployed execution agent on the Mac mini that dials out (no inbound port, no home-service exposure). The agent fetches signed plans and posts status.
  - T2: fully self-hosted. SeerrSense and the engine both run on the Mac mini, and clients reach them over a tailnet or stdio.
  - In both, existing production SeerrSense clients keep talking to the same four media tools plus `whoami`.
- Storage: SQLite in WAL mode on local disk for a single-host engine, with PostgreSQL optional for the hosted control plane (which already exists). SQLite still needs a single-writer discipline, fsync-safe volumes (not network shares), online backup (`.backup` or litestream) and restore drills. Neither SQLite nor a monolith removes lock or corruption risk.
- Language: TypeScript is preferred for anything in SeerrSense (reuse of zod schemas, guard and auth). Go is the candidate for a standalone execution agent or engine (single static binary, low RSS); it is to be validated by the task 4 benchmark. Rust is not justified at this stage: no hot path needs it, and it would add a third toolchain.

### 5. FUTURE: MCP write-tool safety model
1. Intent comes in. `resolve_media` produces a verified TMDB id (existing behaviour).
2. A new read tool, `plan_acquisition`, returns a deterministic plan containing: media, release choice with reasons, target path, space check, and `plan_digest`.
3. The plan carries a confirmation grant: an opaque single-use token bound to (subject, tenant, plan_digest, expiry ≤ 10 min). It is stored hashed, like the refresh tokens in `store-pg.ts`.
4. A new write tool, `execute_plan(grant)`, is idempotent per grant. A replay returns the original result, and a reused grant with a different digest is refused.
5. `get_acquisition_status` reports progress.

Further rules:
- New scopes (for example `media:plan` and `media:execute`) are additive. `seerr:read`/`seerr:request` semantics and the existing token flows stay unchanged.
- Revocation reuses `revoked_sessions`/`revoked_subjects`.
- Every untrusted metadata string (release titles, indexer descriptions) is treated as data. It is never interpolated into tool descriptions, and it is length-capped and stripped of control characters in outputs to limit prompt injection.
- Indexer and downloader URLs pass through the same `guard.ts` checks when they are user-supplied (in T1 the local agent dials them, so the hosted plane never dials home addresses).
- Rate limits reuse `@fastify/rate-limit`, plus a per-subject daily execution budget modelled on `resolve_usage`.
- Audit uses `ToolCallRecord` extended with plan and grant identifiers, never titles.

### 6. FUTURE: first vertical slice (fixtures only)
1. Resolve the public-domain title "Night of the Living Dead (1968)" via a stubbed metadata fixture.
2. Check the library through a Jellyfin mock: absent.
3. Query a synthetic Torznab fixture server that returns crafted XML with 4 releases: wrong language, wrong quality, oversized, and the correct one.
4. `plan_acquisition` picks the correct release and runs a space check against a tmpfs quota.
5. Confirm with a grant.
6. A mock qBittorrent (HTTP stub that "completes" by writing a small synthetic file) handles the download.
7. Import by hardlink into a temp library dir.
8. The Jellyfin mock shows the item, and `get_acquisition_status` returns `imported`.

No real indexer, tracker or copyrighted content is touched. Negative tests are listed in tasks.md.

### 7. RESEARCH: benchmark methodology (task 4)
- Same host, the owner's Mac mini, with its baseline recorded first: RAM, macOS version, Colima vs Docker Desktop vs native, and swap.
- Same pinned versions and digests, and the same synthetic library (for example 500 movies and 50 series of zero-byte or tiny fixture files plus metadata fixtures).
- Measure:
  - idle RSS/CPU after 10 min;
  - active RSS/CPU during a scripted search and import loop;
  - VM overhead, as Colima VM RSS measured separately from container RSS;
  - image size uncompressed vs compressed (registry);
  - search latency p50/p95;
  - pipeline success rate on fixtures;
  - recovery time after `kill -9` mid-import and after disk-full.
- Compare: current stack (Seerr+Radarr+Sonarr+Prowlarr) vs HolyArrs vs (later) the D prototype, each in an isolated compose project with no access to household volumes.
- Record raw outputs and label each number "measured (host, date, version)" or "upstream claim (link)".

### 8. Effort and risk ranges (assumptions: one engineer, existing CI)
- A (read-only status adapters, 3 backends): 2-4 weeks. Risk is low.
- B (isolated evaluation, then a `HolyArrsBackend` adapter behind `MediaBackend`): evaluation takes 1-2 weeks, and the adapter takes 3-6 weeks. Risk is medium-high, driven by upstream volatility.
- C: 8-16 weeks to stabilise a fork, plus ongoing merge cost. Risk is high.
- D: the MVP (movies only, one indexer, qBittorrent, Jellyfin, fixtures) takes 10-20 weeks. Parity with TV season packs and upgrades takes 6-12 months or more. Risk is high.

Gaps:
- P1: owner hardware baseline; HolyArrs MCP/API verification at a tag; the plan/grant model design review.
- P2: Russian release-label corpus (synthetic); shared-volume path mapping on macOS/Colima.
- P3: Seerr multi-user approval parity; music and subtitles.

PDLC metrics:
- request-to-available success rate;
- mis-grab rate (wrong language/quality);
- confirmation abandonment;
- RSS on the host;
- p95 tool latency;
- incidents per month.

Early-user research questions:
- Which *arr features do you actually use?
- Is approval by a household admin required?
- What language/audio preferences apply per person?
- Would a local agent on the Mac mini be acceptable?

### 9. Repository recommendation
A separate `mctlhq/mctl-media` repo is not warranted now. Option A lives in seerrsense. It becomes warranted only when D, or a standalone Go execution agent for T1, gets an owner GO. Its own release cadence, license choice and runtime host justify separation at that point. This spike does not create it.

## Alternatives
- Skip the research and adopt HolyArrs directly (as the XDA article did). Dropped: the project is weeks old, the version docs disagree, the MCP status is unclear, and a maintainer-operated metadata server is involved. The issue requires evidence before adoption.
- Adopt an arr-mcp server instead of SeerrSense. Dropped: those servers are single-API-key wrappers without per-person OAuth, scope separation or SSRF guards. That would regress SeerrSense's security model (`guard.ts`, `tenants.ts`, `auth/*`).
- Fork MediaManager or Reelix as the engine (option C). Dropped for now: copyleft obligations if network-served, Python/Rust stacks that differ from SeerrSense, and no upstream path. It is kept in the matrix for completeness.

## Platform impact
- Migrations: none. This proposal changes no code, schema or gitops file. Future schema additions (grants, plans) would be additive tables in `store-pg.ts`, following its `CREATE TABLE IF NOT EXISTS` convention.
- Backward compatibility: the existing tool names, schemas (open `looseObject`), annotations, scopes and OAuth flows are frozen by requirement. New capabilities are additive tools and scopes only.
- Resource impact: none in the cluster. The benchmark runs only on isolated local fixtures.
- Risks and mitigations:
  - Stale evidence in a fast-moving space: date-stamp every row and re-verify at tag (task 1).
  - Benchmark misinterpretation: separate measured numbers from claims, and record VM overhead separately.
  - Accidental contact with real content or household data: fixtures only, isolated compose network, no household volume mounts.
  - License contamination: B only over the network API, never by vendoring code; resolve the MIT/ISC inconsistency before any combination.
