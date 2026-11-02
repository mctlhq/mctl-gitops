# Tasks: issue-1046-p4-5-external-runtime-contract-threat-mo

Scope: documentation, doc-sync tests and one opt-in conformance tool. No change to credential minting or verification, the claim handler, the token handlers, the runners, error bodies or `Server.Register`.

- [ ] 1. Write `docs/agent-runtime/threat-model.md`. Required sections: invariant, assets, actors, trust boundaries, a read-exposure table (one row per read route), threats T1-T10 with mitigations, the blast radius of the account-scoped `aud=agent` token as it is today, and residual risks. Each mitigation cites the enforcing symbol, for example `enforceBinding`, `toolGate`, `mintJobToken`, `policy.Evaluate`, `MaxRevocationCacheTTL`, `maxRequestBodyBytes`. Describe the managed model (`agent-pool -> agent-job`) as planned in #1090 and not implemented. — DoD: every route in `agentapi.Server.Register` appears in the read-exposure table or the threat list. Every residual risk has an owner and a revisit trigger. The job-token TTL figure is confirmed against the running service or marked unconfirmed. Reviewed against design.md section 1.
- [ ] 2. Write `docs/contracts/agent-job-api.md` (v1, current behaviour). Cover:
  - the credential matrix (account `aud=agent`, job `aud=agent-job` x route);
  - the lifecycle (claim, events/context, propose, request approval, summary, complete, job status, cost);
  - `jobEnvelope` fields;
  - per-route request and response schemas;
  - binding and fencing rules, deadlines, retry and idempotency expectations, deprecations;
  - the CURRENT error semantics: statuses, `{"error": "<text>"}` bodies and the `policy.DenyCode` values.

  Add `docs/agent_job_api_test.go` (same pattern as `docs/compatibility_test.go`). It drives `Register` with a recording router, which `Register` already accepts, and compares the recorded routes with the contract's route table and with the threat model's coverage. Do not refactor `Register`. — DoD: the doc test passes, and fails if a route is added or removed on one side only. No file under `internal/agentapi` other than tests is changed.
- [ ] 3. Document the credential boundary. Update the `docs/assistants/spec.md` T4 row and `docs/agent-worker.md` to link the contract and threat model and to state: own/external keeps the account-scoped `aud=agent`; managed will use `agent-pool -> agent-job` (#1090, planned). Add the same statement to the contract's authentication section. — DoD: the three documents agree and mark the managed model as not implemented. A diff check shows no change in `internal/auth/**`, `internal/agentapi/tokenhandler.go`, `internal/agentapi/binding.go`, the claim handler, `internal/agentworker/claudeinvoker.go`, `internal/agentworker/openairunner.go` or `cmd/server/main.go`.
- [ ] 4. Add `internal/agenteval/conformance.go` (`Conformance`, an `http.Handler` over a queue of the existing `Task`s):
  - `POST /jobs/claim` accepts the harness-issued token, returns the next fixture's `JobEnvelope` (job id, attempt 1, conversation 1, `instructions` from `Target.Instructions`, `tools` from `Target.JobTools`, deadline, a fresh random `job_token`), and returns `{"jobs": []}` after a short hold when the queue is empty;
  - every other route is dispatched to the `Task` of the currently claimed fixture, using the existing `Task` checks and recording, with the harness token accepted wherever production accepts `aud=agent`;
  - serve one fixture at a time.

  Reuse `Score` unchanged. Extend `TestNoPathToEffects` to cover `conformance.go`. — DoD: model-free unit tests with a scripted worker client pass. `Score`, `FixtureResult`, the violation classes and `HarnessVersion` are unchanged.
- [ ] 5. Add `cmd/agent-conformance`: `--suite`, `--worker-cmd` | `--listen`, `--timeout`, `--filter`, `--report`. `--worker-cmd` starts a loopback server, execs the command with `AGENT_API_BASE_URL` and `AGENT_API_TOKEN` (the env names `cmd/agent-worker` reads), inherits the rest of the environment, and kills the command when every fixture is terminal or the timeout hits. `--listen` prints the base URL and token and waits for the same condition. Output is the `Score` report as JSON bound to `harness_version`, `suite_digest` and `definition_digest`, with no model text, and exit code 0 or 1. (depends on 4) — DoD: `go run ./cmd/agent-conformance --worker-cmd <scripted fake worker>` produces a passing report, and a failing one when the fake worker leaks restricted data or leaves a fixture non-terminal.
- [ ] 6. Add opt-in `TestC1Conformance` (`AGENT_CONFORMANCE=1`) in `internal/agentworker`, which builds `cmd/agent-worker` and runs it through `Conformance` as a black box. Document both commands in `docs/agent-worker.md` ("Testing") and in the contract doc ("Conformance"). (depends on 5) — DoD: skipped by plain `go test ./...`. One manual run of the full 32-fixture suite meets 29/32, 32/32 terminal, 0 leaks, 0 binding violations and 0 wrong auto-sends, with the result recorded in the PR description. Model spend for that single run is stated in the PR and stays within the existing eval budget.

## Tests

- [ ] T1. `docs/agent_job_api_test.go`: the contract's route table equals the routes `Register` binds, and every route is named in the threat model. Mutation: drop one row from either document and the test fails.
- [ ] T2. `TestRegister_RoutesUnchanged`: `Register` still binds exactly the 16 current method/pattern pairs (no refactor happened).
- [ ] T3. `internal/agenteval` conformance unit tests: a scripted correct client passes. A scripted client that leaks restricted data, one that sends outside the tool set, and one that never completes a fixture each produce the existing matching failure in `Score`. `TestNoPathToEffects` covers `conformance.go`.
- [ ] T4. `cmd/agent-conformance` end-to-end with a scripted fake worker binary built in the test: exit 0 and a JSON report carrying the current `HarnessVersion`. A misbehaving variant gives exit 1. The report contains no model text.
- [ ] T5. `TestC1ObserveEval` in-process behaviour and its result are unchanged (existing test passes without edits).

## Rollback

All changes are documentation, tests and an opt-in command, with no migration, no gitops change and no runtime effect.
- Revert the PRs. Nothing in the running service changes either way, because the server, auth and worker code paths are untouched.
- The conformance tool is not part of any deployed image.
