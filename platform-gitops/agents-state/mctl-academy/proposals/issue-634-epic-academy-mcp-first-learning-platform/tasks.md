# Tasks: issue-634-epic-academy-mcp-first-learning-platform

All tasks are **proposed**. This proposal authorizes none of them. Each group starts only
after its GO gate (design.md, "GO/NO-GO gates") is approved by the owner. W0 (this
investigation) is complete with these three files. No code, deploy or host pilot was run.

## W1: Shared catalog, progress read, auth spike (gate G1)

- [ ] 1. AS spike on a throwaway branch: pin the better-auth version and its OAuth-provider/MCP plugin, plus the MCP TypeScript SDK version for Bun/Hono. Verify RFC 9728 PRM, RFC 8707 resource/audience, PKCE S256, client onboarding, consent, revocation and refresh rotation against the pinned MCP authorization spec revision, using a local synthetic AS/client. Compare against ZITADEL (2b) and record the outcome as ADR-2 final. — DoD: a written ADR-2 decision with version pins and a compliance checklist, using only synthetic users and no production calls.
- [ ] 2. Extend `scripts/build-content-bundle.mjs` to write `server/generated/eligible-bundle.json` and `.digest` from the same in-memory result as `client/src/content-bundle.json`, and extend the output-contract check (`build-content-bundle.mjs:146`) to assert equality. — DoD: `tests/build-content-bundle.test.mjs` covers parity and digest stability; `test:content` passes unchanged otherwise; no second eligibility rule exists.
- [ ] 3. Dockerfile runner stage: `COPY --from=builder /app/server/generated ./server/generated`. (depends on 2) — DoD: the image contains the artefact; `readOnlyRootFilesystem` still works because it is read-only at runtime.
- [ ] 4. Extract `latestPerQuestion` and `calculateProgressStats` from `client/src/services/progressStore.ts:60-69,680-753` into `shared/progress.mjs` and re-export them from `progressStore.ts`. — DoD: the existing client unit tests pass unmodified, the server can import the module, and `vue-tsc` and the lint pass.
- [ ] 5. Add `server/academy/catalog.mjs` (loads the artefact fatally at boot when `ACADEMY_MCP=on`, exposes course/question lookups and `toPublicQuestion`) and `server/academy/progress.mjs` (`getUserAttempts` with shared stats per course). (depends on 2, 4) — DoD: unit tests with fixture content; no import of `server/questions.mjs` for selection.
- [ ] 6. Add the `/mcp` Streamable HTTP adapter and `/.well-known/oauth-protected-resource` behind `ACADEMY_MCP`, with bearer validation per ADR-2, an Origin check, cookie rejection, `apiErrorLog`, rate limiting, and the read tools `academy_catalog`, `academy_course`, `academy_get_progress`, `academy_dashboard`, `academy_review_mistakes` and `academy_recommend` using the schemas and error codes in design.md. (depends on 1, 5) — DoD: tests T1-T9 and T15-T17 pass; with the flag off, `/mcp` returns the existing JSON 404.
- [ ] 7. PRIVACY.md: add a third-party host disclosure, the consent screen copy, retention of grants and sessions, revocation steps, and the fact that answers and tokens are not logged. (parallel with 6) — DoD: reviewed under claude-review; required before any grant is issuable.

## W2: Server-owned practice (gate G2; G2b for web adoption)

- [ ] 8. Additive migration `migrations/1756000000000_practice_sessions.mjs` (`practice_sessions`, `practice_session_answers`, FK `"user"(id) ON DELETE CASCADE`) with a `down` that drops only these tables. — DoD: migrate up/down passes on a scratch Postgres; `attempts` schema is unchanged.
- [ ] 9. `server/academy/practice.mjs`: start (returns the existing active session or creates one), get (redacted), submit (transaction of answer insert, `recordUserAttempt` and version CAS; idempotency key; first-answer wins; `question_retired` handling). Extend `DELETE /api/attempts` and account deletion so they cover sessions. (depends on 5, 8) — DoD: T10-T13 and T18 pass.
- [ ] 10. MCP tools `academy_start_practice`, `academy_get_session` and `academy_submit_answer`, with annotations, `_meta.ui.visibility: ["app"]` on submit, and the `confirmation_required` path for model-visible fallback. (depends on 6, 9) — DoD: T10-T12 and T14 pass.
- [ ] 11. (G2b, separate approval) Add a REST adapter `/api/practice-sessions/*` (cookie + `requireSameOrigin`) and an opt-in for signed-in users in `client/src/practice/usePracticeSession.ts`; guests keep the local queue. (depends on 9) — DoD: e2e `practice.spec.ts` and `learning-progress.spec.ts` pass, and the new e2e test T19 passes.

## W3: Portable UI (gate G3; A2UI gate G3b)

- [ ] 12. Add a Vite multi-entry build `client/mcp-apps/{catalog,progress,quiz}` (Vue + `@mctlhq/ui`, single-file HTML, no remote origins) written to `server/generated/ui/<view>.<semver>.html`, served through `resources/list` and `resources/read` as `ui://academy/<view>/<semver>`, `text/html;profile=mcp-app`. (depends on 6) — DoD: resources are immutable per version; T14 and T20 pass.
- [ ] 13. Quiz view to host bridge flow (`ui/initialize`, receives tool result, calls `academy_submit_answer` through the host) verified on a local conformance host. (depends on 10, 12) — DoD: T20 shows zero model calls for an answer.
- [ ] 14. (G3b, only if W6 evidence requires it) Deterministic A2UI projection: allowlisted catalogue, schema validation, pinned A2UI version. — DoD: schema tests; no generated markup.

## W4-W7 (designed only; separate gates)

- [ ] 15. (G4) Server-side Mock: port `client/src/exam/session.ts` and `selectMockQuestions.ts` to the server, with a server clock, atomic finalization, per-domain weighting and shortfall handling, and no answer disclosure before finish. — DoD: separate proposal.
- [ ] 16. (G5) Homepage prototype on a synthetic fixture only; SEO shell unchanged. — DoD: T21 passes; production is unchanged.
- [ ] 17. (G6) Host matrix: for each of ChatGPT, Claude, Cursor/Antigravity, Grok, Gemini and MCTL PA/Workspace, record client and version and whether OAuth, read, write, render, callback and fallback each work or are unsupported, using local fixtures first and real accounts only after separate approval. Feeds mctlhq/.github#376. — DoD: a matrix doc that makes no claim without a recorded observation.
- [ ] 18. (G7) Connector install guide and metrics plan (activation, completed practice, cross-host resume, render success, latency/error, duplicate attempt rate). The plan uses aggregates only and no answer content, and requires a privacy review. — DoD: docs PR; no marketplace submission.

## Tests

All tests are proposed and none was executed. They use synthetic users A and B, a fixture content dir (`tests/helpers/answer-key-fixture.mjs`), a fixture dist and a local in-process AS. No production calls are made.

- [ ] T1. Public `academy_catalog` and `academy_course` work without a token and return only catalog fields; counts equal the generated artefact, not README.
- [ ] T2. Personal tools without a token return 401 with `WWW-Authenticate` pointing to the PRM; the PRM document lists the correct `resource` and `authorization_servers`.
- [ ] T3. Tokens with the wrong audience/resource, the wrong issuer, an expired `exp` or a bad signature are rejected. A cookie session on `/mcp` is rejected. No outbound request carries the token.
- [ ] T4. A tool call containing `userId` fails schema validation (`additionalProperties:false`).
- [ ] T5. User A cannot read B's progress or mistakes; results are always A's own.
- [ ] T6. User A calling `get_session`/`submit_answer` with B's session id gets `session_not_found`, and B's data is unchanged.
- [ ] T7. After a grant is revoked, both the access token (after introspection or TTL) and the refresh token fail.
- [ ] T8. Account deletion removes the user, grants, sessions, session answers and attempts. "Clear history" removes attempts and sessions for all courses.
- [ ] T9. `/mcp` with a disallowed `Origin` is rejected. Website routes still send `frame-ancestors 'none'` and `X-Frame-Options: DENY` (extends `tests/security-headers.test.mjs`).
- [ ] T10. Spoiler scan: before submit, no tool result `content`, `structuredContent` or `_meta` and no UI resource contains `correct`, the correct option id as a flagged field, or explanation text. After submit, the result reveals exactly that question's answer.
- [ ] T11. Replaying `submit_answer` with the same idempotency key returns the identical result and inserts one attempts row. A second answer to the same question returns `already_answered` without a new row. A stale `expectedVersion` returns `session_conflict` and leaves progress unchanged. Reordered retries (n+1 before n) do not double count.
- [ ] T12. A model-visible submit without confirmation returns `confirmation_required` and stores nothing.
- [ ] T13. A question removed from the artefact (fixture marks its source drifted, then the bundle is rebuilt) is never served in new or pending sessions (`question_retired`), is excluded from denominators, and still grades historically via `gradeAttempt`.
- [ ] T14. UI resources declare no remote origins, hold no token and include no answer key.
- [ ] T15. Logs for `/mcp` failures contain only method, path, status and code, with no params, tokens or option ids (extends `tests/request-log.test.mjs`).
- [ ] T16. The rate limit applies per token on `/mcp`.
- [ ] T17. Parity: for a synthetic attempt log, `shared/progress.mjs` server output equals the client `calculateProgressStats` output field by field, per course and per domain, including tie-breaking in `latestPerQuestion`.
- [ ] T18. Concurrent submits on one session (two hosts) give one winner and one `session_conflict`, never two attempts. An expired session returns `session_expired`.
- [ ] T19. e2e: the same account answers on web, then in chat (MCP test client), then reloads the web; dashboard numbers are identical at each step. Guest practice and guest-to-user backfill behave exactly as today.
- [ ] T20. Local conformance host: rendering the quiz and answering in it triggers zero model calls. A text-only client completes the same session using text fallback.
- [ ] T21. Existing `tests/spa.test.mjs` and `tests/server.test.mjs` plus the e2e suite pass unmodified (routes, canonical, sitemap, noscript, noindex). `test:content`, `content-evidence.yml` and `security.yml` are unchanged and green.

## Rollback

- Every server change ships behind `ACADEMY_MCP` (default off). The first rollback step is to redeploy with the flag off via `mctl_deploy_service action=update-config`. `/mcp` and the PRM then return 404, and REST and web are untouched.
- Revoke all outstanding MCP grants (an AS admin operation, or by deleting the plugin's grant tables), so hosts lose access immediately.
- Image rollback: `mctl_rollback_service labs/mctl-academy` to `0.1.101` (the current baseline). The migrations are additive, so an older image ignores the new tables.
- Schema rollback (only if required): the migration `down` drops `practice_session_answers` and `practice_sessions` (and the AS tables if 2a). This discards in-flight sessions only, because the `attempts` rows written by sessions stay valid learner history.
- Web changes (task 4 extraction, task 11 opt-in) are reverted by PR, using a merge-commit revert. Task 4 is a pure re-export, so a revert has no data impact.
