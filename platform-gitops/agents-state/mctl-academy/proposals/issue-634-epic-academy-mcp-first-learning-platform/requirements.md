# Academy MCP-first learning platform: portable MCP Apps, optional A2UI, cross-host progress (W0 discovery + phased plan)

## Context

Issue mctlhq/mctl-academy#634 (P1, non-blocking discovery) asks for an investigation into turning
Academy into an MCP-first learning product: the same evidence-backed practice bank and the same
personal progress reachable from the existing website (academy.mctl.ai) and from external AI
assistants (MCP clients) through portable MCP Apps UI, with A2UI as an optional declarative
projection and a later homepage redesign. The product hypothesis is "Learn anywhere. Progress
everywhere. Build with AI. Use without AI": deterministic learning must never depend on an LLM, and
Academy should become a reference consumer of portable MCTL UI.

The owner authorizes exactly one DevLoop investigation. This proposal is therefore the W0
deliverable (audit, ADR, contracts, threat model, cost model, test strategy, GO/NO-GO gates) plus a
phased plan for W1-W7 that each require a separate approval before any implementation. Baseline:
`mctlhq/mctl-academy` main at `bcf8302c90f98476e90df1cf4a520554825f39ca`, package version 0.1.101,
deployed as `labs/mctl-academy` image tag 0.1.101 (Synced/Healthy, one pod). Today there is no MCP
endpoint in Academy (`server/app.mjs:101-293` mounts only auth, attempts, votes, account, reports,
admin stats, probes and the SPA), progress is computed in the browser
(`client/src/services/progressStore.ts:680`), and practice/mock sessions are browser-local
(`client/src/practice/usePracticeSession.ts:43`, `client/src/exam/persistence.ts:17`).

## User stories

- AS a learner using an MCP-capable assistant I WANT to browse the course catalog and see my own
  progress in chat SO THAT I can study where I already work.
- AS a signed-in learner I WANT a practice session started on the web to resume in chat (and back)
  with identical progress SO THAT my learning record is one record, not one per host.
- AS a learner I WANT to choose answers myself through a deterministic UI (or a text fallback)
  SO THAT an AI never silently answers on my behalf and my accuracy stays mine.
- AS a learner who never uses AI I WANT the website to keep working exactly as today, with zero
  model calls SO THAT AI is an option, not a prerequisite.
- AS a guest I WANT to practice without signing in and keep my local progress when I later sign in
  SO THAT the free on-ramp is preserved.
- AS the maintainer I WANT one eligibility rule and one eligible artifact shared by web and MCP
  SO THAT drifted or withdrawn content cannot reach any surface.
- AS a privacy-conscious learner I WANT to see which host has access, revoke it, and have account
  deletion remove MCP grants and sessions SO THAT third-party access stays under my control.
- AS a platform owner I WANT Academy to reuse existing MCTL MCP patterns and the existing host matrix
  work (mctlhq/.github#376, #396) SO THAT no second gateway or duplicate standard is built.

## Acceptance criteria (EARS)

W0 (this proposal):
- WHEN the investigation is delivered THE SYSTEM SHALL provide requirements, design (including an
  ADR with decision criteria, a file:line evidence matrix, reuse map, threat model, cost model and
  contracts) and tasks with GO/NO-GO gates per workstream, pinned to commit bcf8302c.
- THE SYSTEM SHALL make no code, content, gitops, deployment, connector-marketplace or account-linking
  change as part of W0.

Shared eligible catalog (W1):
- WHEN the content bundle is built THE SYSTEM SHALL emit one eligible-questions artifact from
  `scripts/lib/content-model.mjs` `partitionQuestions`/`isEligibleForBundle`, consumed by both the
  web client and the MCP adapter; no second eligibility rule and no runtime evidence re-evaluation
  SHALL be introduced.
- WHILE serving MCP tools THE SYSTEM SHALL select and present only questions from that eligible
  artifact; the full answer key in `server/questions.mjs` SHALL be used only for grading and report
  validation, never for selection or discovery.
- IF the eligible artifact is missing or fails validation at boot THEN THE SYSTEM SHALL refuse to
  enable the MCP endpoint (fail closed) while the existing website keeps serving.

Identity and authorization (W1+):
- WHEN an MCP request carries no valid access token for a personal tool THE SYSTEM SHALL respond with
  HTTP 401 and a `WWW-Authenticate` header pointing at Academy's OAuth Protected Resource Metadata.
- THE SYSTEM SHALL accept only access tokens whose audience/resource is the Academy MCP resource URL
  and whose issuer is the configured authorization server; tokens minted for other resources,
  GitHub/Google/ZITADEL upstream tokens and browser session cookies SHALL be rejected on `/mcp`.
- THE SYSTEM SHALL derive the learner identity only from the validated token subject mapped to an
  existing Academy `user.id`; no tool SHALL accept a `userId` argument.
- WHEN a learner revokes a grant or deletes their account THE SYSTEM SHALL reject subsequent requests
  with that grant's tokens within the access-token lifetime and SHALL cascade-delete grants, MCP
  sessions and server practice sessions with the account.
- THE SYSTEM SHALL never forward a client-presented token to any upstream (no token passthrough).

Progress (W1):
- WHEN a learner requests progress through MCP or REST THE SYSTEM SHALL compute it from the
  latest attempt per question intersected with the course's eligible questions, using the same
  pure function the web uses, reporting accuracy, coverage and solved counts separately.
- THE SYSTEM SHALL keep per-course isolation and SHALL NOT describe any value as certification
  readiness or a pass prediction.
- WHEN the same account reads progress on web, then chat, then web with no intervening answers THE
  SYSTEM SHALL return identical numbers on all three reads.

Practice (W2):
- WHEN a learner submits an answer THE SYSTEM SHALL grade a stable option id (`a`..`d`) server-side
  and ignore any client-sent correctness or domain, as `server/routes/attempts.mjs:34-74` does today.
- WHEN an answer submission repeats an already-applied idempotency key THE SYSTEM SHALL return the
  original result and SHALL NOT insert a second attempt row.
- IF a submission's `expected_version` does not match the session's current version THEN THE SYSTEM
  SHALL refuse with `session_conflict` and SHALL NOT change progress.
- WHILE a question has not been answered in a session THE SYSTEM SHALL NOT include correct flags or
  explanations for it in any tool result, structured content, or UI resource payload.
- IF a tool call that records an answer is not initiated by an explicit learner UI action or a
  learner-confirmed selection THEN THE SYSTEM SHALL NOT record it as an attempt.
- WHEN a practice session references a question that is no longer in the eligible artifact THE SYSTEM
  SHALL skip it for presentation and SHALL still grade an in-flight answer only against the answer
  key, without rewriting any past attempt.

Portable UI (W3):
- WHEN a host supports MCP Apps THE SYSTEM SHALL serve versioned `ui://academy/...` HTML resources
  whose direct UI actions call Academy tools without any model call.
- IF a host does not support MCP Apps THEN THE SYSTEM SHALL return a complete text and structured
  content fallback for every tool.
- THE SYSTEM SHALL NOT relax the website's global CSP (`frame-ancestors 'none'`, X-Frame-Options DENY)
  to support embedding; MCP UI resources SHALL carry their own resource-level CSP metadata.
- IF A2UI is enabled (optional, post-MVP) THEN THE SYSTEM SHALL emit only components from an
  allowlisted catalogue validated against a pinned schema, never executable or model-generated markup.

Website preservation (all phases):
- WHILE any workstream is in progress THE SYSTEM SHALL preserve existing public routes, canonical
  metadata, sitemap, noscript content, noindex on `/mock`, `/dashboard`, `/mistakes`, `/admin`,
  security headers, CSRF same-origin checks, guest practice and "Clear history"/account deletion.
- THE SYSTEM SHALL NOT weaken the content lint, bundle eligibility, evidence CI, CONTENT-POLICY.md,
  SOURCES.md or LEGAL.md rules.
- THE SYSTEM SHALL NOT log or send to telemetry learner answers, option ids, tokens or grant ids.

## Out of scope

- Any implementation, merge, deploy, proposal acceptance or production change during W0.
- Connector marketplace/directory submission, live account linking, real-host pilots with real
  accounts, user-data export, new analytics, additional paid inference.
- A new service, database, or gateway (Option C is documented and rejected, not built).
- Server-side Mock exam (W4) beyond a design sketch; homepage redesign beyond a local prototype (W5).
- Academy #74 (interactive sandbox), #75 (OpenRouter inference OAuth), #81 (GitHub sign-in
  investigation), #633 (source drift fixes); MCP App Builder (mctlhq/.github#430) beyond Academy as
  a reference consumer; any change to related accepted proposals.
- Proctoring or certification claims of any kind.
- Changes to clean-room authorship, vendor-neutral naming, licensing split or redistribution terms.

## Open questions

- Authorization server choice (blocks W1 personal tools, not W1 public tools): (a) better-auth's
  OAuth provider / MCP plugin inside Academy, (b) MCTL ZITADEL as the AS for an Academy resource, or
  (c) an existing MCTL MCP Portal OAuth front. The proposal recommends (a) for the MVP, gated on a W1
  spike (see design ADR-2), because Academy's identities are GitHub/Google/ZITADEL users of its own
  `user` table and ZITADEL is optional (`server/zitadel.mjs`). An owner decision is needed before W1.
- Exact MCP spec revision, MCP Apps extension revision and SDK version to pin for Bun/Hono: must be
  re-verified against the official specification at W1 start; this run did not fetch external specs.
- A2UI version and its relationship to MCP Apps as standardized in mctlhq/.github#396: unresolved;
  the proposal defers A2UI past MVP (Option D for MVP).
- Host support matrix (ChatGPT, Claude, Cursor, Antigravity, Grok, Gemini, MCTL PA/Workspace) is not
  verified here; it is owned by mctlhq/.github#376 and must be consumed, not re-measured, in W6.
- README.md:28 says five courses are published and two are "Coming soon", but the generated
  `client/src/course-catalog.json` marks all seven courses `available: true` (91, 53, 37, 28, 39, 22
  and 45 published questions). Documentation drift to confirm with the owner; counts must come
  from generated artifacts.
- Retention of server practice sessions (proposed: 30 days idle) and of MCP grants (proposed: until
  revoked, refresh tokens expiring after 30 days of disuse) need privacy review in PRIVACY.md.
- Whether the historical grading policy (withdrawn questions remain gradable for backfill,
  `server/questions.mjs:32-39`) should also apply to MCP in-flight submissions after a quarantine
  redeploy. Proposed: yes for an in-flight answer to an already-presented question, no for new
  presentation.
- Deployed image digest: gitops `values.yaml` pins `sha256:e6a52625...` while the running pod reports
  image id `sha256:47bd8901...`. Probably index vs platform manifest digest; not verified.
