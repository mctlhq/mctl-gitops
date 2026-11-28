# Design: issue-634-epic-academy-mcp-first-learning-platform

Baseline: `mctlhq/mctl-academy` `main` @ `bcf8302c90f98476e90df1cf4a520554825f39ca`
(package `0.1.101`). This is the W0 investigation output. Nothing here is approved for
implementation.

## Current state

### Evidence matrix (read in the clone at the baseline SHA)

| # | Area | Evidence | Finding | Consequence for MCP |
|---|------|----------|---------|---------------------|
| E1 | App composition | `server/app.mjs:37,42,84-125` | Hono app; `securityHeaders` on `*`, `apiErrorLog` on `/api/*`, better-auth on `/api/auth/*`, routers for attempts/votes/account; `app.all("/api/*")` 404 at :282 | An `/mcp` route mounts in the same app before the SPA fallback (:304-305). No MCP endpoint exists today. |
| E2 | Boot fail-fast | `server/app.mjs:76-90` | `initDb`, `loadCourseCatalog`, auth secret, and ZITADEL config are checked fatally at boot | An eligible-artefact load for MCP must join this fatal set. |
| E3 | Auth | `server/auth.mjs:148-152,163-165,249-266,271-290` | better-auth; GitHub social (+optional Google); ZITADEL via `genericOAuth` with PKCE, `accountSubject` = verified `sub`; OAuth tokens encrypted; `refuseZitadelCrossLink` blocks cross-provider linking; session IP/UA nulled (:189-191) | A browser cookie session is not a delegated grant. The MCP grant must be a separate OAuth token whose subject = `user.id`. Email-based linking is already refused and must stay so. |
| E4 | Attempt write | `server/routes/attempts.mjs:34-73` | Client sends `{questionId, optionId}`; server grades; `correct`/`domain` from client ignored; `requireSameOrigin` | The grading path is reusable as is. There is no idempotency key, so retries insert duplicates. |
| E5 | Attempt read/erase | `server/routes/attempts.mjs:76-99`, `server/db.mjs:123-194` | Append-only INSERT, server `attempted_at`; `DISTINCT ON (question_id) ... ORDER BY attempted_at DESC`; DELETE all rows of user (all courses) | Progress projection can run server-side from `getUserAttempts`. The erase contract must cover new tables. |
| E6 | Answer key | `server/questions.mjs:32-39,138-164,193-201` | Loads **all** `content/questions/*.yaml` regardless of status; grades withdrawn items by design | Must never be used for selection or catalog. MCP selection uses the eligible artefact only. |
| E7 | Eligibility | `scripts/build-content-bundle.mjs:30-48,152`; `scripts/lib/content-model.mjs` | One fail-closed rule; writes `client/src/content-bundle.json`, `course-catalog.json`, sitemap; paths overridable by env | The builder must emit one additional server-readable copy with a digest from the same run. The rule is not duplicated. |
| E8 | Image contents | `Dockerfile` (runner stage) | Copies `server`, `content`, `migrations`, `client/dist`, `client/src/seo`, `client/src/course-catalog.json`; **not** `content-bundle.json` as a standalone server file | The server cannot read the eligible bundle today except as minified chunks in `client/dist`. A COPY line plus build output is needed. |
| E9 | Bundle shape | `client/src/content-bundle.json` (315 items) | Item keys: `course_id, domain, id, objective, objectiveTitle, options[{id,text,correct,explanation}], sources, stem` | The answer key and explanations are public in the web bundle (spoiler protection only). MCP payloads must still strip `correct`/`explanation` before answer. |
| E10 | Catalog | `client/src/course-catalog.json` | 7 courses, all `available: true`; mock config with domain weights, `mockQuestions`, `timeLimitMinutes` | README.md:28 ("Five courses...") is stale relative to the generated catalog. Counts must come from the artefact. |
| E11 | Progress math | `client/src/services/progressStore.ts:60-69,680-753` | `latestPerQuestion` (ties go to later item, `>=`), `calculateProgressStats(bundle, attempts, domainTitles)` with accuracy/solved/unseen/mistakes per domain | These are pure functions and can be extracted to a shared module used by both client and server. That is the parity mechanism. |
| E12 | Sync/merge | `progressStore.ts:104,266,480-570,594` | Per-owner logs (`guest`, `user:<id>`), sync epoch, clear generation, backfill only when server is older, `clearProgress` erases server+local | Conflict policy already exists. A server-owned session must not bypass it. Web keeps using `/api/attempts`. |
| E13 | Practice queue | `client/src/practice/usePracticeSession.ts:14,43-48,57-224` | Client-side shuffle, queue, first-answer scoring, localStorage per owner/course/mode/domain | Cross-host resume needs a server session. The web keeps local sessions until W2 GO. |
| E14 | Mock exam | `client/src/exam/session.ts:5-17,25-106`; `exam/selectMockQuestions.ts:37`; `exam/persistence.ts:4-15`; `exam/dataSource.ts:13,36` | Pure state functions, weighted selection with domain shortfalls, sessionStorage, `ExamDataSource` abstraction | W4 can port these pure functions server-side. Deferred. |
| E15 | CSP/framing | `server/middleware/security-headers.mjs:22-31,43` | `default-src 'self'`, `frame-ancestors 'none'`, `X-Frame-Options: DENY` | Do not frame academy.mctl.ai. MCP Apps HTML is delivered via `resources/read` and rendered in the host's sandbox, and does not depend on the site CSP. |
| E16 | CSRF | `server/middleware/csrf.mjs:12-19` | Origin / `sec-fetch-site` check; no CORS | `/mcp` is a bearer-token API (no cookies). It needs its own Origin validation (MCP transport rule against DNS rebinding) and must reject cookie auth. |
| E17 | Account erase | `server/routes/account.mjs:22-31`; migrations `1754607600000_better-auth-schema.mjs:58,67,98-111`, `1755000000000_question_votes.mjs:30-31` | DELETE `"user"` cascades session/account/attempts/reports/votes | New tables FK to `"user"(id) ON DELETE CASCADE`. |
| E18 | Logging | `server/middleware/request-log.mjs:8-11,50` | Path only, no query/IP/UA/user id/body | Reuse it for `/mcp`. Never log JSON-RPC params. |
| E19 | Rate limiting | `server/middleware/rate-limit.mjs:17-20` | In-memory, single-replica limitation documented | Acceptable for flag-off/canary. Must be revisited before scale-out. |
| E20 | Routes/SEO | `client/src/router/index.ts:18-33`; `server/spa.mjs:29,154,192-196,254` | `/`, `/courses/:courseId`, `/practice`, `/mistakes`, `/mock`, `/dashboard`, `/admin/stats`; 404 + noindex | Unchanged. No new public route is needed for W1-W3. |
| E21 | Client deps | `client/package.json` | Vue 3.5, vue-router, `@mctlhq/ui` 0.21.0, better-auth; Vite 6 | Use Vue + `@mctlhq/ui` for MCP App views. There is no evidence for adding React. |
| E22 | Server deps | `package.json:41-51` | hono 4.13, better-auth 1.7.x, jose 6, pg, ajv | `jose` is already present for JWT/JWKS validation. The MCP SDK is to be pinned at W1. |
| E23 | Tests/CI | `package.json:32-33`; `tests/*.test.mjs`; `e2e/*.spec.ts`; `.github/workflows/{ci,e2e,content-evidence,security,claude-review}.yml` | `node --test` server suite with fixture dist (`tests/helpers/client-dist-fixture.mjs`, `answer-key-fixture.mjs`, `auth-test-helper.mjs`); Playwright e2e | New tests plug into `test:server` and e2e. The content suite stays untouched. |
| E24 | Policy | CLAUDE.md "The gate", "Attempt immutability", "Deployment"; CONTENT-POLICY.md; LEGAL.md; PRIVACY.md:25 | No runtime evidence check; attempts not mutated by the app; learner erase allowed; MCP-only deploy; `env_vars` drop `:` values | The MCP resource URL and issuer go through `secret_env_vars`, because both contain `:`. |

### Deployed state checked

- `mctl_get_service_status(labs, mctl-academy)`: Argo CD app `labs-mctl-academy` is Healthy/Synced, project `apps`, namespace `labs`, image tag `0.1.101`, host `academy.mctl.ai`, port 8080, `base-service`, `hasDatabase: true`. This matches the baseline package version.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-academy/values.yaml`: image `ghcr.io/mctlhq/mctl-academy:0.1.101` with a pinned digest; requests 200m/256Mi, limits 500m/512Mi; `readOnlyRootFilesystem: true`; hosts `academy.mctl.ai` and `labs-mctl-academy.mctl.ai`; env `APP_ENV`, `MCTL_ACADEMY_STATS_ADMINS`; ExternalSecret maps only `GITHUB_CLIENT_ID/SECRET`, `PUBLIC_BASE_URL`, `BETTER_AUTH_SECRET`, `BETTER_AUTH_URL` plus DB creds. **No ZITADEL_* or GOOGLE_* secrets are mapped**, so those providers appear unconfigured in production. **No `replicaCount`/autoscaling key** is present; the chart default replica count was not observed.
- `$MCTL_GITOPS_ROOT/tenants/labs/` contains `catalog-info.yaml` and `values.yaml` (listed, not otherwise needed).
- `$MCTL_GITOPS_ROOT/services/admins/`: no MCTL MCP Portal/gateway service manifest is visible in this checkout (`argocd-mcp`, `coolify-mcp` and `projects-mcp` are separate `labs` services). Whether a portal exists elsewhere (another cluster/repo, #35/#44) **could not be observed** from here. This gap is recorded as an open question; it is not treated as absence.
- Not called: service logs/pods (not needed for a design; no runtime claims are made).

## Proposed solution

### ADR-1: Architecture. Decision: Option A, an in-process MCP adapter on the existing Hono monolith; MCP Apps for MVP; A2UI deferred

**Context.** Learning logic is deterministic, small and already lives in one container.
The risks are spoilers, IDOR, token misuse, divergent business logic, and weakening the
evidence gate or the site's security headers.

**Decision criteria (weighted):** (1) one eligibility rule and one progress implementation,
(2) per-user isolation and standards-compliant OAuth, (3) zero mandatory model calls,
(4) no new service/DB/gateway, (5) host portability with text fallback, (6) incremental,
flag-gated, reversible rollout, (7) engineering cost.

**Decision.** Add an `academy` domain layer inside `server/` with two adapters:
REST (existing routes, unchanged) and MCP (Streamable HTTP at `/mcp`). The domain layer is
used in-process by both, so the web never makes an MCP round trip. Portable UI is delivered as
MCP Apps resources built from Vue + `@mctlhq/ui`. A2UI is a later, optional, contract-only
projection (W3b, own gate).

**Consequences.** One process and one DB. The MCP code path shares the pod's memory and CPU.
A host outage or MCP bug is isolated by a feature flag rather than a process boundary.

### Component diagram (MVP slice: W1 + W2 practice + W3 quiz)

```
              +------------------- Bun container (labs/mctl-academy) --------------------+
 Browser ---> | Hono app                                                                  |
 (Vue SPA)    |  securityHeaders (unchanged)                                              |
   |  cookie  |  /api/auth/*  better-auth  (GitHub; + OAuth AS endpoints, ADR-2)           |
   +--------->|  /api/attempts, /api/votes, /api/account   (unchanged REST)                |
              |  /api/practice-sessions/*   (W2, REST adapter, cookie + requireSameOrigin) |
 MCP host --->|  /.well-known/oauth-protected-resource      (W1)                          |
 (Claude,     |  /mcp   Streamable HTTP, bearer only, Origin check, flag ACADEMY_MCP      |
  ChatGPT..)  |     |                                                                     |
   bearer     |     v                                                                     |
              |  server/academy/  (domain, pure + db ports)                               |
              |    catalog.mjs   <- server/generated/eligible-bundle.json (+digest)        |
              |    progress.mjs  <- shared/progress.mjs  (latestPerQuestion, stats)        |
              |    practice.mjs  <- practice_sessions / practice_session_answers           |
              |    grade         -> server/questions.mjs gradeAttempt (unchanged)          |
              |    db.mjs recordUserAttempt / getUserAttempts (unchanged)                  |
              |  ui resources: server/generated/ui/<view>.<semver>.html (Vite single-file) |
              +---------------------------------------------------------------------------+
                                  |  PostgreSQL (shared CNPG, existing DB)
```

### W1: Shared eligible catalog and canonical progress read

1. **One artefact.** `scripts/build-content-bundle.mjs` additionally writes
   `server/generated/eligible-bundle.json` and `eligible-bundle.digest`
   (sha256 of the canonical JSON) **in the same run and from the same in-memory result**
   as `client/src/content-bundle.json`. No second eligibility pass is added. The output contract check
   (`build-content-bundle.mjs:146`) asserts both files are byte-identical in content.
   The Dockerfile runner stage adds `COPY --from=builder /app/server/generated ./server/generated`.
   Boot (`app.mjs:76-90`) loads it fatally when `ACADEMY_MCP` is on. The web bundle is unchanged.
2. **Shared progress math.** Move `latestPerQuestion` and `calculateProgressStats`
   (`progressStore.ts:60-69,680-753`) into `shared/progress.mjs` (plain ESM with JSDoc
   types, importable by Vite and Bun). `progressStore.ts` re-exports it, so the web behaviour is
   byte-identical (existing client tests are the guard). The server projection is
   `getUserAttempts(userId)` -> `latestPerQuestion` -> `calculateProgressStats(courseQuestions)`.
3. **Read tools** (all bounded; personal tools require a token):

| Tool | Auth | Annotations | Output (bounded) |
|------|------|-------------|------------------|
| `academy_catalog` | public | readOnly, idempotent, openWorld=false | courses: id, title, summary, available, publishedQuestionCount, mock availability, disclaimer |
| `academy_course` | public | readOnly, idempotent | one course: domains + objectives + counts; no questions |
| `academy_get_progress` | token | readOnly, idempotent | `OverallProgress` per course (shape of `progressStore.ts:94-103`) |
| `academy_dashboard` | token | readOnly | all courses' summary + `ui://academy/dashboard/1.0.0` |
| `academy_review_mistakes` | token | readOnly | up to 20 question ids + stems + objective titles, no answers (the learner reopens them in practice to see feedback) |
| `academy_recommend` | token | readOnly | deterministic next step, e.g. the lowest-coverage domain, with a reason string; no readiness claim |

Example (`academy_get_progress`):

```json
{
  "name": "academy_get_progress",
  "title": "My progress in a course",
  "description": "Returns your practice progress for one course. Accuracy = correct/attempted; coverage = attempted/total; solved = correct/total. Not a prediction of any exam result.",
  "inputSchema": {
    "type": "object",
    "additionalProperties": false,
    "required": ["courseId"],
    "properties": { "courseId": { "type": "string", "pattern": "^[a-z0-9-]{1,64}$" } }
  },
  "outputSchema": {
    "type": "object",
    "required": ["courseId", "contentDigest", "progress"],
    "properties": {
      "courseId": { "type": "string" },
      "contentDigest": { "type": "string" },
      "progress": { "$ref": "#/$defs/OverallProgress" }
    }
  },
  "annotations": { "readOnlyHint": true, "idempotentHint": true, "openWorldHint": false },
  "_meta": { "ui": { "resourceUri": "ui://academy/progress/1.0.0" } }
}
```

There is deliberately no `userId` property, and `additionalProperties: false` rejects one.

**Error envelope** (tool result `isError: true`, `structuredContent.error`):

```json
{ "error": { "code": "session_conflict", "message": "Session changed on another device.", "retryable": false,
             "details": { "currentVersion": 7 } } }
```

Closed code set: `unauthenticated` (HTTP 401 at transport), `insufficient_scope`,
`unknown_course`, `course_unavailable`, `session_not_found` (also for another user's session),
`session_expired`, `session_conflict`, `question_retired`, `unknown_option`,
`already_answered`, `grading_unavailable` (maps `gradeAttempt` `unavailable` -> 503 today),
`rate_limited`, `confirmation_required`.

### W2: Server-owned practice sessions

**Data model (additive migration `1756000000000_practice_sessions.mjs`):**

```
practice_sessions(
  id uuid pk, user_id text not null references "user"(id) on delete cascade,
  course_id text not null, mode text check (mode in ('remaining','mistakes','all')),
  domain text null, content_digest text not null,
  question_ids jsonb not null,          -- fixed order, eligible at creation
  option_orders jsonb not null,         -- {questionId: ["c","a","d","b"]}, display only
  cursor int not null default 0, version int not null default 0,
  status text check (status in ('active','completed','abandoned')),
  created_at timestamptz default now(), updated_at timestamptz, expires_at timestamptz not null)
  index (user_id, course_id, status)
practice_session_answers(
  session_id uuid references practice_sessions(id) on delete cascade,
  question_id text not null, option_id text not null,
  attempt_id uuid null references attempts(id) on delete set null,
  idempotency_key text not null, origin text check (origin in ('web','app','model_confirmed')),
  created_at timestamptz default now(),
  primary key (session_id, question_id),            -- first answer wins
  unique (session_id, idempotency_key))
```

`attempts` is **not altered**. The first answer to a question in a session inserts one
`attempts` row through the existing `recordUserAttempt`, inside the same transaction as the
`practice_session_answers` insert and the `version` bump
(`UPDATE ... WHERE id=$1 AND user_id=$2 AND version=$expected`). Re-answers in the same
session return `already_answered` with the stored result and are not counted, which matches
the web's first-answer scoring. A new session can re-attempt a question, giving a new latest
attempt (existing semantics). `DELETE /api/attempts` ("Clear history") is extended to also delete the
learner's practice sessions; account deletion cascades.

**Tools:**

- `academy_start_practice {courseId, mode, domain?, idempotencyKey}`: creates or returns the
  learner's active session for (course, mode, domain), so starting twice does not fork. Not read-only, idempotent.
- `academy_get_session {sessionId}`: current question **without** `correct`/`explanation`,
  options in session order, `version`, progress-in-session, answered results so far.
- `academy_submit_answer {sessionId, questionId, optionId, idempotencyKey, expectedVersion}`.
  Result: `{correct, correctOptionId, explanation, nextQuestionId, version}`. Annotations:
  `readOnlyHint:false, destructiveHint:false, idempotentHint:true` (idempotent by key).
  `_meta.ui.visibility: ["app"]` where the host supports it, so the model cannot call it.
  On model-visible fallback, the call without `learnerConfirmed: true` that came from an
  elicitation/confirmation step returns `confirmation_required`; the answer is stored with
  `origin = model_confirmed`, so a later decision can exclude such rows from stats.

**Spoiler rule (enforced in one serializer):** `toPublicQuestion(q)` drops `correct` and
`explanation`. It is the only function the MCP adapter may use for unanswered items. A unit
test walks every tool's `structuredContent`, `content` text and `_meta` for the
substrings `"correct"` / explanation text before submit.

**Stale content:** each `get_session` and `submit_answer` checks pending question ids against
the loaded eligible artefact. A missing id gives `question_retired` and the cursor advances.
Historical answers stay graded (E6 policy).

**Web adoption:** `usePracticeSession.ts` keeps its local queue for guests. For signed-in users,
web adoption of server sessions (true cross-host resume) is a separate W2b GO decision.
Until then, cross-host *progress* parity holds through attempts, and *session resume* works
chat-to-chat only.

### W3: Portable UI (MCP Apps)

- Views: `catalog`, `progress`/`dashboard`, `quiz`. They are built by an extra Vite entry
  (`client/mcp-apps/*.ts`, Vue + `@mctlhq/ui`) into single-file HTML with inlined, hashed
  assets, written to `server/generated/ui/`. The resources are immutable: a new version gets a new URI
  (`ui://academy/quiz/1.0.0`). mimeType `text/html;profile=mcp-app`; `_meta.ui.csp` declares
  no remote origins (no stats.mctl.ai beacon inside hosts).
- Flow: `initialize` (server advertises the MCP Apps extension) -> host `tools/call
  academy_start_practice` -> host fetches `resources/read ui://academy/quiz/1.0.0` -> sandboxed
  iframe -> `ui/initialize` handshake over postMessage -> view receives tool result -> learner
  clicks option -> view issues `tools/call academy_submit_answer` through the host bridge
  (zero model calls) -> deterministic feedback rendered.
- The view never holds a token. Calls go through the host bridge. The view never needs the answer key.
- Text fallback: every tool returns a readable `content[0].text` (stem, lettered options in
  session order, instructions), so text-only hosts work.
- The website stays native Vue, embedding nothing and framed by nothing. Shared code is the
  `@mctlhq/ui` components plus `shared/progress.mjs`.

**A2UI (deferred, W3b):** only if W6 shows a target host that renders A2UI but not MCP Apps.
In that case: a server-built, deterministic A2UI message from the same view-model, an allowlisted
component catalogue (Text, Card, List, Button, RadioGroup, ProgressBar), schema validation on
emit, and no model-generated UI. The renderer is the host's. Academy ships no generic renderer.

### ADR-2: Authorization

Academy is an **OAuth 2.1 resource server** per the MCP authorization spec:
`/.well-known/oauth-protected-resource` (RFC 9728) names `resource =
https://academy.mctl.ai/mcp` and `authorization_servers`. Requirements on the AS: PKCE S256,
resource indicators (RFC 8707) with audience = the resource, short-lived access tokens
(<= 1 h) and rotating refresh tokens, a revocation endpoint, a consent screen naming the host
client, scopes `academy:progress.read` and `academy:practice.write`, and client onboarding
(pre-registered and/or dynamic registration or client metadata documents, depending on the
spec revision pinned at W1).

| Option | Pros | Cons |
|--------|------|------|
| 2a better-auth OAuth provider/MCP plugin (preferred, pending spike) | `sub` = Academy `user.id` natively; grants live in Academy DB and cascade on delete; consent UI in Academy; no cross-system mapping | Plugin maturity/spec coverage must be proven at the pinned version; Academy becomes an AS |
| 2b MCTL ZITADEL as AS (#35/#44) | Platform-standard identity, MFA, central revocation | ZITADEL not configured in `labs`; GitHub-only learners have no ZITADEL subject, so a mapping table is needed, along with a cross-system erase |
| 2c MCTL MCP Portal fronting Academy (Option B) | One connector for all MCTL tools | Portal existence/`ui://` passthrough/per-user isolation not observable from this repo; risk of token passthrough |

Invariants regardless of option: validate `iss`, `aud`/resource, `exp` and the signature (JWKS via
`jose`) or introspect; reject cookie-authenticated `/mcp` calls; never forward the token;
actor = `(user.id, client_id)` and record `client_id` on sessions for revocation-scoped audit;
GitHub tokens (`account` table, encrypted) are never exposed to or derived from MCP grants.

### Threat model (STRIDE-oriented, MVP surface)

| Threat | Mitigation | Test |
|--------|-----------|------|
| IDOR (read/write B's data) | user from token only; every query `WHERE user_id = $token_user`; `session_not_found` for foreign ids | T5, T6 |
| Token audience confusion / passthrough | strict `aud`/resource check; no upstream forwarding | T3 |
| Consent bypass / stale grant after revoke | revocation checked on refresh and introspection or short TTL; deletion cascades grants | T7, T8 |
| CSRF/origin on `/mcp` | bearer only, cookies ignored, Origin allowlist (hosts' origins or none), no CORS credentials | T9 |
| DNS rebinding | Origin validation per MCP transport spec; bind via ingress host only | T9 |
| Malicious host/iframe | UI holds no token or answer key; resource CSP no remote origins; site keeps `frame-ancestors 'none'` | T14 |
| Prompt injection via content | question text is DATA in `content` text; tool descriptions static; no tool executes content; model-initiated submit needs confirmation | T12 |
| Answer spoilers | single redacting serializer; recursive payload scan test | T10 |
| Replay / duplicate submit | `(session_id, idempotency_key)` unique; first-answer PK; `expectedVersion` CAS | T11 |
| Stale/retired questions | digest pinned; eligibility re-check per call; `question_retired` | T13 |
| PII leakage in logs | `apiErrorLog` path-only reused; no JSON-RPC param logging; no telemetry in UI resources | T15 |
| Abuse / cost | rate limiting per token; bounded payload sizes; no Academy-side inference | T16 |

### Cost model

- Academy-side inference: **zero** in every option (no LLM in grading, recommendation or UI).
  Host-side model tokens are paid by the learner's host subscription. Direct UI actions on
  MCP Apps hosts cost zero model calls; text-fallback turns cost host tokens.
- Resources: in-process adapter plus about 1 MB artefact and UI HTML. Estimated additional memory is under 50 Mi
  (to be measured in W1), within the current 256Mi request / 512Mi limit. The DB adds two small tables.
- Engineering (relative): W1 M, W2 M-L, W3 M, W3b (A2UI) M, W4 L, W5 M, W6 S-M per host.

### GO/NO-GO gates (each needs separate owner approval)

| Gate | GO when | NO-GO / stop |
|------|---------|--------------|
| G1 (W1) | AS spike proves 2a or 2b meets ADR-2 invariants at pinned versions; artefact parity test green; privacy text drafted | No compliant AS; parity requires duplicating eligibility |
| G2 (W2) | G1 shipped flag-off; migration reviewed; spoiler/IDOR/replay tests green | Any spoiler leak or cross-user read in tests |
| G2b (web adopts server sessions) | W2 canary stable, no duplicate-attempt increase | Guest/offline regression |
| G3 (W3) | Local conformance host (MCP Inspector or a reference MCP Apps host) renders quiz with zero model calls | UI requires remote script or a weaker site CSP |
| G3b (A2UI) | A verified target host needs it (W6 evidence) | MCP Apps coverage sufficient |
| G4 (Mock) | W2 stable; server clock/finalization design reviewed | Scope pressure; defer |
| G5 (homepage) | Prototype on synthetic fixture passes SEO/a11y tests | Any indexability regression |
| G6 (host pilot) | Separate approval for real accounts; host matrix recorded per client version | Unverified capability claims |
| G7 (distribution) | Privacy review done | Marketplace submission without approval |

## Alternatives

- **B: MCTL MCP Portal/gateway in front of Academy.** Attractive for one-connector UX,
  but nothing in this repo or the visible gitops checkout shows a portal that preserves
  `ui://` resources, the app-to-server bridge, per-user audience-bound tokens and no
  passthrough. A second gateway is forbidden. Kept as a *later* option: Academy's standard `/mcp` and
  PRM endpoint stay compatible with being federated by a portal, so Option A does not block B.
- **C: Separate Academy MCP service.** It gives process isolation, but it needs a new service,
  image and DB access path, plus duplicated grading/eligibility or an internal API with its own
  auth. There is no scale or isolation evidence that justifies it, and it is not authorized. Dropped.
- **D: Static MCP tools only, no MCP Apps or A2UI.** It is the cheapest and fully portable, but it fails
  the "portable MCTL UI reference implementation" goal and makes every answer a model turn,
  which costs host tokens and allows silent AI answering. Adopted partially: the text fallback
  is exactly D, and A2UI is deferred.
- **LLM-generated UI.** Rejected because it is non-deterministic, would execute model markup, and depends on inference.
- **First-party web as an MCP host (thin own host).** Rejected for MVP. It adds an HTTP/JSON-RPC
  hop and token handling to the web for no learner benefit. The in-process domain layer gives the same
  contract guarantee without it.

## Platform impact

- **Migrations:** one additive migration (two tables with FKs and indexes), plus the AS tables if
  2a is chosen (plugin-owned, additive). No ALTER or DROP on `attempts`. `down` drops only the new tables.
  The attempt history and the erase contract are preserved (CLAUDE.md "Attempt immutability").
- **Backward compatibility:** REST endpoints, web bundle, routes, SEO and security headers
  stay unchanged. The `progressStore.ts` re-export keeps the client API identical. With `ACADEMY_MCP`
  off, `/mcp` and `/.well-known/oauth-protected-resource` fall through to the existing 404.
- **Config:** `ACADEMY_MCP=on|off` (colon-free env). The resource URL and AS issuer contain `:`,
  so they go into Vault via `secret_env_vars` (CLAUDE.md "Deployment"). Deploy is MCP-only.
- **Resources:** see Cost model. The single-replica rate limiter (E19) is a known constraint.
- **Risks:** AS plugin immaturity (mitigated by the G1 spike and the 2b fallback); host spec churn (pin
  the SDK and MCP Apps extension versions, immutable UI URIs); spoiler regressions (one serializer and a
  scan test); duplicate attempts from retries (idempotency); privacy (PRIVACY.md update
  before any grant); README drift (counts from the artefact only).
