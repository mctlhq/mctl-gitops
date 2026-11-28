# Design: issue-634-epic-academy-mcp-first-learning-platform

Status: proposed (W0 discovery output). Not an implementation approval. Every workstream below has
its own GO/NO-GO gate and needs separate owner approval.

Baseline: mctlhq/mctl-academy main `bcf8302c90f98476e90df1cf4a520554825f39ca`, `package.json`
version 0.1.101. All file:line references are against that commit.

## Current state

### Evidence matrix (file:line, verified by reading the clone)

| Area | Evidence | Finding |
|---|---|---|
| HTTP surface | `server/app.mjs:37` (`securityHeaders` on `*`), `:42` (`apiErrorLog`), `:101` (better-auth `/api/auth/*`), `:113` attempts, `:117` votes, `:122` account, `:157` `/readyz`, `:184` reports, `:293` `/api/*` 404, then static + SPA handler | One Hono app, no MCP endpoint, no OAuth resource metadata. A new `/mcp` and `/.well-known/*` must be mounted before the `/api/*` 404 and the SPA fallback. |
| Boot fail-closed | `server/app.mjs` boot try/catch (`initDb`, `loadCourseCatalog`, `assertAuthSecretConfigured`, `assertZitadelConfigValid`, then `process.exit(1)`) | There is an existing pattern for fatal boot checks. The MCP path should instead disable only itself, so a bad MCP artifact cannot take the website down. |
| Auth | `server/auth.mjs:1-160` better-auth with `pg` pool; `account.encryptOAuthTokens: true` (`:162-166`); GitHub/Google `socialProviders` (`:248-270`); ZITADEL via `genericOAuth` only when configured (`:122-150`) | The browser session is a cookie for this origin. It is not an OAuth access token for an MCP resource. Upstream GitHub/Google tokens are stored encrypted and never reused, so they must never become MCP credentials. |
| Account linking | `server/zitadel.mjs:21-30`, `:248-272` (`refuseZitadelCrossLink`, `unable_to_link_account`); comment in `server/auth.mjs` (account hooks): "GitHub <-> Google linking is unchanged" | Implicit e-mail linking is refused across the ZITADEL boundary, but GitHub and Google can still be linked by e-mail (better-auth default). An MCP grant inherits whatever `user.id` the sign-in resolves to. Record this in the threat model and keep it unchanged. |
| Privileged allowlists | `server/allowlist.mjs:1-40` (GitHub login or `zitadel:<sub>`, never e-mail) | Precedent for stable-subject matching. MCP subject mapping must also use the immutable `user.id`, not e-mail. |
| Attempt write | `server/routes/attempts.mjs:34-74`: requires session, `requireSameOrigin`, accepts only `{questionId, optionId}`, grades with `gradeAttempt`, ignores client `correct`/`domain` | The grading contract can be reused as is by the MCP adapter. |
| Attempt read/erase | `server/routes/attempts.mjs:77-99`; `server/db.mjs:123-150` (append-only INSERT, no idempotency key); `server/db.mjs:160-178` (`DISTINCT ON (question_id) ... ORDER BY attempted_at DESC`); `server/db.mjs:181-194` (DELETE all for user) | Latest-per-question semantics live in SQL and are duplicated in `progressStore.latestPerQuestion` (`client/src/services/progressStore.ts:60`). Retried POSTs today create duplicate rows. Harmless for "latest" semantics, but they distort attempt counts and history. |
| Account erase | `server/routes/account.mjs:21-30` deletes the `user` row; the cascades are documented there and in `migrations/1754607600000_better-auth-schema.mjs` | New tables (grants, mcp sessions, practice sessions) must FK to `user(id) ON DELETE CASCADE` to keep this contract. |
| Answer key | `server/questions.mjs:8-22` (doc), `:32-39` (status deliberately not consulted), `:41-66` (`loadAnswerKey` reads every YAML), `:73-76` `isKnownQuestionId`, `:94-102` `gradeAttempt` | This is the answer key for every question, including withdrawn ones. It must not be used for MCP discovery or selection. |
| Eligibility rule | `scripts/lib/content-model.mjs:438` `checkBundleEligibility`, `:471` `isEligibleForBundle`, `:480` `partitionQuestions`; `scripts/build-content-bundle.mjs:33` import, `:153` writes bundle, `:155` catalog, `:182` sitemap | There is one fail-closed rule. Its output goes only to `client/src/content-bundle.json` (315 questions at this commit) and `client/src/course-catalog.json`. |
| Image contents | `Dockerfile:31-39` copies `server`, `content`, `migrations`, `client/dist`, `client/src/seo`, `client/src/course-catalog.json` | The server has no server-readable eligible bundle today. `content-bundle.json` is only compiled into the Vite JS. W1 must ship it, or a server variant, next to the catalog. |
| Bundle payload | `client/src/content-bundle.json` entries carry `options[].correct` and `options[].explanation` | The web bundle exposes the answer key publicly by design (spoiler protection only, no proctoring). MCP payloads must strip `correct`/`explanation` until answered. |
| Progress | `client/src/services/progressStore.ts:60` `latestPerQuestion`, `:226` `getStoredAttempts`, `:266` `setProgressOwner`, `:417` `recordAttempt`, `:480` `syncFromServer`, `:571` `getMistakeQuestionIds`, `:594` `clearProgress`, `:680` `calculateProgressStats` (denominator = bundle questions per domain) | Progress is client-computed from bundle and attempts. The pure functions (`latestPerQuestion`, `calculateProgressStats`, `getMistakeQuestionIds` logic) can be extracted into a shared module. |
| Practice session | `client/src/practice/usePracticeSession.ts:14` `shuffle`, `:43` `practiceStorageKey` (`academy.practice.v1.` + owner/course/mode/domain in localStorage), `:57` `eligibleQuestions`, `:140` `reconcile`, `:191` `selectOption` (first answer scored) | Session state is device-local, so cross-host resume needs a server-owned session. |
| Mock exam | `client/src/exam/session.ts:25` `startSession`, `:48` `remainingMs`, `:54` `submitSession`, `:90` `scoreSession`; `client/src/exam/persistence.ts:4-42` (sessionStorage); `client/src/exam/selectMockQuestions.ts:37` (weighted per domain, `DomainShortfall`); `client/src/exam/dataSource.ts:13,36` `ExamDataSource` / `StaticBundleDataSource` | The pure state functions and the data-source abstraction make W4 feasible. The client clock is authoritative today. |
| Routing/SEO | `client/src/router/index.ts:18-33`; `client/src/seo/spaRoutes.mjs:30` `NOINDEX_PATH_PREFIXES` = `/mock`, `/dashboard`, `/mistakes`, `/admin`; `server/spa.mjs` renders head and noscript per route | `/mcp` and `/.well-known/*` must stay out of the SPA handler. |
| Security headers | `server/middleware/security-headers.mjs:21-32` CSP incl. `frame-ancestors 'none'` (`:31`), `X-Frame-Options: DENY` (`:43`) | These are global and correct for the site. MCP UI is delivered as `resources/read` content rendered by the host, not as a framed academy.mctl.ai page, so no header change is needed. |
| CSRF | `server/middleware/csrf.mjs:9` `requireSameOrigin` | Cookie-authenticated writes only. `/mcp` is bearer-token authenticated with an Origin allowlist (the mctl-telegram OriginGuard precedent). |
| Rate limit | `server/middleware/rate-limit.mjs:19` (in-memory store, "revisit with a shared store") | Works for a single replica only. MCP write limits inherit this constraint. |
| Frameworks | `client/package.json`: `vue ^3.5.13`, `@mctlhq/ui 0.21.0`, `vite ^6.4.3`; root `package.json:45-49`: `hono ^4.13.1`, `better-auth ^1.7.15`, `pg ^8.22.0` | No React, no MCP SDK yet. Nothing in the code justifies a second UI framework. |
| Tests/CI | `tests/attempts.test.mjs`, `account.test.mjs`, `security-headers.test.mjs`, `spa.test.mjs`, `build-content-bundle.test.mjs`, `content-lint.test.mjs`, `verify-evidence*.test.mjs`, `zitadel*.test.mjs`; `e2e/learning-progress.spec.ts`, `practice.spec.ts`, `mock-exam.spec.ts`; workflows `.github/workflows/ci.yml`, `content-evidence.yml`, `e2e.yml`, `claude-review.yml`, `security.yml` | The existing suites are the regression floor. New MCP tests extend them and must not replace them. |
| Docs drift | `README.md:28` says "Five courses have a published question bank" while `client/src/course-catalog.json` has all 7 `available: true` | Use generated counts, never README text. |

### Deployed state checked

- `mctl_get_service_status(labs, mctl-academy)`: Argo CD `labs-mctl-academy` Healthy/Synced, project
  `apps`, imageTag `0.1.101`, host `academy.mctl.ai`, port 8080, base-service, hasDatabase true.
  The deployed tag matches the baseline package version.
- `mctl_get_service_pods(labs, mctl-academy)`: one pod Running/Ready, 0 restarts, requests 200m/256Mi,
  limits 500m/512Mi, image id `sha256:47bd8901...`.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-academy/values.yaml`: tag `0.1.101`, digest
  `sha256:e6a52625...` (differs from the pod's reported image id, probably index vs platform digest,
  not verified), hosts `academy.mctl.ai` and `labs-mctl-academy.mctl.ai`, env `APP_ENV`,
  `MCTL_ACADEMY_STATS_ADMINS`, secrets via ExternalSecret from `teams/labs/mctl-academy`
  (`GITHUB_CLIENT_ID`, `PUBLIC_BASE_URL`, `BETTER_AUTH_URL`, ...), readOnlyRootFilesystem, no
  replica/autoscaling key (the observed count is 1).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml:86-97` (reuse precedent): mctl-telegram
  serves MCP Apps in-process on its existing `/mcp` route (`MCP_APPS_ENABLED: "true"`,
  `MCP_APPS_WORKSPACE_ONLY`, `ui://mctl-telegram/workspace-2.html`, its own `OAUTH_ISSUER_URL`, and
  an OriginGuard allowlist), with "Rollback: set MCP_APPS_ENABLED=false".
- Not observed: the MCTL MCP Portal/gateway configuration (only the `services/` and `tenants/` trees
  are checked out; the Cloudflare portal lives under `infrastructure/`, which is not present). Its
  ability to front a per-user Academy resource with `ui://` passthrough is therefore unknown (see
  Open questions). External specs (MCP authorization, MCP Apps, A2UI) were not fetched in this run.

## Proposed solution

### ADR-1: Topology. Decision: Option A, an in-process modular monolith with an MCP adapter

Decision criteria, weighted: (1) no new service/DB/gateway (hard constraint from the issue), (2)
single source of truth for eligibility, grading and progress, (3) the web needs zero model calls and
no new mandatory HTTP round trip, (4) the security posture of the existing site is unchanged, (5) the
change can be shipped incrementally and switched off with one flag, (6) it reuses existing MCTL
patterns.

```
                 academy.mctl.ai (one Bun/Hono pod, labs tenant)
  +------------------------------------------------------------------------+
  | securityHeaders (unchanged)                                            |
  |                                                                        |
  |  /api/* (cookie session, requireSameOrigin)   /mcp (Bearer, Origin     |
  |   attempts | votes | account | reports         allowlist, flag-gated)  |
  |        |                                          |                    |
  |        v                                          v                    |
  |   REST adapter  ------------------->  academy domain (server/domain/)  |
  |                                       - catalog   (eligible artifact)  |
  |                                       - progress  (shared pure fns)    |
  |                                       - practice  (server sessions)    |
  |                                       - grading   (questions.mjs key)  |
  |                                                |                       |
  |  /.well-known/oauth-protected-resource         v                       |
  |  /.well-known/oauth-authorization-server   PostgreSQL (CNPG, existing) |
  |  /api/auth/oauth2/* (better-auth AS)       attempts (+ nullable cols)  |
  |                                            practice_sessions (new)     |
  |  SPA (unchanged; Vue imports shared pure fns in-process)               |
  +------------------------------------------------------------------------+
        ^ browser (no LLM)            ^ MCP host (Claude, ChatGPT, ...) renders
                                        ui://academy/v1/*.html from resources/read
```

- New `server/domain/` (plain ESM, no framework) holds catalog, progress, practice and grading
  services. `server/routes/attempts.mjs` and the new `server/mcp/` adapter both call it.
- Shared pure progress functions move from `client/src/services/progressStore.ts` (`latestPerQuestion`,
  `calculateProgressStats`, the mistake-selection logic behind `getMistakeQuestionIds`) into
  `shared/progress.mjs` (typed via `.d.mts`, the pattern `client/src/seo/*.mjs` already uses). The
  client imports them in-process, the server imports the same file, and contract tests pin parity.
  The browser keeps computing locally for guests and offline use. Signed-in users get identical
  numbers because both sides run the same function over the same eligible set and the same server
  latest-per-question rows.
- The first-party web does NOT become an MCP host for the MVP. It keeps its Vue views and gains
  shared view components (see ADR-3) only where MCP Apps need them. This avoids a mandatory HTTP
  round trip and avoids building a host.
- Precedent: mctl-telegram ships MCP Apps in-process behind `MCP_APPS_ENABLED` (gitops values above).

### ADR-2: Authorization. Decision: Academy is its own MCP resource server, using better-auth's OAuth provider for the MVP, gated on a W1 spike

- Academy publishes RFC 9728 Protected Resource Metadata at
  `/.well-known/oauth-protected-resource` with `resource = https://academy.mctl.ai/mcp`, the
  authorization server issuer, and scopes `academy.progress.read` and `academy.practice.write`.
  The public catalog tools need no token.
- Authorization server (MVP recommendation): better-auth's OAuth 2.1 provider/MCP plugin, mounted
  under `/api/auth/*`, which better-auth already owns at `server/app.mjs:101`. It offers
  authorization code + PKCE (S256 only), dynamic client registration rate-limited (or a
  pre-registered client allowlist if DCR is refused at review), consent screen listing host name
  and scopes, access tokens of at most 1 h audience-bound to the resource, rotating refresh tokens,
  and revocation. The user signs in on the consent page with the existing GitHub/Google/ZITADEL
  login. The resulting grant's subject is Academy `user.id`, so there is no e-mail matching.
- Rejected for the MVP (re-evaluated at the W1 gate): ZITADEL as the AS (optional per
  `server/zitadel.mjs`, and most learners are GitHub users who have no ZITADEL identity); the MCTL
  Portal OAuth front (unobserved, see Option B). The choice must be confirmed by the owner (Open
  question 1).
- Never conflated: the GitHub/Google OAuth tokens (stored encrypted, unused after login), inference
  credentials (#75, out of scope) and the Academy MCP grant. `/mcp` validates `iss`, `aud`/resource,
  `exp`, scope and grant-not-revoked on every request, maps `sub` to `user.id`, and never forwards a
  token.
- Revocation surface: a "Connected assistants" list on `/dashboard` (W1 UI, noindex already) with
  per-grant revoke. Account deletion cascades the grant tables (better-auth's OAuth tables FK `user`).

### ADR-3: UI. Decision: MCP Apps (static, versioned, deterministic HTML) for the MVP; A2UI deferred (Option D for MVP)

- Resources: `ui://academy/v1/catalog.html`, `ui://academy/v1/progress.html`,
  `ui://academy/v1/practice.html`, served via `resources/list`/`resources/read` with the MCP Apps
  HTML mime type and resource-level CSP metadata (no remote script origins; data arrives only via
  the host bridge). They are built by a separate Vite entry (`client/mcp-apps/`) that reuses Vue and
  `@mctlhq/ui` components as a single-file inlined bundle. The version is in the URI; old versions are
  served for one release after a bump.
- Tools declare their UI via `_meta` (MCP Apps `ui.resourceUri`). The practice app calls
  `academy_submit_answer` through the host bridge (`tools/call` from the app) when the learner clicks
  an option, with no model in the loop where the host supports app-initiated tool calls. On hosts
  without it, the text fallback lists options with stable ids and the learner must state their choice.
- A2UI: an optional later projection (post-W3 gate). If adopted, it emits only an allowlisted
  component catalogue (Card, Text, ProgressBar, OptionList, Button), validated with ajv against a
  pinned schema, and a thin adapter maps domain view-models to it. Neither LLM-generated UI nor
  arbitrary markup is ever emitted. The rationale for deferring is that MCP Apps alone satisfy the
  MVP, and the A2UI/MCP Apps relationship is still being settled in mctlhq/.github#396.

### Contracts (proposed, examples)

Tool list (W1 read, W2 write). All tools return `structuredContent` plus a text summary, carry no
`userId` argument, and have bounded payloads (at most 50 items per list, with cursors).

| Tool | Auth | Annotations | Phase |
|---|---|---|---|
| `academy_catalog` | none | readOnlyHint, idempotentHint, openWorldHint:false | W1 |
| `academy_course` | none | readOnly, idempotent | W1 |
| `academy_get_progress` | `academy.progress.read` | readOnly, idempotent | W1 |
| `academy_dashboard` | `academy.progress.read` | readOnly; ui `ui://academy/v1/progress.html` | W1 |
| `academy_review_mistakes` | `academy.progress.read` | readOnly; returns question ids + stems of the learner's own wrong answers, explanations only for already-answered items | W1 |
| `academy_recommend` | `academy.progress.read` | readOnly; deterministic (lowest-coverage domain first), no model | W1 |
| `academy_start_practice` | `academy.practice.write` | destructiveHint:false, idempotentHint:true (by key) | W2 |
| `academy_get_session` | `academy.practice.write` | readOnly | W2 |
| `academy_submit_answer` | `academy.practice.write` | destructiveHint:false, idempotentHint:true (by key); ui-initiated or learner-confirmed | W2 |

Example `academy_submit_answer` input schema:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["session_id", "question_id", "option_id", "expected_version", "idempotency_key"],
  "properties": {
    "session_id": {"type": "string", "pattern": "^ps_[A-Za-z0-9]{20,40}$"},
    "question_id": {"type": "string", "pattern": "^q-[0-9a-f]{12}$"},
    "option_id": {"type": "string", "enum": ["a", "b", "c", "d"]},
    "expected_version": {"type": "integer", "minimum": 0},
    "idempotency_key": {"type": "string", "minLength": 16, "maxLength": 64}
  }
}
```

Example result (`structuredContent`). Correctness and the explanation appear only after the submit:

```json
{
  "session_id": "ps_...", "version": 4, "question_id": "q-039ec8a2d5f7",
  "result": {"correct": false, "correct_option_id": "a", "explanation": "..."},
  "first_answer": true, "replayed": false,
  "next": {"question_id": "q-...", "stem": "...",
           "options": [{"id": "c", "text": "..."}, {"id": "a", "text": "..."}, {"id": "d", "text": "..."}, {"id": "b", "text": "..."}]},
  "progress": {"course_id": "physical-ai", "eligible": 45, "attempted": 12, "solved": 9,
               "coverage": 0.267, "accuracy": 0.75}
}
```

Errors (JSON-RPC tool result `isError: true` plus a typed `structuredContent.error`):
`auth_required` (an HTTP 401 with `WWW-Authenticate: Bearer resource_metadata=...` at the transport
level), `insufficient_scope`, `session_not_found` (also returned for another user's session, with no
existence oracle), `session_conflict` {current_version}, `session_expired`, `question_not_in_session`,
`unknown_option`, `ungradable` (answer key unavailable), `rate_limited`, `course_not_found`.

App-to-host flow (MCP Apps): host `initialize` (capability negotiation for apps/ui) -> `tools/call
academy_start_practice` -> the result references `ui://academy/v1/practice.html` -> host
`resources/read` -> the app receives the tool result via the bridge -> learner click -> the app
issues `tools/call academy_submit_answer` with a fresh idempotency key -> it renders the result
deterministically. There are zero model calls on this path when the host supports app tool calls.

### Data model (additive only)

- `practice_sessions` (new): `id text pk`, `user_id text not null references "user"(id) on delete
  cascade`, `course_id text`, `mode text`, `domain text null`, `content_version text` (bundle hash),
  `queue jsonb` (question ids + shuffled option order), `cursor int`, `version int`,
  `created_at`, `updated_at`, `expires_at` (idle TTL, 30 days proposed). Indexed on `(user_id, course_id)`.
- `attempts` (existing): add nullable `session_id text null`, `idempotency_key text null`, and a
  unique partial index `(user_id, idempotency_key) where idempotency_key is not null`. Existing rows
  stay untouched, the REST path keeps working without a key, and past rows are never updated (the
  immutability rule in CLAUDE.md). "Clear history" and account deletion keep deleting all rows.
- OAuth grant/client/token tables created by the better-auth plugin migration, FK to `user` with cascade.
- Migration strategy: node-pg-migrate files under `migrations/`, `up` additive only, `down` drops only
  the new objects. No backfill. Rollback = disable the flag; the tables can stay.

### Offline/guest sync and conflict policy

- Guests: unchanged (local log, `progressStore` merge on sign-in via `syncFromServer`).
- Server practice sessions are opt-in per device. The web keeps its local cursor
  (`practiceStorageKey`) and, when signed in with `MCP_SESSIONS_ENABLED`, offers to resume the
  newest server session. Conflicts resolve by `version` (optimistic concurrency): a stale client
  gets `session_conflict` and refetches. Attempts themselves never conflict, because progress is
  latest-per-question by server `attempted_at`.
- Offline web answers keep today's queued POST. W2 adds a client-generated idempotency key so a
  retry cannot duplicate.

### Threat model (summary)

| Threat | Mitigation |
|---|---|
| IDOR (A reads B's session/progress) | Identity only from the token `sub`; every query is `WHERE user_id = $sub`; a foreign session returns `session_not_found`. Synthetic-user tests T3/T4. |
| Token audience confusion / passthrough | Validate `aud`/resource == `https://academy.mctl.ai/mcp`, `iss`, `exp`, scope; reject session cookies and upstream tokens on `/mcp`; never forward tokens. |
| Consent / revocation | Consent page names the client and scopes; revoke list; deletion cascade; access tokens at most 1 h. |
| CSRF / origin / DNS rebinding | `/mcp` is bearer-only (no cookies read) plus an Origin allowlist (OriginGuard precedent); `/api/*` keeps `requireSameOrigin`. |
| Malicious host / iframe | The global CSP is unchanged; UI resources have no remote origins and no tokens inside the HTML; app actions are tool calls the host mediates; the server re-authorizes each call. |
| Prompt injection via content | Question text is author-reviewed content, but tool results label it as data. No tool executes content, and the write tool requires UI-initiated or learner-confirmed input. Server-side annotations alone are not trusted. |
| Silent AI answers | `academy_submit_answer` is documented as "only with the learner's explicit choice"; the practice app is the primary path; first-answer scoring; an optional per-session `answered_via` audit column (`ui` / `text`) that holds no answer content. |
| Answer spoilers | Correct flags and explanations stripped before answer; contract test T7. The answer key is public in the repo and web bundle, so this is spoiler protection only, not exam security. |
| Replay / duplicates | Idempotency key unique per user, `expected_version`, and first-answer scoring. |
| Stale / retired questions | Selection only from the eligible artifact; `content_version` on the session; quarantined items skipped on the next read; grading still uses the answer key for an in-flight answer; no past attempt rewritten. |
| PII leakage | No answers, option ids, tokens or grant ids in logs (extend `server/middleware/request-log.mjs` tests); minimal payloads; PRIVACY.md update for third-party hosts (a host sees what the learner views). |

### Cost model

- Inference: zero platform model calls on every path. The web never calls a model. MCP-host
  conversations spend the host's/learner's model budget, not Academy's. Direct UI actions in
  supporting hosts need no model call. Text fallback costs belong to the host, and this is documented.
- Compute: one pod at 200m/256Mi today. Estimated MCP overhead: about 20-40 MiB for the SDK and
  eligible artifact, plus per-request JSON work. The proposed W1 gate is measuring p95 under 150 ms
  and RSS under 400 Mi before enabling in production. Raising limits would go through
  `mctl_deploy_service` and is not authorized here.
- DB: one small table plus two nullable columns, on the existing CNPG database.
- Engineering complexity (relative): W1 M, W2 L, W3 L, W4 L, W5 M, W6 S (consumes #376), W7 S.

### Rollout and GO/NO-GO gates

| WS | GO criteria | NO-GO / stop |
|---|---|---|
| W0 | Owner reviews this proposal; AS choice decided | No decision on AS -> W1 limited to public tools |
| W1 | Shared artifact and progress parity tests green; auth spike proves PRM + PKCE + audience + revocation on a local fixture; security review P1/P2 clear | Any eligibility divergence or progress mismatch |
| W2 | Idempotency/concurrency/IDOR tests green; privacy review of sessions | Duplicate attempts or cross-user access in tests |
| W3 | Local conformance fixture host renders the apps; zero-model path proven; text fallback complete | Needs a CSP change on the site |
| W4 | Server clock and atomic finalize designed and reviewed | Defer if W2 is not stable |
| W5 | Local prototype only; SEO/noindex/a11y tests unchanged | Any indexability regression |
| W6 | Host matrix consumed from mctlhq/.github#376; real-host pilot separately approved | Claims without recorded client/version evidence |
| W7 | Docs plus metrics without answer content; privacy review | Any new tracker |

Production enablement (separate approval): `MCP_ENABLED=false` by default (a colon-free scalar, which
is safe under the CLAUDE.md `env:` constraint); flip it on a preview first (`mctl_create_preview`),
then in production, with rollback by flag.

## Alternatives

- **B: route through the existing MCTL MCP Portal/gateway/identity.** Kept as a later option, not the
  MVP. It is attractive for discovery and for a single connector across MCTL, but it could not be
  observed here (the infrastructure tree is not checked out). It would have to preserve per-user
  Academy identity (the portal's ZITADEL subject is not Academy `user.id` for GitHub-only learners),
  `ui://` passthrough and bidirectional app tool calls. Re-evaluate at the W6 gate with evidence from
  #376/#396/#35/#44. Academy's own `/mcp` can sit behind the portal later without contract changes.
- **C: a separate Academy MCP service.** Rejected. It would require a new service (not authorized), a
  second copy of the eligibility artifact and answer key, a cross-service attempt write path, and
  duplicated auth. There is no security or scale evidence for it: one pod is healthy at low load,
  and the risk of a wrong eligibility copy outweighs the isolation benefit.
- **D-full: A2UI-first or LLM-generated UI.** Rejected for the MVP. LLM-generated UI violates the
  "deterministic, no LLM" hypothesis and widens the injection surface. A2UI-first duplicates
  rendering before the cross-upstream contract (#396) is settled. Static MCP Apps cover catalog,
  dashboard and quiz.
- **A-variant: the first-party web as its own MCP host (web -> HTTP /mcp).** Rejected for the MVP. It
  adds a mandatory round trip and a host implementation to the website for no learner benefit. The
  shared pure functions plus a shared domain service deliver parity in-process.

## Platform impact

- Migrations: additive only (one new table, two nullable columns plus a partial unique index, OAuth
  plugin tables), all with cascade to `user`. No destructive change; `down` drops only new objects.
- Backward compatibility: `/api/attempts` request/response unchanged (the optional
  `idempotencyKey` is ignored if absent); web routes, SEO, headers and CSRF unchanged; guest flow
  unchanged; the content gate unchanged; the Dockerfile adds one generated artifact copy
  (`server-content-bundle.json` produced by `build-content-bundle.mjs` alongside the client bundle).
- Resource impact: small, measured at the W1 gate. Single replica: the in-memory rate limiter
  (`server/middleware/rate-limit.mjs:19`) and MCP session state must stay in Postgres or be
  stateless (Streamable HTTP without server-held session affinity), so a future second replica does
  not break correctness.
- Risks: (1) the spec/SDK churn of MCP Apps: pin versions and version `ui://` URIs; (2) a
  better-auth OAuth plugin maturity gap: W1 spike with NO-GO fallback to public-only tools; (3) the
  GitHub<->Google implicit e-mail linking inherited into grants: documented, unchanged, flagged for
  #81; (4) host behaviour differences: text fallback mandatory, matrix from #376; (5) the answer key
  is public: no exam-security claims; (6) env constraint: URLs (issuer, resource) must go via
  `secret_env_vars` or derive from the existing `PUBLIC_BASE_URL` secret, since `env_vars` drops `:`.
