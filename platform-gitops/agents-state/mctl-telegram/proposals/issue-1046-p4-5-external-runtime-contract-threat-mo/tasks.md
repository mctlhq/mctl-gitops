# Tasks: issue-1046-p4-5-external-runtime-contract-threat-mo

- [ ] 1. Write `docs/agent-runtime/threat-model.md`. Required sections: invariant, assets, actors, trust boundaries, a read-exposure table (one row per read route), threats T1-T10 with mitigations, and residual risks. Each mitigation cites the enforcing symbol, for example `enforceBinding`, `toolGate`, `mintJobToken`, `policy.Evaluate`, `MaxRevocationCacheTTL`, `maxRequestBodyBytes`. — DoD: every route in `agentapi.Server.Register` appears in the read-exposure table or the threat list. Every residual risk has an owner and a revisit trigger. Reviewed against design.md section 1.
- [ ] 2. Add `internal/agentapi/codes.go` with the closed error-code enum and `ErrorCodes()`. Add `writeAPIError` in `internal/agentapi/json.go`. Move every `writeJSONError` call in `internal/agentapi` (handlers, `denyBinding`, `requireAccountToken`, `toolGate`) to it, keeping the `error` text byte-identical. Policy refusals use `code=policy_denied` and `reason=<policy.DenyCode>`. — DoD: no `writeJSONError` call remains in agentapi handlers. Existing tests pass unchanged.
- [ ] 3. Refactor `Server.Register` to iterate a route table exposed as `agentapi.Routes()` (method, pattern, tool from `tools.Endpoints`, `claimOnlyAllowed bool`). Check that `internal/agentworker/client.go` tolerates the extra `code` field. (depends on 2) — DoD: the routes registered are identical before and after (test). The worker client decodes an error body with `code`.
- [ ] 4. Write `docs/contracts/agent-job-api.md` (v1). Cover:
  - the credential matrix (runtime, job, account x route);
  - the lifecycle (claim, events, propose, request approval, summary, complete, job status, cost);
  - `jobEnvelope` fields;
  - per-route request and response schemas;
  - binding and fencing rules;
  - deadlines;
  - deprecations;
  - the error-code table.

  Add `docs/agent_job_api_test.go`, which compares the doc's route and code tables with `agentapi.Routes()` and `agentapi.ErrorCodes()`. Link the contract from `docs/assistants/spec.md` (T4 row: "runtime token (claim-only) + job tokens") and `docs/agent-worker.md`. (depends on 1, 3) — DoD: the doc test passes, and fails if a route or code is added or removed on one side only.
- [ ] 5. Add `auth.Identity.ClaimOnly`. Add `localjwt.ProviderConfig.ClaimOnly`, which sets it on success. Add `agent-runtime` to `derivedAudiences` in `internal/auth/localjwt/issuer.go`. — DoD: unit tests cover a provider with `ClaimOnly` setting the flag and the revocation check running for `agent-runtime` without a `jti`.
- [ ] 6. Add `NewRuntimeTokenHandler` (`POST /api/agent/runtime-token`, admin `admin:users`, `aud=agent-runtime`, `jti`, `orig_iat`, TTL 7 d default / 30 d cap) in `internal/agentapi/tokenhandler.go`. Make `NewAgentTokenHandler` mint a `jti` too. Mount the route, and add `selectAgentRuntimeProvider` to the agent provider chain in `cmd/server/main.go`. (depends on 5) — DoD: a minted token authenticates on `/api/agent/v1/jobs/claim` with `ClaimOnly=true`. `selectAgentProvider` rejects it. The mint log line carries the `jti` and not the token.
- [ ] 7. Add `requireNotClaimOnly` in `internal/agentapi/binding.go`, applied in `Register`'s wrappers to every route whose table entry is not `claimOnlyAllowed` (only `POST /jobs/claim`). In `handleClaimJobs`, for `ClaimOnly` identities: return 503 `job_token_unavailable` without a signer, and requeue (not return) any claimed job whose `mintJobToken` result is empty. (depends on 3, 6) — DoD: a table test over `Routes()` shows a 403 `credential_claim_only` plus an audit `denied` row on every non-claim route. A claim-only claim without a signer is 503 and claims nothing.
- [ ] 8. In `ClaudeInvoker.Run` (`internal/agentworker/claudeinvoker.go`, the `finishRun` client) and `OpenAIRunner.Run` (`internal/agentworker/openairunner.go`, `workerAPI`), build the client passed to `finishRun` from `job.JobToken` when it is present, and fall back to the configured worker token only without one. This covers both `GetJobStatus` and `ReportJobCost`. (independent) — DoD: a unit test for each runner uses a fake API that refuses the worker token on per-job routes, and the job finishes successfully.
- [ ] 9. Add `internal/agenteval/conformance.go` (`Conformance` handler):
  - claim token, `POST /jobs/claim` serving fixtures in order with a fresh job token per job;
  - per-token dispatch to `Task`;
  - path-id binding checks;
  - the `claim_token_on_job_route` violation class.

  Extend `Score`/`FixtureResult` and `TestNoPathToEffects`. Bump `HarnessVersion` to `agenteval/2`. (depends on 7 for the response shape) — DoD: model-free unit tests with a scripted worker client pass. Each violation class is detected.
- [ ] 10. Add `cmd/agent-conformance`: `--suite`, `--worker-cmd` | `--listen`, `--timeout`, `--filter`, `--report`; JSON report bound to the harness version, suite digest and definition digest; exit code 0 or 1. Add the binary to `Dockerfile.agent-worker`. (depends on 9) — DoD: `go run ./cmd/agent-conformance --worker-cmd <scripted fake worker>` produces a passing report, and produces a failing one when the fake misuses the claim token.
- [ ] 11. Add opt-in `TestC1Conformance` (`AGENT_CONFORMANCE=1`) in `internal/agentworker`, which runs the built `cmd/agent-worker` through `Conformance`. Document both commands in `docs/agent-worker.md` ("Testing") and in the contract doc ("Conformance"). (depends on 8, 10) — DoD: skipped by plain `go test ./...`. One manual run of the full 32-fixture suite meets 29/32, 32/32 terminal, 0 leaks, 0 binding violations, 0 claim-token-on-job-route and 0 wrong auto-sends, with the result recorded in the PR description.

## Tests

- [ ] T1. `TestRuntimeToken_ClaimOnly`: a table over `agentapi.Routes()`. A runtime token gets 403 `credential_claim_only` on every route except `POST /jobs/claim`, and every refusal writes an audit `denied` row. Mutation: drop the guard from one wrapper and the test fails.
- [ ] T2. `TestRuntimeToken_ClaimReturnsJobTokens`: a claim with a runtime token returns jobs that each carry a `job_token` with the runtime `jti`. A claim without a signer returns 503 `job_token_unavailable` and the job stays pending.
- [ ] T3. `TestRuntimeRevocation_KillsDerivedJobToken`: mint a runtime token, claim, revoke the runtime `jti`, then call `propose_reply` with the existing job token. It is refused within `MaxRevocationCacheTTL`, and claim is refused too. Repeat with a blanket revocation by Telegram id.
- [ ] T4. `TestRuntimeToken_TTLClamp` and `TestRuntimeToken_AdminOnly`: the 7 d default, a requested 60 d clamped to 30 d, 403 without `admin:users`, and 400 for `telegram_id<=0`.
- [ ] T5. `TestAgentToken_HasJti`: newly minted account tokens carry a `jti`, and an account token minted without one still authenticates.
- [ ] T6. `TestAudienceSeparation`: a runtime token is rejected by the account provider. An account token is not `ClaimOnly`. A job token is not accepted as a runtime token.
- [ ] T7. `TestErrorCodes_Closed`: every agentapi error response in the handler tests carries a `code` from `ErrorCodes()`, and the `error` text matches the pre-change strings.
- [ ] T8. `docs/agent_job_api_test.go`: the doc's route and code tables equal `Routes()` and `ErrorCodes()`.
- [ ] T9. `TestRegister_RoutesUnchanged`: `Register` binds exactly the 16 current method/pattern pairs.
- [ ] T10. `TestClaudeInvoker_FinishRunUsesJobToken` and `TestOpenAIRunner_FinishRunUsesJobToken`.
- [ ] T11. `internal/agenteval` conformance unit tests: a scripted client that is correct passes. Using the claim token on `GET /jobs/{id}`, using job A's token for job B, and calling a tool outside `job_tools` each produce the matching recorded violation and a failing `Score`. `TestNoPathToEffects` covers `conformance.go`.
- [ ] T12. `cmd/agent-conformance` end-to-end with a scripted fake worker binary built in the test: exit 0 and a JSON report bound to `agenteval/2`. A misbehaving variant gives exit 1.

## Rollback

All changes are code and docs, with no migration and no gitops change.
- Revert the PRs in reverse order. The runtime-token route and provider disappear with the revert, and any runtime tokens already minted stop authenticating (401). That is a safe failure: the account's jobs route to the owner after `AGENT_UNCLAIMED_ROUTE_AFTER`, like any unclaimed job.
- To stop a single external runtime without reverting, revoke its `jti` with the existing `revoke_worker_token` tool (effective within 15 s, including its derived job tokens). Blanket revocation by Telegram id also covers it.
- The `code` field and the account-token `jti` are additive. Reverting them leaves existing workers unaffected.
- The conformance harness is opt-in tooling and has no runtime effect. Reverting `HarnessVersion` to `agenteval/1` restores the old binding for P4.3 eval runs.
