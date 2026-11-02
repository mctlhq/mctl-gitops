# External runtime contract: threat model, agent job API docs, conformance harness, claim-only runtime credentials

## Context

Issue #1046 (P4.5 of epic #1002, tier T4 "own runtime") asks for a contract under
which a runtime that MCTL does not operate can run an account's assistant. The
invariant is fixed by the issue: an external runtime may reason, but it never
gets authority to bypass MCTL execution policy. The only path is claim ->
external model -> propose -> MCTL policy -> MCTL send. The runtime holds no
Telegram credentials. Today `docs/assistants/spec.md` (tier table, row "T4 Own
runtime") describes T4 as "account-scoped token; policy enforced server-side",
and the only worker that exists is first-party (`cmd/agent-worker`). ADR 0008
(`docs/adr/0008-managed-runtime.md`) already names #1046 as its foundation.

Policy enforcement is already server-side (`internal/agentapi`,
`internal/agent/policy`, the send gate of ADR 0002). Per-job credentials
(`aud=agent-job`, `mintJobToken` in `internal/agentapi/events.go`) are bound to
job, attempt, conversation and tool set. The gaps are elsewhere:
- No threat model exists.
- The job API is documented only indirectly, in `docs/agent-worker.md` and code comments.
- Error responses are free-form `{"error": "<text>"}` strings.
- The C1 harness (`TestC1ObserveEval`) can only drive the in-repo runners.
- The credential handed to a worker is the account token (`aud=agent`, `POST /api/agent/token`). It lasts 30 days by default (90 days max), has no `jti`, works on every route and is not bound to any conversation.

This proposal makes four deliverables, in the issue's order. It decides that
external runtimes get only a claim-only, short-lived, `jti`-revocable runtime
credential plus the per-job tokens the server mints at claim, and never the
account-wide token.

## User stories

- AS an account owner running my own worker (T4) I WANT a documented, versioned job API SO THAT I can build a runtime without reading mctl-telegram's source.
- AS an account owner I WANT the credential I give an external runtime to be claim-only, short-lived and individually revocable SO THAT a leaked runtime credential cannot read arbitrary conversations, act outside a claimed job, or outlive my intent.
- AS a security reviewer I WANT a written threat model of what an external worker can read and do SO THAT changes to the job API are reviewed against stated assets, trust boundaries and mitigations.
- AS a runtime author I WANT to run the C1 conformance harness against my own worker binary or deployment SO THAT I can show it completes jobs, respects the job binding and the tool set, and never leaks restricted data before I connect it to a real account.
- AS an operator I WANT stable machine-readable error codes on the job API SO THAT external runtimes can handle refusals (binding, tool gate, fence, policy) without matching message text.

## Acceptance criteria (EARS)

Threat model
- THE SYSTEM SHALL include `docs/agent-runtime/threat-model.md`. It names assets, actors, trust boundaries and threats, and gives a mitigation for each threat that cites the enforcing code. It covers at least:
  - what an external worker can read (event bodies, conversation context, owner profile view, instructions with owner notes, leads/records, policy);
  - credential theft and replay;
  - job binding and cross-job/cross-account access;
  - tool-set widening;
  - prompt injection via inbound messages;
  - cost misreporting;
  - denial of service.
- THE SYSTEM SHALL record every accepted residual risk in the threat model with an owner and a revisit trigger. Example: bearer tokens are not sender-constrained.

API contract
- THE SYSTEM SHALL include `docs/contracts/agent-job-api.md`. It documents every route registered by `agentapi.Server.Register` with:
  - method, path, the credentials it accepts (runtime, job, account), request and response schema, and binding checks;
  - the tool each route serves (`tools.Endpoints`);
  - error codes.
- WHEN a route is added to or removed from `agentapi.Server.Register` without a matching change to `docs/contracts/agent-job-api.md` THE SYSTEM SHALL fail `go test ./docs/...`.
- WHEN the agent API refuses a request THE SYSTEM SHALL return a JSON body carrying both the existing `error` string and a stable `code` from the documented enum.
- WHEN a code is returned THE SYSTEM SHALL use only codes listed in the contract doc, enforced by a test.

Scoped credentials
- WHEN an admin calls `POST /api/agent/runtime-token` with `{telegram_id, ttl_hours}` THE SYSTEM SHALL mint a token with `aud=agent-runtime`, `sub=tg:<id>`, a fresh `jti`, `orig_iat`, a default TTL of 7 days, and any requested TTL clamped to 30 days.
- WHEN an identity authenticated with `aud=agent-runtime` calls any agent API route other than `POST /jobs/claim` THE SYSTEM SHALL refuse it with 403 and code `credential_claim_only`, and audit the refusal as `denied`.
- IF an `agent-runtime` identity claims jobs and no job-token signer is configured THEN THE SYSTEM SHALL refuse the claim with 503 and code `job_token_unavailable`, and SHALL NOT return a job without a `job_token`.
- WHEN a job is claimed with an `agent-runtime` credential THE SYSTEM SHALL mint the job token with the runtime credential's `jti` and `orig_iat`, so that revoking the runtime `jti` revokes every job token derived from it within `localjwt.MaxRevocationCacheTTL` (15 s).
- WHEN an admin blanket-revokes a Telegram id THE SYSTEM SHALL reject that id's `agent-runtime` tokens and the job tokens derived from them, because `agent-runtime` is in `derivedAudiences`.
- WHEN `POST /api/agent/token` mints an account token THE SYSTEM SHALL include a fresh `jti`, so account tokens become individually revocable as well.
- WHILE the agent API is mounted THE SYSTEM SHALL keep accepting existing `aud=agent` account tokens on every route they reach today. Backward compatibility for the first-party worker is kept.
- THE SYSTEM SHALL document in the contract and the threat model that external runtimes are issued only `agent-runtime` credentials.

Conformance harness
- WHEN `AGENT_CONFORMANCE=1` and `AGENT_CONFORMANCE_WORKER_CMD` is set THE SYSTEM SHALL start the named command with `AGENT_API_BASE_URL` pointing at the harness's fake agent API and `AGENT_API_TOKEN` set to a harness-issued claim-only token. It SHALL then serve the selected suite's fixtures one job per claim and score the run.
- WHEN `AGENT_CONFORMANCE=1` and `AGENT_CONFORMANCE_LISTEN` is set instead THE SYSTEM SHALL serve the same fake API on that address for an externally started worker. It SHALL print the base URL and claim token, and stop after every fixture is terminal or `AGENT_CONFORMANCE_TIMEOUT` elapses.
- WHEN the worker under test calls a per-job route with the claim token, or a route with a job token for a different job, attempt or conversation THE SYSTEM SHALL record a binding violation, and the run SHALL fail.
- WHEN the worker under test calls a route outside the job's tool set THE SYSTEM SHALL answer 403 `tool_not_allowed`, as `toolGate` does, and record it.
- THE SYSTEM SHALL pass a conformance run only if all of the following hold:
  - classification meets the suite threshold (hr-recruiter@0.1.0: at least 29 of 32);
  - every fixture reaches a terminal status;
  - there are zero leaks, zero binding violations, zero claim-token-on-job-route uses and zero wrong auto-sends.
- THE SYSTEM SHALL bind each conformance report to `agenteval.HarnessVersion`, the suite digest and the definition digest. The report SHALL contain no model text.
- WHILE `go test ./...` runs without `AGENT_CONFORMANCE=1` THE SYSTEM SHALL skip the model-driven conformance run and spend no model quota. The model-free protocol tests of the harness itself SHALL still run.

## Out of scope

- Self-service minting of runtime tokens by account owners (portal or MCP tool). Minting stays admin-only (`admin:users`), as for every worker credential today.
- The managed pool credential (`aud=agent-pool`) and its claim semantics. These are ADR 0008 / #1090. This proposal provides the generic claim-only guard that #1090 reuses.
- Sender-constrained tokens (DPoP, mTLS). They are recorded as a residual risk.
- Revoking or shortening existing `aud=agent` account tokens already in use, and removing the account token entirely.
- Changes to the policy engine, the send gate, or the assistant definition format.
- Publishing conformance results to the assistant registry or gating promotion on them.

## Open questions

- Restricting existing account tokens: should `aud=agent` account tokens also become claim-only, ending their per-job and cross-conversation reach, once the first-party worker always uses job tokens? This proposal leaves them unchanged and documents them as first-party only. A follow-up can flip them behind a flag.
- Runtime token TTL: are 7 days (default) and 30 days (cap) the right values? A runtime has no browser to re-authenticate from, so the token cannot be hours-long. The values could be shorter if a renewal route is added, mirroring `internal/workertoken/renewhandler.go`. This proposal does not add one.
- Meaning of "endpoint" in the issue's "any worker binary or endpoint": this proposal reads it as a worker running elsewhere that is pointed at the harness's listen address. It could instead mean a worker that exposes its own HTTP endpoint which the harness calls, but no such worker protocol exists, since workers pull jobs and nothing pushes to them.
- Deployed state: only the gitops values files were read. The live pod env (for example the effective `AGENT_JOB_VISIBILITY`, which is unset in values and so presumably the 5 min default) and replica state were not observed with mctl tools in this run. The design does not depend on them, but the job-token TTL figure in the threat model should be confirmed against the running service.
- Should owner notes (part of the rendered `instructions` in the claim envelope) be withheld from external runtimes, or is sending them acceptable? They are owner-authored and already go to the first-party runtime's model provider. The threat model lists them as readable, and this proposal does not change it.
