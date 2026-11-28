# Academy MCP-first learning platform: portable MCP Apps, optional A2UI, cross-host progress (W0 investigation output)

Status requested: **proposed**. This document is the W0 discovery deliverable for
mctlhq/mctl-academy#634. It authorizes nothing: no implementation, no implementer
run, no deploy, no new service/DB/gateway, no connector submission, no live account
linking, no additional paid inference. Every workstream below W0 has its own GO/NO-GO
gate (design.md, "GO/NO-GO gates") that requires separate owner approval.

Baseline: `main` at `bcf8302c90f98476e90df1cf4a520554825f39ca`, package version
`0.1.101`, deployed `labs/mctl-academy` image `0.1.101` (verified, see design.md
"Deployed state checked").

## Context

Academy today is a Vue 3/Vite client and a Hono API in one Bun image
(`Dockerfile`), with GitHub sign-in via better-auth (`server/auth.mjs:148`),
server-graded attempts (`server/routes/attempts.mjs:34-73`) and progress computed
client-side from a build-time, fail-closed content bundle
(`scripts/build-content-bundle.mjs`, `client/src/services/progressStore.ts:680`).
There is no MCP endpoint, no server-owned practice or exam session, and the global
CSP forbids framing (`server/middleware/security-headers.mjs:31`).

The owner wants Academy to become an MCP-first learning product: learn in an
external AI assistant (Claude, ChatGPT, Cursor and others) through portable MCP Apps
UI, keep the same personal progress across web and chat, and still use the site
without any LLM ("Learn anywhere. Progress everywhere. Build with AI. Use without
AI."). Academy should become a reference implementation of portable MCTL UI. This
matters because the learning logic is fully deterministic. An MCP surface must
add reach without making learning depend on a model, and without weakening the
evidence gate, spoiler protection, privacy or the existing site.

## User stories

- AS a learner using an AI assistant I WANT to browse courses and see my Academy progress inside the chat SO THAT I do not have to switch to the website.
- AS a signed-in learner I WANT to start a practice session in chat, answer in an embedded quiz, and resume the same session later on the web SO THAT my progress is one record wherever I learn.
- AS a learner I WANT the AI assistant to be unable to answer questions on my behalf and have that counted as my work SO THAT my progress reflects what I actually know.
- AS a guest on the website I WANT practice to keep working with no sign-in and no AI SO THAT the free product is unchanged.
- AS a learner I WANT to revoke an assistant's access and to delete my account and history SO THAT I control which hosts can see my data.
- AS the maintainer I WANT the MCP surface to serve only bundle-eligible content from the same build artefact as the web SO THAT evidence policy is enforced once, at build time.
- AS an MCTL platform owner I WANT Academy to reuse existing MCTL contracts (`@mctlhq/ui`, identity, MCP Apps host matrix) SO THAT it is a reference consumer, not a fork.

## Acceptance criteria (EARS)

### Investigation deliverable (this proposal)
- THE PROPOSAL SHALL pin the baseline commit, provide a file:line evidence matrix, a reuse map, an ADR with decision criteria, at least three compared options (including "no A2UI for MVP"), example tool schemas, errors and annotations, an MCP Apps contract, an auth/token flow, a threat model, a data model and migration plan, a test strategy with synthetic users, a cost model, and GO/NO-GO gates per workstream (design.md).
- THE PROPOSAL SHALL distinguish proposed tests from executed results. No test, host pilot or production call was executed in this investigation.

### Content and catalog (W1)
- WHEN any MCP tool returns questions, courses or counts THE SYSTEM SHALL derive them only from the same generated eligible artefact that `scripts/build-content-bundle.mjs` writes for the web client, never from the all-status answer key loaded by `server/questions.mjs:138-164`.
- WHILE a question is absent from the eligible artefact THE SYSTEM SHALL NOT offer it in any new session, catalog count, recommendation or progress denominator. It MAY still grade a historical attempt for backfill, which is the existing behaviour of `gradeAttempt`.
- THE SYSTEM SHALL NOT add a runtime evidence check, read private R2 snapshots, or relax evidence CI (CLAUDE.md "The gate").
- THE SYSTEM SHALL NOT place certification naming in any MCP tool name, title, description, UI resource name or payload field other than verbatim course `prepares_for`/`description`/`disclaimer` from `content/courses/<id>.yaml` (LEGAL.md).

### Identity and authorization
- WHEN an MCP request without a valid access token calls a personal tool THE SYSTEM SHALL answer HTTP 401 with a `WWW-Authenticate` header pointing at its OAuth Protected Resource Metadata (RFC 9728).
- THE SYSTEM SHALL accept only access tokens whose audience/resource equals the Academy MCP resource URL, issued by the configured authorization server, unexpired and not revoked. Tokens for other resources SHALL be rejected, and tokens SHALL never be passed through to upstream services.
- THE SYSTEM SHALL resolve the learner only from the token subject mapped to the Academy `user.id`. IF a tool argument names a user id THEN THE SYSTEM SHALL reject the argument, because no tool schema accepts one.
- THE SYSTEM SHALL NOT link accounts by email address. The GitHub sign-in credential, any inference credential and the Academy MCP grant SHALL remain separate.
- WHEN a learner revokes a host grant THE SYSTEM SHALL reject that grant's access and refresh tokens on their next use. WHEN a learner deletes their account THE SYSTEM SHALL cascade-delete grants, tokens, sessions and attempts (extending `server/routes/account.mjs:22-31`).
- WHERE public catalog tools are called without a token THE SYSTEM SHALL return only public catalog data and no personal data.

### Progress parity (W1)
- WHEN the same account reads progress through the web and through `academy_get_progress` THE SYSTEM SHALL return identical totals, attempted, correct, mistakes, unseen, accuracy and solved values per course and per domain. Both SHALL be computed by one shared pure implementation of `latestPerQuestion` and `calculateProgressStats`.
- THE SYSTEM SHALL compute progress per course by intersecting latest-per-question attempts with that course's eligible question ids, and SHALL keep accuracy (correct/attempted), coverage (attempted/total) and solved (correct/total) distinct.
- THE SYSTEM SHALL NOT present any value as certification readiness or a pass prediction.

### Practice sessions (W2)
- WHEN a learner starts practice through MCP or web THE SYSTEM SHALL create a server-owned session that is bound to the user, course, mode and content digest, and that holds a fixed question order. Option order SHALL be fixed per question within the session.
- WHILE a session question is unanswered THE SYSTEM SHALL NOT include `correct` flags, the correct option id or explanations in any tool result, `structuredContent`, `_meta` or UI resource payload.
- WHEN an answer is submitted THE SYSTEM SHALL require an explicit stable `optionId` ("a".."d"), an `idempotencyKey` and the session's `expectedVersion`, grade it server-side, and append exactly one `attempts` row for the first answer to that question in that session.
- IF the same `idempotencyKey` is replayed THEN THE SYSTEM SHALL return the original result and SHALL NOT insert a row. IF `expectedVersion` is stale THEN THE SYSTEM SHALL return `session_conflict` with the current version and SHALL NOT change progress.
- IF a session's content digest no longer matches the deployed artefact and a pending question is no longer eligible THEN THE SYSTEM SHALL skip it with `question_retired` and SHALL NOT serve it.
- IF a session has expired or is owned by another user THEN THE SYSTEM SHALL return `session_expired` or `session_not_found` respectively. It SHALL return `session_not_found` for another user's session so the session's existence is not revealed.
- THE SYSTEM SHALL count an answer as learner work only when it arrives from an app-originated UI action, or after an explicit learner confirmation in text-only hosts. The submit tool SHALL be marked app-only where the host supports tool visibility.

### Portable UI (W3)
- THE SYSTEM SHALL expose versioned, immutable UI resources (`ui://academy/<view>/<semver>`) via `resources/list` and `resources/read`, and reference them from tool `_meta`. Each resource SHALL declare the CSP it needs and load no remote script.
- WHILE a host cannot render MCP Apps THE SYSTEM SHALL return complete text plus `structuredContent` so that learning still works.
- WHEN a learner selects an option inside the embedded quiz on a host that supports app-to-server tool calls THE SYSTEM SHALL complete the grade with zero model calls.
- THE SYSTEM SHALL NOT render arbitrary model-generated markup or script. If A2UI is later added, only an allowlisted component catalogue validated against a schema SHALL be rendered.
- THE SYSTEM SHALL keep `frame-ancestors 'none'`, `X-Frame-Options: DENY` and `requireSameOrigin` unchanged for the website.

### Web, SEO, privacy, operations
- THE SYSTEM SHALL keep every existing public route, canonical tag, sitemap, noscript content, noindex rule and keyboard focus behaviour (`client/src/router/index.ts`, `server/spa.mjs`) unchanged.
- WHILE the web client runs THE SYSTEM SHALL make zero mandatory model calls and SHALL NOT require an MCP round trip to render practice.
- THE SYSTEM SHALL NOT log learner answers, tokens, authorization codes or tool arguments. It SHALL extend the `apiErrorLog` path-only rule (`server/middleware/request-log.mjs:8-11`) to `/mcp`.
- BEFORE any external host can obtain a grant THE SYSTEM SHALL update PRIVACY.md with a third-party host disclosure, a consent screen, retention terms and revocation.
- THE SYSTEM SHALL ship the MCP surface behind a default-off feature flag. Deploying with the flag off SHALL change no observable behaviour.

## Out of scope

- Any implementation, implementer run, PR merge, proposal acceptance, production deploy or config change during this investigation.
- Connector marketplace or directory submission, live account linking, real-host pilots (each needs separate approval).
- A new service, database, gateway, or second MCP gateway; new paid inference; new analytics or tracking of answer content; user-data export.
- Academy #74 (interactive sandbox), #75 (OpenRouter inference OAuth), #81 (GitHub sign-in investigation) and #633 (source drift) beyond referencing them; MCTL #376, #393, #396, #401, #416, #426, #430, #35 and #44 are dependencies only, and none of them is started or modified.
- Proctoring, certification claims, readiness scoring.
- Changes to clean-room authorship, CONTENT-POLICY.md, SOURCES.md, LEGAL.md, licensing split or the evidence gate.
- Server-side Mock exam (W4) and the homepage redesign (W5). Both are designed only to the level needed for compatibility and are deferred behind their own gates.

## Open questions

1. **Authorization server.** Should Academy use better-auth's OAuth-provider/MCP plugin (identity stays in Academy's `user` table, so cascade erasure is simple) or the MCTL ZITADEL/MCP Portal identity (#35/#44)? The decision criteria are in design.md ADR-2. Proceeding assumption: better-auth acts as the authorization server, with a W1 spike that must verify the exact pinned plugin version supports RFC 9728 metadata, RFC 8707 resource binding, PKCE S256, dynamic or pre-registered clients, and revocation. If it does not, fall back to ZITADEL. ZITADEL is not configured in `labs` today, because `values.yaml` maps no ZITADEL_* secrets.
2. **App-only submit visibility.** Host support for app-only tool visibility (MCP Apps `_meta.ui.visibility`) and for elicitation is unverified per host. W6 must record it. Until then, text-only hosts get a confirm-then-submit flow.
3. **Guest progress in chat.** A guest's progress lives only in browser localStorage (`progressStore.ts:104`). Proceeding assumption: chat requires sign-in for personal tools, and guest-to-account merge stays web-only, with the existing backfill semantics.
4. **Historical timestamps.** The server stamps `attempted_at` at insert time (`server/db.mjs:123-131`), so an offline backfill is re-timestamped. Should W2 accept a bounded client `answeredAt` for offline rows? Proceeding assumption: no. Server time stays authoritative, and the current behaviour is documented.
5. **Course count discrepancy.** README.md:28 says five courses are published, but the committed generated `client/src/course-catalog.json` marks all seven `available: true` (91/53/37/28/39/22/45 questions). The generated artefact is authoritative, and counts must be re-derived at build time rather than hardcoded.
6. **A2UI version.** A2UI is pre-1.0 and its spec version must be pinned at W3b. Proceeding assumption: A2UI is deferred (Option D for MVP).
7. **MCTL MCP Portal (Option B).** No portal/gateway manifest is visible in the gitops checkout available to this run. Its capabilities (`ui://` passthrough, app-to-server bridge, audience-bound per-user tokens) could not be observed, and this is not evidence that the portal is absent. It must be confirmed against mctlhq/.github#35/#44 before G1.
8. **Replica count.** The in-memory rate limiter (`server/middleware/rate-limit.mjs:17-20`) assumes a single replica. MCP traffic may require a Postgres-backed limiter before scaling out. The replica count is not set in `values.yaml`, so the chart default was not observed.
