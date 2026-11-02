# External runtime contract: threat model, agent job API reference, black-box conformance runner, credential-boundary documentation

## Context

Issue #1046 (P4.5 of epic #1002, tier T4 "own runtime") asks for a contract under
which a runtime that MCTL does not operate can run an account's assistant. The
invariant is fixed by the issue: an external runtime may reason, but it never
gets authority to bypass MCTL execution policy. The only path is claim ->
external model -> propose -> MCTL policy -> MCTL send. The runtime holds no
Telegram credentials.

The owner decided the credential boundary on 2026-11-02 (comment on #1046) and
confirmed it when rejecting the first version of this proposal (digest
`sha256:d984e987a2c80bc58f421794dc94bebff5502ed7cf612f965f4f763ae0d7e409`):

- **Own / external runtime** keeps the existing account-scoped `aud=agent`
  token. The own credential path is not changed.
- **Managed runtime** will use a claim-only `aud=agent-pool` credential, then
  job-bound `aud=agent-job`. That is implemented later in #1090, together with
  the proof that revoking the pool credential kills the job tokens derived
  from it.

This proposal therefore changes no runtime behaviour of the agent API. It
delivers documentation and one opt-in tool, in the issue's order:

1. a threat model for the own/external runtime;
2. a reference for the CURRENT agent job API, including its current error
   semantics;
3. a minimal black-box conformance runner that reuses the existing C1 fixtures
   and gates;
4. documentation of the credential boundary above.

Policy enforcement is already server-side (`internal/agentapi`,
`internal/agent/policy`, the send gate of ADR 0002). Per-job credentials
(`aud=agent-job`, `mintJobToken` in `internal/agentapi/events.go`) are bound to
job, attempt, conversation and tool set where they are issued. The gaps this
proposal closes are the missing threat model, the missing API reference, and a
C1 harness that can only drive the in-repo runners.

## User stories

- AS an account owner running my own worker (T4) I WANT a documented job API SO THAT I can build a runtime without reading mctl-telegram's source.
- AS a security reviewer I WANT a written threat model of what an external worker holding the account-scoped token can read and do, including its blast radius, SO THAT changes to the job API are reviewed against stated assets, trust boundaries and mitigations.
- AS a runtime author I WANT to run the C1 conformance checks against my own worker binary or deployment SO THAT I can show it completes jobs, respects the job binding and tool set, and never leaks restricted data before I connect it to a real account.
- AS the platform owner I WANT the own-vs-managed credential boundary written down SO THAT #1090 starts from an agreed contract.

## Acceptance criteria (EARS)

Threat model
- THE SYSTEM SHALL include `docs/agent-runtime/threat-model.md`. It names assets, actors, trust boundaries and threats, and gives a mitigation for each threat that cites the enforcing code. It covers at least:
  - what an external worker can read (event bodies, conversation context, owner profile view, instructions with owner notes, leads/records, policy);
  - Telegram context exposure;
  - replay and token theft;
  - job binding and cross-job / cross-account access;
  - stale or revoked credentials;
  - a compromised worker and a compromised model provider;
  - the prompt/tool-injection boundary;
  - why the worker cannot send Telegram messages directly.
- THE SYSTEM SHALL state in the threat model the blast radius of the account-scoped `aud=agent` token as it is today: its TTL, that it carries no `jti`, that it can claim, read any conversation's context, leads and events of the account, and call every per-job route for any job of the account, and how it can be revoked.
- THE SYSTEM SHALL record every accepted residual risk with an owner and a revisit trigger. Examples: bearer tokens are not sender-constrained; the account-scoped token is wide; owner notes and the engaged profile view reach a model provider MCTL does not choose. The threat model documents the owner-notes exposure and does not change it.
- WHEN a route is added to or removed from `agentapi.Server.Register` THE SYSTEM SHALL fail `go test ./docs/...` unless every route is still named in the threat model's read-exposure table or threat list.

API contract reference
- THE SYSTEM SHALL include `docs/contracts/agent-job-api.md`, a reference for the agent job API as it behaves now. It documents every route registered by `agentapi.Server.Register` with: method, path, the credentials it accepts today (account `aud=agent`, job `aud=agent-job`), request and response schema, binding checks, and the tool the route serves (`tools.Endpoints`).
- THE SYSTEM SHALL document the lifecycle: claim, events/context, propose, request approval, owner summary, complete, job status, cost report. It documents deadlines, retry and idempotency expectations, and the fencing rules (attempt, `install_revision`) as the code implements them.
- THE SYSTEM SHALL document the CURRENT error semantics: HTTP statuses and the existing `{"error": "<text>"}` bodies, and the `policy.DenyCode` values that policy refusals carry. It SHALL NOT introduce new error codes or change any response body.
- WHEN a route is added to or removed from `agentapi.Server.Register` without a matching change to `docs/contracts/agent-job-api.md` THE SYSTEM SHALL fail `go test ./docs/...`.

Credential boundary
- THE SYSTEM SHALL document in the threat model, in the contract, and in the `docs/assistants/spec.md` T4 row that an own/external runtime uses the existing account-scoped `aud=agent` token, and that job-level binding comes from the `aud=agent-job` tokens the server mints at claim where they are issued.
- THE SYSTEM SHALL document the planned managed model as design intent only: claim-only `aud=agent-pool`, then job-bound `aud=agent-job`, implemented in #1090 and ADR 0008. The documents SHALL mark it as not implemented.
- THE SYSTEM SHALL NOT change any credential minting, verification, audience, TTL, `jti` or revocation behaviour, the claim handler, or the token handlers.

Conformance runner
- THE SYSTEM SHALL provide `cmd/agent-conformance`, a CLI that runs the existing C1 suite fixtures and gates against a worker it does not link.
- WHEN `--worker-cmd` is given THE SYSTEM SHALL start a loopback fake agent API, exec the command with `AGENT_API_BASE_URL` pointing at it and `AGENT_API_TOKEN` set to a harness-issued token, serve the suite's fixtures one job per claim through `POST /jobs/claim`, and score the run.
- WHEN `--listen` is given instead THE SYSTEM SHALL serve the same fake API on that address for an externally started worker, print the base URL and token, and stop after every fixture is terminal or the timeout elapses.
- THE SYSTEM SHALL reuse the existing `agenteval` fixtures, `Task` fake and `Score` gates. It SHALL NOT add a new evaluation framework, violation class or scoring rule, and SHALL NOT change what the in-process `TestC1ObserveEval` measures.
- THE SYSTEM SHALL mirror production credential semantics in the fake: the harness-issued token stands for the account-scoped token, and it is accepted wherever production accepts `aud=agent`. A per-job token minted per job is returned in the claim envelope, and existing binding checks apply to it as they do today.
- THE SYSTEM SHALL route every per-job request to the fixture that owns its job token, or its job id when the harness token is used, for the whole run. A request SHALL NOT be routed to a fixture merely because that fixture was claimed most recently. WHEN a request cannot be attributed to exactly one fixture THE SYSTEM SHALL answer 409 and record a binding violation.
- WHEN a job token is used after its job is terminal and after later fixtures were claimed THE SYSTEM SHALL still resolve it to its own fixture, answer the status read and the cost report as production does, answer a write with 409, and leave every other fixture's record unchanged.
- WHEN every fixture is terminal or the timeout elapses THE SYSTEM SHALL NOT stop at once. It SHALL let the post-terminal status reads and cost reports of every fixture arrive (bounded by a quiet period and an overall maximum), release a long-polling worker with an empty claim, stop the worker command gracefully, shut the HTTP server down gracefully so in-flight requests finish, and only then compute the report. A settle timeout SHALL be reported and SHALL NOT change the pass/fail rule.
- THE SYSTEM SHALL pass a conformance run only if the existing C1 bar holds: classification meets the suite threshold (hr-recruiter@0.1.0: at least 29 of 32), every fixture reaches a terminal status, and there are zero leaks, zero binding violations and zero wrong auto-sends.
- THE SYSTEM SHALL bind each report to `agenteval.HarnessVersion`, the suite digest and the definition digest, and the report SHALL contain no model text.
- WHILE `go test ./...` runs without `AGENT_CONFORMANCE=1` THE SYSTEM SHALL skip the model-driven conformance run and spend no model quota. The model-free protocol tests of the harness itself SHALL still run.

## Out of scope

Removed from the first version of this proposal by the owner, and not to be reintroduced:

- `POST /api/agent/runtime-token` and any new `agent-runtime` credential model;
- a `ClaimOnly` flag or any change to the current `aud=agent` path;
- `requireNotClaimOnly` guards across agent routes;
- changes to `handleClaimJobs` for claim-only credentials;
- changing `NewAgentTokenHandler` credential semantics for own runtime, including adding a `jti`;
- switching existing own runners (`ClaudeInvoker`, `OpenAIRunner`) to a new credential flow;
- the derived-token revocation proof (`TestRuntimeRevocation_KillsDerivedJobToken` or equivalent): it belongs to #1090;
- the `aud=agent-pool` implementation: #1090;
- refactoring `Server.Register`;
- converting agent API errors to a new stable error-code enum, or adding a `code` field to responses;
- any change to owner-note visibility;
- any decision on token TTL policy;
- a Dockerfile change to ship the conformance binary;
- bumping `agenteval.HarnessVersion` (no scoring or in-process behaviour changes);
- self-service minting of tokens by account owners, sender-constrained tokens, publishing conformance results to the assistant registry, and any change to the policy engine, the send gate or the assistant definition format.

## Open questions

- Meaning of "endpoint" in the issue's "any worker binary or endpoint": this proposal reads it as a worker running elsewhere that is pointed at the harness's listen address. It could instead mean a worker that exposes its own HTTP endpoint which the harness calls, but no such worker protocol exists, since workers pull jobs and nothing pushes to them. Say if a push protocol is wanted; it would be a separate issue.
- Deployed state: only the gitops values files were read. The live pod env (for example the effective `AGENT_JOB_VISIBILITY`, which is unset in values and so presumably the 5 min default) was not observed with mctl tools. The job-token TTL figure in the threat model must be confirmed against the running service before the document states it as fact.
