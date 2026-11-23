# Design: issue-127-spike-media-competitive-landscape-and-mc

Revision 2. This is a research design. The sections are labelled:
- RESEARCH (delivered here): content this proposal delivers now.
- EXPERIMENT (proposed next, isolated): a test for the owner to authorise.
- FUTURE (only after owner GO): implementation shape.

Nothing in this proposal is built, deployed or run against household systems. Evidence ids (E1...) refer to the Evidence annex at the end. Every resource figure is an upstream claim or unknown. None was measured.

## Current state

### SeerrSense inventory (read in the clone, commit da0c5a3, v1.14.4)
- Transports: `src/index.ts` selects stdio or HTTP. `src/api/server.ts` is the Fastify app. It serves `/mcp` (Streamable HTTP, a per-session `McpServer`), REST `GET /api/v1/search`, health and readiness routes, and `public/`.
- MCP tools, from `createSeerrSenseMcpServer` in `src/mcp/server.ts`:
  - `whoami`: identity only, first on the portal allowlist.
  - `search_media`, `resolve_media`, `get_media`: all `READ_ONLY`.
  - `request_media`: `WRITE`, `readOnlyHint:false`. It checks `SCOPE_REQUEST` itself.

  The issue's "four tools" are the four media tools. `whoami` is a fifth, identity-only tool. Output schemas are `z.looseObject`, so fields can be added compatibly (mctlhq/.github#64).
- Write path: `MediaRequestService.requestMediaSafely` (`src/api/service.ts`) re-reads the canonical record and refuses unless the title is absent or partial, then files `POST /api/v1/request`. There is no server-side plan or approval object. Confirmation relies on the client honouring `readOnlyHint:false`. That is a client courtesy, not proof of consent.
- Canonical IDs: `src/core/media.ts` (`MediaCandidateSchema`), `src/core/search.ts`, `src/core/query.ts`. The LLM in `src/api/resolver/intent.ts` (`NebiusIntentExtractor`) extracts intent but never mints IDs. Its cost is capped per subject by `src/api/resolver/budget.ts`.
- Provider and SSRF:
  - `SeerrClient` (`src/providers/seerr/client.ts`) splits trusted from untrusted fetches. The untrusted path pins DNS (`pinnedLookup`), caps body size and refuses redirects.
  - `src/providers/seerr/guard.ts` (`isBlockedAddress`, `assertPublicSeerrUrl`) blocks private and metadata addresses at submit time and at dial time.
  - Logs carry only path templates (`operationOf`).
- Tenancy: `TenantResolver` (`src/providers/seerr/tenants.ts`) maps an OAuth subject to `own`, `household` or `none`. Household requests are attributed through `attributedUserId` (`findUserIdByEmail`). Per-user Seerr keys are sealed by `src/auth/crypto.ts`.
- Auth (door 1):
  - Endpoints in `src/auth/routes.ts`: authorize, token, revoke, consent and DCR. Google is the IdP (`src/auth/google.ts`), and JWTs are issued by `src/auth/tokens.ts`.
  - Scopes are `seerr:read`, `seerr:request` and `offline_access` (`src/auth/config.ts:14-16`).
  - PostgreSQL tables (`src/auth/store-pg.ts`, all `CREATE TABLE IF NOT EXISTS`): `oauth_pending_auth`, `oauth_auth_codes`, `oauth_refresh_tokens`, `user_connections`, `resolve_usage`, `revoked_sessions`, `revoked_subjects`, `oauth_registered_clients`.
- Audit: one `mcp_tool_call` `ToolCallRecord` per invocation (`src/mcp/server.ts:224`), with identifiers only.
- Packaging:
  - `Dockerfile` builds from node:22-slim, multi-stage, as uid 1000, with a read-only root and no disk writes.
  - `.github/workflows/release-binaries.yml` builds Bun single-file executables on tag. A single-binary distribution path already exists for TypeScript.
- License metadata mismatch, verified: `LICENSE` is "MIT License, Copyright (c) 2026 mctlhq", and `package.json` says `"license": "ISC"`.
- Not in SeerrSense today: quality profiles, release selection, indexers, download clients, import, hardlinks, monitoring, upgrades.

### Identity context (#120, epic mctlhq/.github#236)
#120 ("MCP identity I2: second door for mctl-api tokens", OPEN, draft, not started) keeps door 1, Google OAuth at seerrsense.mctl.ai, unchanged. It adds door 2: mctl-api access tokens with `aud=https://seerrsense.mctl.ai/mcp`, verified offline against `https://api.mctl.ai/.well-known/jwks.json` (issuer pinned, `alg` pinned, `kid` from the set), carrying `sub=prn_...`. It also covers principal mapping, linked revocation, fail-closed behaviour and per-person tool filtering. Epic #236 is "mctl-owned MCP gateway" (OPEN). This spike changes no identity code. Section 6 defines the compatibility tests any future media tool must pass.

### Deployed state checked
- `$MCTL_GITOPS_ROOT/services/labs/seerrsense/values.yaml` (read):
  - tenant `labs`, image `ghcr.io/mctlhq/seerrsense:1.14.4` pinned to digest `sha256:e65663bf...`;
  - hosts `seerrsense.mctl.ai` and `labs-seerrsense.mctl.ai`;
  - requests 200m/256Mi, limits 500m/512Mi;
  - `SEERR_URL=https://media.mctl.ai`, `SEERRSENSE_LOCALE=ru-RU`, `SEERRSENSE_OPEN_SIGNUP="true"`, `SEERRSENSE_LEGACY_TOKEN_ENABLED="false"`;
  - OAuth client `cloudflare-portal-mcp` and the DCR redirect allowlist;
  - DB credentials from `labs-seerrsense-db-creds`; CF Access client id and secret mapped from Vault.
- `mctl_get_service_status(labs, seerrsense)` on 2026-11-22: ArgoCD `labs-seerrsense` Healthy and Synced, image 1.14.4, `hasDatabase: true`.
- Not observed:
  - The owner's Mac mini, where the household Seerr/*arr/qBittorrent/Jellyfin run, and their resource use. SeerrSense runs in the cluster, not on the Mac mini, so any saving applies to the unobserved host. See Open questions in requirements.md.
  - The createmediabox.dev website (not fetched). The mapping to JuanCMPDev/mediabox-mcp rests on the README.

## Proposed solution

### 1. RESEARCH: competitor matrix (verified at tag via GitHub API, 2026-11-22)
MCP status classes:
- R: released in a tag, on by default.
- G: released in a tag behind an off-by-default switch or feature flag.
- P: planned or documented as deferred.
- X: absent from the tag's tree.
- U: unknown.

| # | Candidate | Repo scored | Tag / SHA / date | SPDX | Lang | Contrib / releases | CI and security files | MCP | Auth model (MCP) | Replaces | Ev |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | HolyArrs | HolyArrs/HolyArrs | 1.2.0 / d63e43f / 2026-11-17 | AGPL-3.0 + CLA | Go + Svelte | 5 (top: 43, 2, 1 commits) / 26 since 2026-11-09 | codeql, scorecard, sign, cla, CODEOWNERS; no SECURITY.md; 0 GHSA | G (`ai_apps` held-back feature) | OAuth 2.1 auth-code + PKCE S256, open DCR (rate-limited), single scope `mcp`, no refresh grant; or hand-made AI key; 7 per-key permission groups; two-call `confirm_token` (5 min) on `ask_for_title` | Sonarr, Radarr, Lidarr, Bazarr, Prowlarr, Seerr (claim) | E1-E6 |
| 2 | Streamline | DataHearth/streamline | v3.4.0 / 6d6d255 / 2026-11-06 | GPL-3.0 | Go + Svelte | 4 humans/bots (1069, 129 claude, 82 renovate, 67) / 17 since 2026-04-16 | ci, helm-e2e, image, release, renovate, SECURITY.md | X (only a dev `.mcp.json` for Playwright) | n/a; OIDC SSO and API keys for its REST API (`api/openapi.yaml`) | Radarr, Sonarr, Lidarr, Readarr, Seerr (claim) | E7 |
| 3 | Mediarium | rdborg/Mediarium | v4.1.0 / 9ff49c2 / 2026-11-18 | AGPL-3.0 | Go + TSX | 2 (102, 3) / 74 since 2026-09-28 | ci, codeql, dependabot; no SECURITY.md | G (MCP switched on only from the signed-in web UI) | admin-only API key, or OAuth 2.1 + PKCE S256 + DCR, scopes `mcp:read`/`mcp:write`, 1 h tokens with 90-day refresh, revocable | Radarr, Sonarr, Prowlarr, SABnzbd, torrent client, Bazarr (claim) | E8 |
| 4 | Reelix | demonzoned/Reelix | v0.8.7 (prerelease) / 606fa71 / 2026-11-09 | GPL-3.0 | Rust | 4 (17, 16, bots) / 15, all prerelease | ci, release, dependabot | X (no mcp paths at the tag or on `master`) | n/a; REST API keys | Radarr, Sonarr, Prowlarr, Jellyseerr, Readarr, Lidarr (claim) | E11 |
| 5 | MovieClaw | movieclaw/MovieClaw | v0.51.0 / 395373e / 2026-11-18 | NOASSERTION (custom license) | Python + TS + native apps | 24 (930, 403 claude, ...) / 100+ | ci, dependabot, many app pipelines | R | Bearer tokens per endpoint; OAuth explicitly deferred to P3 in `docs/design/mcp-server.md` | Radarr/Sonarr/Prowlarr + Jellyfin-compatible playback | E9 |
| 6 | MediaManager | maxdorninger/MediaManager | v1.12.3 / 0cfd1fa / 2026-02-10 | AGPL-3.0 | Python + Svelte | 31 / 26; last release 2026-02-11, last push 2026-07-22 | build/push, docs; no CodeQL | X | n/a (OIDC for UI) | Sonarr, Radarr, Overseerr/Jellyseerr (claim) | E10 |
| 7 | arr-mcp | bardesss/arr-mcp (also aplaceforallmystuff/mcp-arr v1.9.0 / 9348ee2, MIT, 250 stars) | v2.3.2 / 7d47b74 | MIT | TS | 14 / active (pushed 2026-11-21) | ci, openapi-drift, SECURITY.md, dependabot | R | MCP tokens with tier and expiry (hashed); writes opt-in per service, previewed and confirmed, audited | none (federated wrapper over the existing stack) | E12 |
| 8 | MediaStack MCP | clive-stokes/mediastack-mcp (alt: aderaaij/mcp-mediastack v0.1.0) | v1.0.0 / e152712 | MIT | Python | 1 / 1; last push 2026-07-04 | no workflows | R | two-step confirmation, 2-min expiry for destructive actions; auth model not verified | none (federated, polls 13 services into PostgreSQL) | E13 |
| 9 | Mediabox MCP | JuanCMPDev/mediabox-mcp | v2.2.0-beta.3 / 8c6a976 | MIT | TS | 1 / betas; last push 2026-09-15 | ci, docker-publish, release | R | "OAuth2"; at the tag, `authorize()` issues a code with no user authentication or consent, and clients and tokens are in-memory Maps (finding E14) | none (orchestrates the existing *arr + Jellyfin containers) | E14 |

Corrections to revision 1:
- Streamline, MediaStack MCP and Mediabox MCP were reported as "not found". They are now resolved, as above.
- Mediarium was "API key only, no OAuth". At v4.1.0 it has OAuth 2.1 with PKCE (E8).
- The claim that "no unified backend has comparable OAuth/PKCE" is withdrawn. HolyArrs (gated) and Mediarium (gated) both implement auth-code + PKCE S256 + DCR. What they lack, compared with SeerrSense:
  - Mediarium has finer-grained scopes, but its sign-in is admin-only.
  - HolyArrs has a single `mcp` scope plus per-key permission groups.
  - Neither has a second-door principal model like #120.
  - HolyArrs has no refresh grant, so expiry handling must be verified live.
  - Neither has per-household multi-tenant isolation across separate backends.

HolyArrs tools vs permission groups, reconciled (E2, E3):
- The MCP surface at 1.2.0 is seven tools: `search_titles`, `library_lookup`, `calendar`, `downloads`, `my_asks`, `health`, `ask_for_title`. Only `ask_for_title` writes.
- The seven tick boxes (See, Add, Downloads, Settings, Delete, Admin, Approve) limit what a key may do across HolyArrs' route groups (`app/backend/internal/ai/mcpkeys/groups.go`, `testdata/route-groups.txt`). They do not imply that every REST operation is exposed as an MCP tool.
- Integration through MCP therefore gets the seven tools. Anything else needs its REST API, under the same key limits.

HolyArrs "Seerr compatibility" (E5) means HolyArrs answers at `/sonarr` and `/radarr`, so an existing Seerr can keep filing requests into it. It does not implement the Seerr API that `SeerrClient` calls. Under option B, SeerrSense either keeps Seerr on top of HolyArrs, or gains a new HolyArrs backend adapter.

HolyArrs metadata (E6):
- The default is the maintainer-run `https://api.holyarrs.com`. It receives lookup terms, TMDB/MusicBrainz ids, language and region, plus an install count that can be switched off. Per the docs it never receives files, library, users or keys.
- It can be replaced with `HOLYARRS_METADATA_URL` or `HOLYARRS_TMDB_KEY`.
- So a hosted metadata server is not compulsory. The data the docs say is sent still needs verifying by capture in the experiment (X1).

Footprint claims, never measured here:
- HolyArrs README (E4) says 16.1 MB compressed (amd64, measured upstream 2026-11-13 on 1.1.3).
- It also gives idle RAM as "about 95 MiB on a fresh install" in one place and "~140 MiB at 10,000 titles" (2026-11-08) in another. These are different contexts, both upstream claims.
- Streamline claims a single CGO-free SQLite binary (E7). No RSS figure was found.

Code-size signal (bytes of non-test source at tag, from the git tree; not LOC; includes generated code):

| Project | Source size | Test files |
|---|---|---|
| HolyArrs | Go 7.6 MB, Svelte 3.5 MB | 1873 |
| Streamline | Go 14.8 MB, Svelte 2.0 MB | 463 |
| Mediarium | Go 6.9 MB, TSX 2.5 MB | 1304 |
| Reelix | Rust 6.2 MB | 83 |
| MediaManager | Python 0.36 MB | 0 found by pattern |
| SeerrSense | TS, about 6,000 lines in `src/` | 23 test files |

A fork of any unified engine inherits millions of bytes of domain code.

Reusable modules seen at tag (candidates for the parser-corpus experiment):
- HolyArrs: `internal/core/releasename/parse.go`, `internal/downloads/client_qbit*.go`.
- Streamline: `internal/library/parser.go`, `internal/indexer/torznab.go`, `internal/download/qbittorrent.go`, `internal/mediaserver/jellyfin.go`, plus `e2e/fakes/torznab.go` and `e2e/fakes/qbittorrent.go`, which are useful as fixture designs.
- Mediarium: `internal/parser/language.go`, `internal/parser/parser.go`.
- Reelix: the `crates/reelix-parser` crate.

Screened out of the scored options, with the reason:
- MovieClaw: the license forbids hosted, SaaS or multi-tenant provision to third parties and any for-profit use without written authorization (E9). Hard governance blocker for MCTL.
- MediaManager: no MCP, and no release in about 9 months (E10).
- Reelix: prerelease only, no MCP, Rust toolchain (E11).
- arr-mcp, MediaStack MCP, Mediabox: federated wrappers that replace nothing. They are prior art for option A's tool design: preview+confirm+audit in arr-mcp, a 2-minute confirm in MediaStack. Mediabox has the auth finding in E14.
- Mediarium is a credible substitute for B: Go, AGPL, gated MCP with OAuth. B's experiment should include it as a second unified backend if cost allows.

### 2. RESEARCH: weighted decision matrix (auditable, revision 2)
Options:
- Baseline: do nothing.
- A: extend SeerrSense as a federated MCP: read-only queue, disk and library adapters, then a plan/approval write model.
- B: integrate HolyArrs unmodified behind a SeerrSense `MediaBackend` adapter.
- C: Streamline as engine, unmodified first, fork only if needed.
- D: clean-room minimal Go movie engine behind SeerrSense.
- H: incremental hybrid. A movies-only engine (D-minimal) replaces Radarr. Seerr+Sonarr keep TV, and the engine consumes Prowlarr's Torznab endpoints, so it has no indexer management of its own.

Scores run 1-5 (5 is best; for effort, 5 means least effort). The format is point [low-high].

| Criterion (w) | Baseline | A | B HolyArrs | C Streamline | D Go engine | H hybrid |
|---|---|---|---|---|---|---|
| Fit 25% | 2 [2-2] | 3 [2-3] | 4 [3-4] | 4 [3-4] | 2 [1-3] | 3 [2-3] |
| Safety/operability 20% | 4 [3-4] | 4 [3-4] | 3 [2-4] | 3 [2-4] | 3 [2-4] | 3 [2-4] |
| Effort 20% | 5 [5-5] | 4 [3-4] | 3 [2-4] | 3 [1-3] | 1 [1-2] | 2 [1-3] |
| Footprint 15% | 2 [1-3] | 2 [1-3] | 4 [2-5] | 4 [2-5] | 4 [3-5] | 2 [2-3] |
| License/governance 10% | 5 [5-5] | 5 [5-5] | 3 [2-4] | 3 [2-4] | 5 [5-5] | 5 [5-5] |
| Migration/reversibility 10% | 5 [5-5] | 5 [4-5] | 4 [3-4] | 3 [2-4] | 3 [3-4] | 4 [4-5] |
| Total (point) | 3.60 | 3.65 | 3.50 | 3.40 | 2.70 | 2.95 |
| Total (low-high) | 3.25-3.75 | 2.75-3.80 | 2.35-4.15 | 2.05-3.95 | 2.10-3.60 | 2.30-3.60 |

Cell rationale (evidence or assumption):
- Fit:
  - B and C cover movies, TV, indexers and qBittorrent natively (E4, E7).
  - B's MCP is limited to 7 tools, and Seerr-API callers need an adapter (E2, E5).
  - C has no MCP but does have an OpenAPI REST surface (E7).
  - A adds visibility, not replacement.
  - D and H cover movies only at MVP (assumption).
- Safety:
  - B: CodeQL, Scorecard, signing and a two-call confirm (E1, E3). Against that: 13 days old, 26 releases in 9 days, one dominant committer, no SECURITY.md, MCP still held back, no refresh grant.
  - C: SECURITY.md, helm e2e and renovate (E7), but no CodeQL seen and MCP absent.
  - D/H: own code, but new and untested release parsing (assumption).
  - A: reuses `guard.ts`, `TenantResolver` and the door-1 auth (E15).
- Effort: the subsystem estimates in section 8.
- Footprint:
  - B: upstream claims only (E4).
  - C: single-binary claim only (E7).
  - D: assumption that a Go static binary is small.
  - H: removes only Radarr.
  - A and Baseline: the full stack unchanged. Every footprint cell is unmeasured.
- License:
  - B: AGPL plus a CLA that lets the maintainer relicense (E1).
  - C: GPL-3.0 (E7). See section 9.
  - A, D, H: MCTL-owned code.
- Migration:
  - B: read-only import with undo (E4 README "Import your setup ... undo it later").
  - C: import path not verified (U, scored lower).
  - H: reversible per domain (movies only).

Sensitivity, recomputed with these numbers (script: weighted sum; sampling is uniform within each [low-high] range, 20,000 draws, seed 127):

| Scenario | Weights changed | Baseline | A | B | C | D | H | Leader |
|---|---|---|---|---|---|---|---|---|
| s0 | as specified | 3.60 | 3.65 | 3.50 | 3.40 | 2.70 | 2.95 | A (B within 0.15) |
| s1 | footprint 30%, fit 20, effort 15, migration 5 | 3.30 | 3.35 | 3.55 | 3.50 | 3.00 | 2.80 | B |
| s2 | safety 30%, fit 20, footprint 10 | 3.80 | 3.80 | 3.40 | 3.30 | 2.70 | 3.00 | A = Baseline |
| s3 | effort 10%, fit 30, footprint 20 | 3.30 | 3.50 | 3.60 | 3.50 | 2.90 | 3.00 | B |

- Sampled first-place share: Baseline 74.7%, B 15.5%, A 7.8%, C 1.6%, H 0.2%, D 0.1%.
- P(B > A) = 0.465, so A and B are statistically tied.
- Baseline's high share comes from its narrow ranges, not a high point total.

Rank reversals (single cell changes at s0 weights):
- B overtakes A if B's safety rises to 4 (B = 3.70) or its effort rises to 4 (B = 3.70).
- Footprint 5 alone gives B = 3.65, a tie.
- If B's safety falls to 2 (for example a confirm-token replay or a DCR abuse in X1), B drops to 3.30, below Baseline.

The pivotal unknowns are therefore:
1. B's demonstrable safety (security and recovery tests).
2. Measured footprint on the owner host.
3. B's adapter effort.

The X1 experiment targets exactly these three.

Verdicts (provisional; for owner review, not decisions):

| Option | Experiment verdict | Business verdict |
|---|---|---|
| Baseline | n/a | Acceptable fallback. Remains the default until X1 reports. |
| A | GO for design-only work (tool catalogue, approval model, #120 tests). Implementation of read-only adapters only after #120's contract settles. | DEFERRED to after X1. |
| B | GO for isolated experiment X1 (fixtures, no egress, no household data). | DEFERRED. Requires gates G1-G6 to pass. |
| C | GO to include Streamline in X1, unmodified, as a second engine. A fork is not proposed. | DEFERRED. |
| D | NO experiment yet beyond X2 (parser corpus). Its effort is the dominant cost. | DEFERRED. Revisit if B and C both fail the gates. |
| H | Design-only. It shares D's engine, and its value depends on X1 footprint numbers (Radarr's share of stack RSS). | DEFERRED. |

Gate criteria, replacing revision 1's age and maintainer thresholds. They are demonstrable, and they apply to any engine in B, C, D or H:
- G1 reliability: the fixture vertical slice (section 7) succeeds in at least 49 of 50 consecutive runs, with zero duplicate grabs and zero imports outside the library root.
- G2 recovery:
  - `kill -9` during download and during import, 10 times each: reconciles to a consistent state with no manual action.
  - A simulated disk-full is refused before any grab.
  - Restore from the engine's own backup onto a clean volume succeeds, and the fixture library is intact.
- G3 security:
  - OAuth conformance: plain PKCE is refused, an unregistered redirect is refused, an auth code works once only, a revoked key is refused at once.
  - The confirm token is single-use and bound to the user.
  - DCR rate limits hold.
  - No unfixed critical or high advisories in the dependency scan of the tag.
  - The release signature or attestation verifies.
- G4 upgrade: an upgrade across at least two consecutive tags on the fixture DB has no migration failure, and the documented rollback is tested.
- G5 footprint: measured idle RSS of the engine (container plus attributed VM share) is at least 30% below the measured RSS of the components it replaces on the same host. Otherwise the footprint argument is void and option scores revert to fit/safety.
- G6 governance:
  - A security contact channel exists. HolyArrs has no SECURITY.md (finding E1), which is flagged but not disqualifying.
  - The license boundary in section 9 holds for the intended topology.
  - The metadata egress observed in X1 matches the docs (E6).

### 3. RESEARCH: native replacement scope and complexity
Scope:
- Radarr: movie monitor, search, grab, import, upgrade.
- Sonarr: series/season/episode monitoring, season packs vs single episodes, scene vs absolute numbering, specials.
- Prowlarr: Torznab/Newznab caps, categories, rate limits and credential storage.
- qBittorrent: the WebAPI v2 adapter (add with category and savepath, poll, ratio and seeding).
- Jellyfin: items, library refresh, watch history.

High-complexity areas:
- Release normalisation: title, year, edition, resolution, codec, source and group, plus Russian titles and audio labels ("Dub", "MVO", "DVO", "AVO", "Rus+Eng", studio tags), size sanity and seed counts. Mediarium ships `internal/parser/language.go` and a mojibake fixer (E8), evidence that Cyrillic handling is a known pain point.
- TMDB/TVDB/IMDb matching.
- Upgrade cutoff.
- Duplicate detection.
- Bounded retries and stalled downloads.
- Disk preflight.
- Hardlink import with a cross-device copy fallback. This needs a shared path mapping between the downloader and the library, which is acutely fragile on macOS with Colima bind mounts. Unverified; X1 tests it.
- RSS sync scheduling.
- Crash reconciliation: a file exists with no row, or a row exists with no file.

Deferred: music, subtitles, playback, transcoding, native torrent.

### 4. FUTURE: component boundaries and topologies
- SeerrSense stays the front door: both identity doors, `TenantResolver`, the resolver, the MCP catalogue and audit.
- A new `MediaBackend` port in `src/providers/` with these methods: `search`, `getMedia`, `planAcquisition`, `getStatus`. `SeerrClient` becomes the first implementation, unchanged in behaviour. Execution is not a port method: it goes through the approval/outbox path in section 5.
- Engine adapters behind the port: `HolyArrsBackend` (B), `StreamlineBackend` (C), or the D engine's `IndexerAdapter`, `DownloadClientAdapter`, `LibraryAdapter` and `MetadataAdapter`.
- Topology T1 (default): the hosted control plane (`labs/seerrsense`) plus a local execution agent on the Mac mini that only dials out. The agent holds every home credential and reaches the engine on localhost or the LAN. No home service is exposed.
- Topology T2: fully self-hosted SeerrSense and engine, reached over a tailnet or stdio. This loses door 2 unless mctl-api JWKS is reachable from home.
- Storage:
  - The engine's own store: SQLite WAL for HolyArrs/Streamline/D (E7), or PostgreSQL where the engine supports it.
  - The control plane keeps PostgreSQL (existing).
  - SQLite needs a single writer, local fsync-safe disk (no network share or VirtioFS write-heavy path), online backup (`.backup` or litestream) and restore drills.
  - Neither SQLite nor a monolith removes lock or corruption risk. G2 tests it.
- Language:
  - TypeScript inside SeerrSense, to reuse zod, `guard.ts` and the auth code. Bun single-binary builds already exist in `release-binaries.yml`.
  - Go for a standalone agent or engine: a static binary, and the language of HolyArrs, Streamline and Mediarium, so their modules are readable as reference.
  - Rust: not justified (no hot path, a third toolchain), even though Reelix's parser crate exists.
  - X2 is the smallest experiment that informs the Go vs TS choice.

### 5. FUTURE: data-plane security model (no write tools during research)
1. Preview is not consent. `plan_acquisition` (read-only) returns a deterministic plan containing: media id, chosen release id and reasons, target root, space check, `plan_digest` and `preview_id`. The preview id authorises nothing.
2. Trusted approval is a human action on a first-party surface, not a model tool call:
   - The person opens an approval URL on seerrsense.mctl.ai (door 1 session) or the mctl decide page (door 2), signs in fresh if the session is old, and approves.
   - That creates `approval(id, subject, principal_door, tenant, backend_id, agent_id, plan_digest, expires_at <= 10 min, state)`.
   - A household policy of "auto-approve for trusted person X" is an open question, off by default.
3. Execute: `execute_plan(approval_id)` runs one transaction:
   - an atomic `UPDATE approvals SET state='consumed' WHERE id=$1 AND state='approved' AND expires_at>now() AND subject=$sub AND tenant=$t RETURNING ...`;
   - an insert into `executions` with `idempotency_key=approval_id`;
   - an insert into an `outbox` row for that agent.

   A replay returns the existing execution. A mismatched digest, subject, tenant, backend or agent is refused. Revocation (`revoked_sessions`, `revoked_subjects`, the door-2 principal revocation) is checked at consume and again at agent dispatch.
4. TOCTOU guard: before grabbing, the agent re-evaluates the preconditions (title still absent, free space, release still listed, digest recomputed from current state). Any deviation aborts to `needs_reapproval` and never auto-substitutes.
5. Durability: an execution state machine (`queued -> dispatched -> downloading -> importing -> imported | failed | needs_reapproval`) with a reconciler that sweeps rows stuck past a bound. Retries are bounded with backoff. Status is observable through `get_acquisition_status`.
6. Local agent:
   - Enrollment: a one-time, short-TTL code shown on `/account`. The agent generates a keypair locally and registers only the public key.
   - It authenticates outbound with signed requests (or mTLS), using a long-poll or WebSocket, with no inbound port.
   - Least privilege: it fetches jobs only for its own `agent_id`, and posts status only.
   - Jobs use a closed schema with release ids from the agent's own local search, never raw URLs from the control plane. The agent never dials control-plane-supplied hosts, which keeps SSRF out of the home LAN.
   - Credentials (qBittorrent, Jellyfin, indexer keys) never leave the host.
   - Path validation: realpath under configured roots, `..` and symlink escapes rejected, a same-filesystem check before hardlinking.
   - Offline: jobs expire and never run late. The agent can be revoked from `/account`.
7. Untrusted metadata: release titles and indexer text are data. They are capped, stripped of control characters, never placed in tool descriptions, and returned as structured fields.
8. Limits and audit:
   - `@fastify/rate-limit`, plus a per-subject daily execution budget modelled on `resolve_usage`.
   - `ToolCallRecord` is extended with `preview_id`, `approval_id` and `execution_id`, never titles.

### 6. FUTURE: identity compatibility (#120), tests only, no change in the spike
- I1: door 1 Google-issued tokens keep working for all five existing tools with unchanged schemas and annotations (`tests/oauth.test.ts`, `tests/integration.test.ts` unmodified).
- I2: door 2 mctl-api tokens with the correct `aud` and a mapped principal are accepted, and media tools are filtered per person.
- I3: wrong audience, wrong issuer or an unpinned `alg` is refused.
- I4: an unmapped `prn_` principal is refused, fail-closed.
- I5: after a principal is revoked, plan, approve, execute and status are all refused, including an already-issued approval.
- I6: a door-2 principal cannot read or approve a door-1 subject's plan, and the reverse also holds (cross-door, cross-tenant).

### 7. FUTURE: one vertical slice, the same for every option
1. Resolve the public-domain "Night of the Living Dead (1968)" (TMDB id from a stubbed metadata fixture).
2. A Jellyfin mock reports it absent.
3. A synthetic Torznab fixture returns crafted XML with 5 releases:
   - wrong audio language;
   - below quality cutoff;
   - oversized for the free space;
   - a duplicate of an existing item;
   - the correct one.
4. Preview.
5. Human approval (section 5.2).
6. A mock qBittorrent "completes" by writing a small synthetic file.
7. Hardlink import into a temp library.
8. The Jellyfin mock lists the item, and status shows `imported`.

For B and C the same fixtures are pointed at the engine. For D and H they are pointed at the engine prototype. No real indexer, tracker or copyrighted content is used. The negative tests are in tasks.md.

### 8. RESEARCH: effort and risk by subsystem
Assumptions:
- Figures are human engineer-weeks, P50 [P10-P90], for one engineer familiar with the SeerrSense codebase. They include tests and review. Ongoing support is excluded.
- DevLoop figures are model costs only, under these assumptions:
  - investigator about $3 per proposal and shepherd about $1-5 per proposal, from the mctl tool descriptions;
  - implementer cost is variable and not quoted;
  - human review of 0.5-2 h per PR is unchanged.
- No speedup is promised.

| Subsystem | A | B | C | D | H |
|---|---|---|---|---|---|
| Read-only adapters (queue, disk, library) | 3 [2-5] | - | - | - | - |
| Engine adapter in SeerrSense | - | 2 [1-3] | 2.5 [1.5-4] | 1 [0.5-2] | 1 [0.5-2] |
| Release parser + RU labels + profile | - | 0 (engine) | 0 (engine) | 3 [2-6] | 3 [2-6] |
| Torznab client + fixture server | 0.5 | 0.5 | 0.5 | 1 [0.5-2] | 0.5 (via Prowlarr) |
| qBittorrent + state machine | - | 0 | 0 | 1.5 [1-3] | 1.5 [1-3] |
| Import (hardlink/copy, path map) | - | 0 | 0 | 2 [1-4] | 2 [1-4] |
| Jellyfin adapter | (in read-only) | 0 | 0 | 1 [0.5-2] | 1 [0.5-2] |
| Store, backups, migrations | - | 0.5 | 0.5 | 1.5 [1-3] | 1.5 [1-3] |
| Scheduler, monitoring, reconcile | - | 0.5 | 0.5 | 2 [1-4] | 1.5 [1-3] |
| Preview/approval/execute + outbox | 3 [2-5] | 3 [2-5] | 3 [2-5] | 3 [2-5] | 3 [2-5] |
| Local agent (enrol, outbound, paths) | 2 [1-4] | 2 [1-4] | 2 [1-4] | 2 [1-4] | 2 [1-4] |
| Security review + identity tests I1-I6 | 1.5 [1-3] | 2 [1-3] | 2 [1-3] | 2 [1-3] | 2 [1-3] |
| Total P50 [P10-P90] | about 10 [6-18] | about 10.5 [6-18] | about 11 [6.5-20] | about 20 [12-38] | about 19 [12-35] |

Notes on the table:
- TV parity for D adds about 12-26 weeks.
- A fork for C adds 8-16 weeks plus ongoing merge cost.
- B and C carry an upstream-volatility risk: HolyArrs shipped 26 releases in 9 days (E1).
- Parallelizable once the `MediaBackend` port and the fixture set exist: the parser, Torznab, qBittorrent, Jellyfin and import modules.
- Sequential chain: port -> preview/approval -> execute/outbox -> agent -> reconcile.
- The DevLoop could take 15-25 proposals for D (about $60-200 in investigator+shepherd cost plus implementer cost, assumption). It does not remove the human review and security-review burden, which is the binding constraint on the sequential chain.

Smallest experiments that reduce uncertainty before choosing Go, TypeScript or a fork:
- X1 (isolated benchmark + security probe): current stack vs HolyArrs 1.2.0 vs Streamline v3.4.0 (optionally Mediarium v4.1.0), all on the same fixtures. Covers G1-G6 where applicable.
- X2 (parser corpus): a synthetic corpus of about 150 release names covering Russian/English titles, audio labels, editions, sizes and season packs, run through each engine's parser test harness at tag (HolyArrs `releasename`, Streamline `internal/library`, Mediarium `internal/parser`, Reelix `reelix-parser`). It measures accuracy and tells whether D can borrow a design or must start from scratch. It is the cheapest discriminator for D vs B/C.

Risk-ranked findings:
1. High: HolyArrs MCP is gated, very young and has no refresh grant (E1-E3). Mitigation: X1 G3, and no production use before the gates pass.
2. High: macOS/Colima path mapping breaks hardlink import (assumption). Mitigation: X1 import test on the owner host.
3. High: Mediabox `authorize()` has no user step at the tag (E14). Excluded. Prior art only.
4. Medium: licence boundary misread for C or B (section 9). Mitigation: an integration boundary of unmodified engines over the network only.
5. Medium: HolyArrs metadata egress differs from its docs (E6). Mitigation: X1 egress capture against a local stub.
6. Medium: #120 contract changes under any future write tool. Mitigation: build only after #120 settles; I1-I6 as gates.
7. Low: the seerrsense MIT/ISC metadata mismatch. Follow-up only.

### 9. RESEARCH: licensing triage (not legal advice)

| Boundary | AGPL-3.0 (HolyArrs, Mediarium, MediaManager) | GPL-3.0 (Streamline, Reelix) | MovieClaw custom | MIT (arr-mcp, Mediabox, MediaStack) |
|---|---|---|---|---|
| Run unmodified, SeerrSense talks over the network API | No source obligation on SeerrSense (separate program). Recipients of the engine are owed its source if it is redistributed | No obligation from network use | Prohibited for SaaS, multi-tenant or for-profit use without written authorization | None beyond notice |
| Modify the engine and let users interact with it remotely | Section 13: offer the modified source to those users | No obligation unless the binary is conveyed | Prohibited commercially | None |
| Distribute (ship a binary or image to others, e.g. a household agent bundle) | Full source under AGPL | Full source under GPL | Non-commercial only, license must be kept | Notice |
| Vendor code into SeerrSense | SeerrSense would become AGPL | SeerrSense would become GPL | Not permitted | Permitted with notice |

- The HolyArrs CLA (E1) lets the maintainer relicense contributions. That is a governance signal, not a user obligation.
- The seerrsense mismatch (MIT `LICENSE` vs ISC `package.json`) should be fixed in a follow-up PR before any combination is considered.

### 10. RESEARCH: PDLC discovery (drafted; not run without owner approval)
Hypotheses (not observations):
- Hh1: the household uses fewer than 30% of Radarr/Sonarr features (profiles, monitor, upgrade).
- Hh2: Russian audio preference is per person, not per household.
- Hh3: a local agent install is acceptable to the owner.
- Hh4: approval through a link is acceptable latency, under 1 minute.

Questions:
- Which *arr features are used weekly?
- Who approves requests today?
- What are each person's language, audio and quality preferences?
- Is a local agent acceptable?
- What failure has hurt most in the last 3 months?

Metrics and thresholds for any pilot:
- request-to-available success of at least 95% on fixtures and at least 90% in a pilot;
- mis-grab rate (wrong language or quality) of at most 2%;
- approval abandonment of at most 20%;
- p95 tool latency of at most 2 s for reads;
- zero cross-tenant or replay incidents;
- host RSS meeting G5.

### 11. Repository recommendation
A separate `mctlhq/mctl-media` repo is not warranted now. Option A and any backend adapter live in seerrsense.

A separate repo becomes warranted when either of these gets an owner GO:
- a standalone Go execution agent (T1), which has its own release cadence, signing and host;
- the D/H engine.

This spike creates no repo.

## Alternatives
- Adopt HolyArrs directly, as the XDA article did. Dropped: its MCP is still a held-back feature (E3), it is 13 days old with daily releases, and none of G1-G6 has been demonstrated.
- Replace SeerrSense with an arr-mcp server. Dropped: it is a federated single-operator wrapper with no per-person, two-door identity. It would regress `guard.ts`, `tenants.ts` and `auth/*`. Its preview+confirm+audit pattern is reused as prior art in section 5.
- Fork Streamline, Reelix or Mediarium now (option C as a fork). Dropped for now: 6-15 MB of foreign domain code, copyleft distribution obligations, and no upstream path. Running C unmodified stays in X1.
- Score only the full-parity strategies. Dropped at the reviewer's request: H (replace Radarr first) is added so value can be delivered without full *arr parity.

## Platform impact
- Migrations: none. No code, schema or gitops change. Future tables (`plans`, `approvals`, `executions`, `outbox`, `agents`) would be additive in `src/auth/store-pg.ts` style (`CREATE TABLE IF NOT EXISTS`).
- Backward compatibility: the five existing tools, their open schemas, annotations, scopes and both identity doors are frozen by requirement. New capability means additive tools and scopes only.
- Resource impact: none in the cluster. X1 and X2 run on isolated local fixtures with egress blocked.
- Risks and mitigations: see the risk-ranked findings in section 8. Stale evidence is mitigated by the tag and SHA pins below; re-verify before any decision, because HolyArrs main moves daily.

## Evidence annex (GitHub API reads on 2026-11-22; tag commit SHAs resolved via `repos/<r>/commits/<tag>`)
- E1: HolyArrs/HolyArrs.
  - Repo facts: created 2026-11-09; SPDX AGPL-3.0; tags 1.1.3 (2026-11-13), 1.1.4 (2026-11-14) and 1.2.0 (2026-11-17, d63e43f36a3a2babf475624f61b0a11021fd98fc); 26 releases; 5 contributors (CoderLuii 43); main at 4b0349e on 2026-11-19.
  - Files at tag: `.github/workflows/{build,cla,codeql,linux,lock,release,scorecard,sign,synology}.yml`, `.github/CLA.md`, `.github/CODEOWNERS`.
  - Absent: SECURITY.md (contents API 404); `repos/.../security-advisories` returned 0.
- E2: HolyArrs `docs/reference/ai.md` @1.2.0. "AI apps are held back in this release ... only when the `ai_apps` feature is switched on". The 7-tool table, the 7 tick boxes, and "Only `ask_for_title` changes anything".
- E3: HolyArrs code @1.2.0:
  - `app/backend/internal/core/startup/held_features.go` (`AIApps = "ai_apps"`);
  - `app/backend/internal/accounts/ai_signin.go` (OAuth 2.1 PKCE S256, `POST /oauth/register`, `scopes_supported: [mcp]`, `grant_types_supported: [authorization_code]`, per-address registration limit);
  - `app/backend/internal/ai/tools.go` (`confirm_token` two-call flow, "unknown, used or expired");
  - `app/backend/internal/ai/limits.go` (`confirmFor = 5 * time.Minute`);
  - `app/backend/internal/core/webserver/confirm.go` (in-memory confirm map bound to user and method+path, deleted on use).
- E4: HolyArrs `README.md` @1.2.0, lines 44 and 99-110 (size and RAM claims), 128-130 (import, old-app API, metadata server) and 420 (maintainer-paid metadata server).
- E5: HolyArrs `docs/reference/old-app-api.md` and `old-app-api-limits.md` @1.2.0 (`/sonarr`, `/radarr`; "Answer Seerr and Overseerr", off by default).
- E6: HolyArrs `docs/library/metadata.md` @1.2.0 (sent vs never-sent lists; `HOLYARRS_METADATA_URL`, `HOLYARRS_TMDB_KEY`; "Count this install").
- E7: DataHearth/streamline v3.4.0 (6d6d255e5b6e662c374aa3b7de98b2a736f50ab5, 2026-11-06).
  - Repo facts: GPL-3.0; created 2026-04-16; 17 releases; README (single binary, CGO-free SQLite, OIDC, request system); `api/openapi.yaml`; `SECURITY.md`; `.mcp.json` (Playwright dev tool only).
  - Modules: `internal/indexer/{torznab,prowlarr}.go`, `internal/download/qbittorrent.go`, `internal/mediaserver/jellyfin.go`, `internal/library/parser.go`, `e2e/fakes/{torznab,qbittorrent}.go`.
- E8: rdborg/Mediarium v4.1.0 (9ff49c21169b8ac135a3022906e0c961b34bc16c, 2026-11-18).
  - Repo facts: AGPL-3.0; created 2026-09-28; 74 releases; 2 contributors.
  - `docs/mcp.md` covers admin-only keys, MCP switched on only from the web UI, OAuth 2.1 PKCE S256, DCR, `mcp:read`/`mcp:write`, and 1 h / 90-day tokens.
  - Code: `internal/api/mcp*.go`, `db/migrations/0221_mcp_oauth.sql`, `internal/parser/language.go`.
- E9: movieclaw/MovieClaw v0.51.0 (395373eb3c79058ee8ce1b2077850b3c4c84ea5c, 2026-11-18).
  - `LICENSE`: modified Apache-2.0. Sections 1-2 (non-commercial only; SaaS, multi-tenant and for-profit use need written authorization), section 4 (contributor relicensing).
  - `docs/design/mcp-server.md`: no OAuth authorization server; OAuth deferred to P3.
- E10: maxdorninger/MediaManager v1.12.3 (0cfd1fa7245d82aa32277550530b6166da5488dd, 2026-02-10). AGPL-3.0, no MCP paths in the tree, last push 2026-07-22.
- E11: demonzoned/Reelix v0.8.7 prerelease (606fa714fa939271a086ed89c3695c9492210fd8, 2026-11-09). GPL-3.0, Rust crates, no MCP at the tag or on `master` (606fa71), README *arr-compatible APIs.
- E12: bardesss/arr-mcp v2.3.2 (7d47b74), MIT, created 2026-08-04, README (44 tools; writes opt-in, previewed, audited; token tiers). aplaceforallmystuff/mcp-arr v1.9.0 (9348ee2), MIT.
- E13: clive-stokes/mediastack-mcp v1.0.0 (e152712), MIT, 1 contributor, no CI, README (27 tools, two-step confirmation, 2-minute destructive expiry). Alternative aderaaij/mcp-mediastack v0.1.0 (14b87d9).
- E14: JuanCMPDev/mediabox-mcp v2.2.0-beta.3 (8c6a976).
  - `packages/mcp-server/src/auth.ts`: `InMemoryClientsStore`; `authorize()` creates a code and redirects without authenticating the user; tokens are held in a `Map` with 24 h access / 30 d refresh.
  - Whether another middleware gates `/authorize` was not verified.
- E15: mctlhq/seerrsense clone at da0c5a3. The files are cited in Current state.
- E16: `platform-gitops/services/labs/seerrsense/values.yaml` and `mctl_get_service_status(labs, seerrsense)`.
- E17: mctlhq/seerrsense#120 (body read via `gh issue view`), mctlhq/.github#236 (title and state only), and the revision-2 review comment on #127.

Limitations:
- Contributor counts come from the GitHub contributors API (default branch, bots included).
- Code size is the sum of blob bytes at the tag, excluding paths that match test, vendor or fixture patterns. It is a signal, not LOC.
- No repository was cloned, built or executed, and no website other than GitHub was fetched. The XDA article and createmediabox.dev were not re-read.
