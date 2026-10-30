# Tasks: issue-858-spike-runtime-mctl-agents-760-slice-1-co

- [ ] 1. Add the pure package `internal/agent/turn` with `State`, `Config`, `Event`, `Turn`, `SessionKey`, `New`, `Offer`, `Tick`, `Claim`, `Done` and `ErrInvalidTransition`, as described in design.md section 1. It imports only the standard library, starts no goroutines and never reads the clock. — DoD: `go vet` and `golangci-lint` are clean. `go list -deps ./internal/agent/turn` shows no non-stdlib import. No production package imports it.
- [ ] 2. Add `internal/db/agent_admission_sim_test.go`: a round-based simulator over the real `Store.ClaimAgentJobs` / `CompleteAgentJob` against the SQLite test store, with `max_concurrent_global` and `max_concurrent_per_user` caps applied by the simulator. The invariants are checked from `agent_jobs` rows after every claim. Use the synthetic personas `Alice`, `Bob`, `Carol` and `Dana`, with ids checked via `git grep`. — DoD: Experiment B passes (T2) without changing `ClaimAgentJobs`.
- [ ] 3. Add the job-binding claims. Add `JobID`, `JobAttempt` and `ConversationID` (`job_id`, `job_attempt`, `conv_id`, all omitempty) to `localjwt.Claims` (`internal/auth/localjwt/issuer.go`) and `auth.Identity` (`internal/auth/identity.go`), and populate them in `localjwt.Provider.Authenticate`. — DoD: a round-trip mint/verify unit test passes. Existing tokens without the claims verify unchanged.
- [ ] 4. Mint job tokens at claim (depends on 3). Add `agentapi.Server.WithJobTokenSigner`. In `handleClaimJobs` (`internal/agentapi/events.go`), add `job_token` to each `jobEnvelope`: `aud=agent-job`, issuer `PublicBaseURL`, TTL = claim deadline - now, parent `Jti`/`OriginalIssuedAt` inherited. Wire the signer and a `selectAgentJobProvider` in `cmd/server/main.go`, and accept either provider on `/api/agent/v1`. — DoD: a claim response carries a verifiable job token whose claims equal the job row. An `aud=agent` token still authenticates every route.
- [ ] 5. Enforce the binding (depends on 4). Add `internal/agentapi/binding.go` with `enforceBinding` and `requireAccountToken`, and call them from every handler listed in design.md section 3. A mismatch returns 403 and `s.audit(..., "denied", "conversation binding: ...")`. — DoD: T3a-T3d pass. Removing the `enforceBinding` call in `handleConversationContext` makes T3a fail; record this mutation check in the PR description.
- [ ] 6. Pass the job token to the MCP subprocess (depends on 4). Add `JobToken` to the worker `Job` / `jobEnvelope` (`internal/agentworker/client.go`). `claudeinvoker.go` puts it in the mcp-config `AGENT_API_TOKEN`, falling back to the account token when it is absent. — DoD: a unit test on the generated mcp-config shows the job token, not `APIToken`. The fallback test passes.
- [ ] 7. Add the operator-routing config and builder. Add `EVENTS_OPERATOR_ROUTING` (default false) to `internal/config`. Give `events.BuildEnvelope` / `OutboxBuilder` an optional closed `routing_reason` (`policy_deny`, `policy_require_approval`, `worker_failure`) written into `Subject`. Envelopes without a reason are byte-identical to today's. — DoD: envelope unit tests pass, and `Marshal` stays under 4096 bytes.
- [ ] 8. Route at decision time (depends on 7). With routing on, skip `insertOutboxTx` in `InsertEventEnqueueJobAndTouch` when a job was enqueued. Add `insertRoutedOutboxTx` and call it inside the deciding transactions:
  - the job-tied `propose_reply` action persisted as `ActionDenied` / `ActionPendingApproval`;
  - `RetryAgentJob` -> `JobDeadLetter`;
  - `RequeueStaleAgentJobs` dead-letter;
  - `CompleteAgentJob` / `CompleteAgentJobWithResult` with `JobFailed`.
  Call `outboxNotify` after commit. — DoD: T4a-T4e pass. With routing off, the existing outbox and relay tests pass unchanged.
- [ ] 9. Follow-ups outside this repo (depends on 1-8). Post the contract findings from design.md ("Contract findings") as a comment on mctlhq/mctl-agents#760. Check whether mctl-claude-remote needs a change to consume `routing_reason` or the reduced stream, and if so file an issue there; do not edit that repo. Confirm with the mctlhq/.github envelope schema owners that `subject.routing_reason` is allowed. — DoD: links to the comment and any filed issue are in the PR description.
- [ ] 10. Prepare enablement as a separate gitops change; do not merge it as part of this PR. Once the image is deployed, a follow-up PR sets `EVENTS_OPERATOR_ROUTING: "true"` in `platform-gitops/services/labs/mctl-telegram-preview/values.yaml`. — DoD: the follow-up is described in the PR description, gated on task 9's schema confirmation.

## Tests

- [ ] T1. `internal/agent/turn/turn_test.go`, a table test (Experiment C):
  - (a) 3 events within `quiet_ms` give 1 turn with 3 `source_event_ids` in order;
  - (b) an event after `quiet_ms` opens a new turn and the first turn is `READY`;
  - (c) a steady stream inside the quiet window is closed by `max_wait_ms` alone;
  - (d) `max_msgs` alone closes the window;
  - (e) `max_bytes` alone closes the window; an oversized single event forms its own turn;
  - (f) invalid transitions return `ErrInvalidTransition`;
  - (g) `turn_id` is deterministic for the same input;
  - (h) sessions are independent.
- [ ] T2. `internal/db/agent_admission_sim_test.go` (Experiment B):
  - 10 sessions over 4 users, global N=5, per-user cap 2: at most 5 processing at any time, at most 1 per conversation and at most 2 per user;
  - every job completes within the asserted `R_max`, and every session is first claimed within the asserted bound;
  - a second case: 1 user with 10 sessions, global N=5.
- [ ] T3a. Negative test: a job token for conversation A calls `GET /conversations/{B}/context`, where B is the same user's other conversation. It gets 403, and a `tool_calls` row records status `denied` and the binding reason. This is the mutation-verified test.
- [ ] T3b. The same negative case for `propose_reply`, `request_owner_approval`, `notify/summary` and `POST /leads` with body `conversation_id = B`; `GET /leads/{id}` for B's lead; `GET /recruiters/{peer}` for B's peer; `GET /jobs/{id}` and `/jobs/{id}/complete` for B's job; and `GET /event/{id}` for B's event. Each returns 403 and is audited.
- [ ] T3c. A job token on `/jobs/claim` and `/events` returns 403 and is audited. A job token on `/policy` and `/autopilot/pause` returns 200.
- [ ] T3d. Positive test: the job token on its own conversation's routes returns 200 and the same bodies as the account token. The existing `aud=agent` tests in `internal/agentapi/server_test.go` keep passing unchanged.
- [ ] T4a. Routing on: a `propose_reply` deny writes one outbox row with `routing_reason=policy_deny` for the job's source event.
- [ ] T4b. Routing on: `require_approval` writes one row with `routing_reason=policy_require_approval`.
- [ ] T4c. Routing on: a job dead-lettered via `RetryAgentJob`, and one completed `failed`, each write one row with `routing_reason=worker_failure`.
- [ ] T4d. Routing on, happy path: ingest plus an executed reply plus `completed` write no outbox row. `ignored` also writes none.
- [ ] T4e. Routing off: ingest writes the outbox row exactly as today, and envelope bytes are unchanged against a golden value.

## Rollback

- The coalescer and the simulator are inert: no production caller uses them. Revert them freely.
- Operator routing: set `EVENTS_OPERATOR_ROUTING` back to `false` (or remove it) in `services/labs/mctl-telegram-preview/values.yaml`. Ingest-time publishing resumes for new events with no redeploy of code. Events that arrived while routing was on and were handled by the worker are not re-published; this is acceptable because the worker already handled them.
- Job token: the worker falls back to the account token when `job_token` is absent, so rolling back the server image alone is safe. Rolling back the worker image alone is also safe, because the server still accepts `aud=agent`.
- No migration exists, so no schema rollback is needed. Release-please revert plus a re-tag restores the prior image.
