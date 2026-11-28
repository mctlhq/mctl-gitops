# Tasks: issue-634-epic-academy-mcp-first-learning-platform

Only task 0 (W0) is in scope for this investigation. Tasks 1+ are the proposed plan. Each
workstream needs a separate owner approval at its GO/NO-GO gate (design.md, "Rollout and GO/NO-GO
gates"), and nothing is implemented automatically. Baseline commit bcf8302c.

- [ ] 0. W0: owner review of this proposal; decide the authorization server (better-auth OAuth
  provider vs ZITADEL vs MCTL Portal) and confirm A2UI deferral. — DoD: a recorded decision on the
  issue; no code, gitops or deploy change made.

W1: shared eligible catalog and read-only tools
- [ ] 1. Extend `scripts/build-content-bundle.mjs` to also write a server-readable eligible artifact
  (`server/generated/content-bundle.json`, same `partitionQuestions` output, plus a content hash), and
  add it to `scripts/lib/validate-generated-artifacts.mjs` and `Dockerfile` (runner stage, next to
  `course-catalog.json`). — DoD: byte-identical question set to `client/src/content-bundle.json`
  asserted in `tests/build-content-bundle.test.mjs`; the lint and evidence CI are unchanged.
- [ ] 2. Extract `latestPerQuestion`, `calculateProgressStats` and the mistake-selection logic from
  `client/src/services/progressStore.ts` into `shared/progress.mjs` + `.d.mts`, and re-export from
  progressStore. (depends on 1) — DoD: existing client tests and `e2e/learning-progress.spec.ts`
  green, unchanged.
- [ ] 3. Add `server/domain/catalog.mjs` and `server/domain/progress.mjs` over the artifact and
  `getUserAttempts`. (depends on 1, 2) — DoD: parity contract test client vs server on fixtures.
- [ ] 4. Auth spike on a local fixture: better-auth OAuth provider/MCP plugin, RFC 9728 metadata,
  PKCE S256, audience-bound tokens, revocation, consent, cascade on `DELETE /api/account`.
  (depends on 0) — DoD: spike report with pinned versions; GO/NO-GO recorded; NO-GO leaves W1 public-only.
- [ ] 5. Mount `server/mcp/` (pinned MCP SDK, Streamable HTTP, stateless) at `/mcp` before the
  `/api/*` 404 in `server/app.mjs`, behind `MCP_ENABLED` (default false), with an Origin allowlist and
  bearer validation; tools `academy_catalog`, `academy_course`, `academy_get_progress`,
  `academy_dashboard`, `academy_review_mistakes`, `academy_recommend`. (depends on 3, 4) — DoD: tests
  T1-T6, T10-T12 green; security review via `claude-review.yml` has no P1/P2.
- [ ] 6. "Connected assistants" list and revoke on `/dashboard`; PRIVACY.md update for third-party
  hosts, retention and revocation. (depends on 4) — DoD: privacy review approved.

W2: authenticated practice
- [ ] 7. Additive migration: `practice_sessions` table; nullable `attempts.session_id`,
  `attempts.idempotency_key`; partial unique index. (depends on 5) — DoD: up/down tested;
  `tests/account.test.mjs` proves cascade.
- [ ] 8. `server/domain/practice.mjs` (queue from eligible artifact, option order, version,
  first-answer scoring, grading via `gradeAttempt`) and tools `academy_start_practice`,
  `academy_get_session`, `academy_submit_answer`. (depends on 7) — DoD: T7-T9, T13 green.
- [ ] 9. Optional `idempotencyKey` on `POST /api/attempts` and a web "resume server session" offer
  behind `MCP_SESSIONS_ENABLED`. (depends on 8) — DoD: existing attempts tests unchanged and green.

W3: portable UI
- [ ] 10. `client/mcp-apps/` Vite entry producing inlined `ui://academy/v1/{catalog,progress,practice}.html`
  with Vue + `@mctlhq/ui`; `resources/list`/`read`; tool `_meta` UI links; text fallback for every tool.
  (depends on 5, 8) — DoD: local conformance fixture host renders them; a zero-model click-to-grade
  path is demonstrated; T14-T15 green.
- [ ] 11. (Optional, separate gate) A2UI allowlisted catalogue plus ajv schema and adapter. (depends on
  10 and the mctlhq/.github#396 outcome) — DoD: schema validation tests; no generated markup.

Later (design sketches only until approved)
- [ ] 12. W4 server Mock: server clock, weighted selection reuse of `selectMockQuestions`, atomic
  finalize in one transaction, no answer disclosure before finish. (depends on 8)
- [ ] 13. W5 homepage prototype on synthetic fixtures; SEO shell untouched. (depends on 10)
- [ ] 14. W6 host matrix consumed from mctlhq/.github#376; preview flag/canary plan. (depends on 10)
- [ ] 15. W7 connector docs and privacy-reviewed aggregate metrics (no answer content). (depends on 14)

## Tests

All tests are proposed, use synthetic users and local fixtures only, and make no production calls.
None has been run as part of this investigation.

- [ ] T1. Eligibility: the MCP catalog and the practice queue contain only artifact questions; a
  fixture question with a drifted/deprecated source never appears; course isolation holds.
- [ ] T2. Progress parity: the same synthetic account web -> MCP -> web gives identical
  eligible/attempted/solved/coverage/accuracy per course.
- [ ] T3. IDOR: user A's token cannot read B's progress or session (`session_not_found`), and there
  is no `userId` argument accepted anywhere.
- [ ] T4. Token checks: wrong audience, wrong issuer, expired, revoked, missing scope, session cookie on
  `/mcp`, and an upstream GitHub token are all rejected; a 401 carries the `WWW-Authenticate`
  resource_metadata.
- [ ] T5. Revocation and deletion: after a revoke, or after `DELETE /api/account`, tokens fail and
  grants/sessions/attempts are gone; after `DELETE /api/attempts`, progress reads are empty on both surfaces.
- [ ] T6. Fail closed: a missing or invalid server artifact disables `/mcp` while `/readyz` and the
  site stay up.
- [ ] T7. Spoilers: no `correct`/`explanation` in any tool result, `structuredContent` or UI payload for
  an unanswered question.
- [ ] T8. Idempotency: a duplicate submit with the same key returns `replayed: true` and inserts no row;
  reordered retries produce no progress change.
- [ ] T9. Concurrency/expiry: a stale `expected_version` gets `session_conflict`; an expired session
  gets `session_expired`; two concurrent submits produce exactly one first-answer score.
- [ ] T10. Security headers: `tests/security-headers.test.mjs` unchanged (CSP `frame-ancestors 'none'`,
  X-Frame-Options DENY) and also asserted on `/mcp` and `/.well-known/*` responses.
- [ ] T11. SEO/routing: `tests/spa.test.mjs` unchanged; `/mcp` and `/.well-known/*` are never served
  the SPA shell; noindex prefixes unchanged.
- [ ] T12. Logging: `tests/request-log.test.mjs` extended so that no option id, token or grant id
  appears in log lines.
- [ ] T13. Retired question: an in-flight answer after quarantine is still graded, the question is
  absent on the next read, and no past attempt row changes.
- [ ] T14. Fallback: on a host without UI capability every tool returns a complete text answer.
- [ ] T15. Zero model calls: the web e2e suites and the fixture host's UI actions make no outbound
  inference request.
- [ ] T16. Regression floor: the existing `tests/*`, `e2e/*`, content lint, evidence and
  `verify-evidence*` suites stay green and unmodified in their assertions.

## Rollback

- W0: nothing to roll back (no changes).
- W1-W3: set `MCP_ENABLED=false` (and `MCP_SESSIONS_ENABLED=false`), a colon-free scalar via
  `mctl_deploy_service action=update-config`, or redeploy the previous semver tag via
  `mctl_rollback_service`. The website is unaffected because the MCP path is isolated behind the flag.
- Migrations are additive. The new tables and columns can stay in place harmlessly; `down` drops only
  the new objects and never touches existing attempt rows.
- Grants: revoke all through the OAuth provider's tables (or delete them) so connected hosts lose
  access immediately; learners' progress is unaffected.
