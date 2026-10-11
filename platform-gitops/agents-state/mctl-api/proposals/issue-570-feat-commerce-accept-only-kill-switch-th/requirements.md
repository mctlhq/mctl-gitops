# Commerce accept-only kill switch that keeps reconciliation running

## Context

Today `COMMERCE_DISABLED` is the only commerce kill switch. In
`cmd/api/main.go` it leaves `commerceStore` nil, and `requireCommerce` in
`internal/api/handlers_commerce.go` then answers 503 on every
`/api/v1/commerce*` route. The ledger goes dark: tenants cannot read their
receipts, and `POST /api/v1/commerce/reconcile/expired`, `…/release` and
`…/finalize` stop too. Any outstanding liability (accepted, reserved,
dispatching, dispatched or `outcome_unknown` rows, plus their holds) is then
frozen rather than drained.

The disable procedure of C5 (mctlhq/mctl-agents#620, part of
mctlhq/.github#173) needs a narrower switch that stops only **new paid
acceptances**. While it is on, minting a quote and accepting an invocation
are refused with the existing ADR 020 sec. 13 reason code
`unsupported-execution` (`commerce.ReasonUnsupportedExecution`; the owner
decided this on 2026-10-11 so that no new code is added). Every other
commerce route keeps working, so reconcile, release, finalize and
settlement can bring every non-terminal invocation to a terminal phase.

## User stories

- AS a platform operator I WANT to stop new paid acceptances without turning the ledger off SO THAT outstanding liability can still drain through reconcile, release and finalize.
- AS a tenant owner I WANT my budget, quotes and invocation receipts to stay readable while acceptance is paused SO THAT I can see what I owe and what was released.
- AS the commerce gateway (C4) I WANT a refusal code from the existing ADR 020 vocabulary SO THAT I can pass it to the caller verbatim and do not need a new mapping.
- AS an operator following the C5 runbook I WANT a documented enable/disable order SO THAT I never switch the ledger off while liability is still open.

## Acceptance criteria (EARS)

- WHEN the process starts with `COMMERCE_ACCEPT_DISABLED` set to a value that `killSwitchOn` reads as on THE SYSTEM SHALL record the accept-only switch as on and log a warning naming the variable.
- WHEN `COMMERCE_ACCEPT_DISABLED` is unset or set to a value `killSwitchOn` reads as off (`""`, `false`, `f`, `0`, `no`, `off`) THE SYSTEM SHALL behave exactly as it does today.
- WHILE the accept-only switch is on and the commerce store is configured, WHEN an authorized caller sends `POST /api/v1/commerce/tenants/{tenant}/quotes` THE SYSTEM SHALL refuse with HTTP 422 and error code `unsupported-execution`, and SHALL NOT call `commerce.Store.MintQuote`.
- WHILE the accept-only switch is on and the commerce store is configured, WHEN an authorized caller sends `POST /api/v1/commerce/tenants/{tenant}/invocations` THE SYSTEM SHALL refuse with HTTP 422 and error code `unsupported-execution`, and SHALL NOT call `commerce.Store.AcceptInvocation`. This includes a request that would have replayed an existing row.
- WHILE the accept-only switch is on THE SYSTEM SHALL keep the existing authentication, tenant-access (404) and identity (`identity-unresolved`) checks ahead of the switch refusal, so the refusal reveals nothing about a tenant the caller cannot see.
- WHILE the accept-only switch is on THE SYSTEM SHALL write a `denied` audit entry for each refused quote or accept, with operation `commerce-quote-mint` or `commerce-invocation-accept` and a message naming the switch.
- WHILE the accept-only switch is on THE SYSTEM SHALL serve every other `/api/v1/commerce*` route (terms, quote/invocation/transition reads, budget routes, `…/reserve`, `…/dispatch`, `…/finalize`, `…/release`, `…/transitions`, `/invocations/overdue`, `/reconcile/expired`, `/dispatch-keys`) exactly as when the switch is off.
- WHILE the accept-only switch is on, WHEN the reconciler runs on an `accepted` invocation whose quote has expired, or on a `reserved` invocation past its reservation deadline, THE SYSTEM SHALL move it to `refused` or `released` as it does today.
- IF both `COMMERCE_DISABLED` and `COMMERCE_ACCEPT_DISABLED` are on THEN THE SYSTEM SHALL behave as `COMMERCE_DISABLED` alone: every commerce route answers 503 "commerce ledger not configured".
- IF `COMMERCE_ACCEPT_DISABLED` is on THEN THE SYSTEM SHALL still validate the dispatch signing key in `config.validate`, because dispatch stays live for rows that were accepted before the switch.
- WHEN an operator reads `docs/commerce-ledger.md` THE SYSTEM documentation SHALL describe `COMMERCE_ACCEPT_DISABLED`, its refusal, which routes stay live, and the enable and disable order relative to `COMMERCE_DISABLED`.

## Out of scope

- A fault-injection hook on `SimulatedAuthorizer`. The owner decided on 2026-10-11 that the settlement-only retry is proven offline only.
- A new reason code. `unsupported-execution` is reused, and ADR 020 sec. 13 stays unchanged.
- A runtime (no-restart) toggle, an admin endpoint or an MCP tool to flip the switch. It is an env var like every other kill switch.
- Blocking `…/reserve` or `…/dispatch` on rows accepted before the switch was turned on. The issue says everything else stays unchanged, and those rows are existing liability that must be allowed to complete or release.
- Turning the switch on in the deployed environment. This proposal only adds the capability; the deployed values stay off.
- An automatic reconciler schedule. `POST /reconcile/expired` stays operator- or cron-driven, as today.

## Owner decisions (2026-10-11)

- The accept-only refusal is HTTP **422** with code `unsupported-execution`, not 503. The mctl-agents commerce client classifies every 5xx as `UNKNOWN` (`orchestrator/commerce.py::_classify`), so a 503 would be reported to the agent as `outcome-unknown` / ledger unreachable while nothing is held. This resolves the first open question below.
- Refusing replayed accepts while paused is accepted: the C4 gateway resumes through `GET …/invocations?idempotency_key=…` (`_find`) before it ever re-accepts.
- Reserve/dispatch of rows accepted before the switch stay allowed, as proposed.

## Open questions (all resolved; kept for history)

- **RESOLVED 2026-10-11 (owner): 422, not 503; see Owner decisions above. The text below is the superseded original question.** HTTP status for the refusal. The issue fixes the code (`unsupported-execution`) but not the status. This proposal uses 503: the condition is temporary and operator-controlled, it matches the existing `dispatch-unavailable` 503, and a 422 would read as a permanent refusal of this specific call. If the C4 gateway in mctl-agents treats 503 as "retry automatically", 422 may be preferred. The reviewer should confirm against the gateway's mapping.
- **RESOLVED 2026-10-11 (owner): accepted as proposed; see Owner decisions above.** Replayed accepts. The proposal refuses every `POST …/invocations` while the switch is on, including one that would only have returned an existing row with `replayed: true`. This is the simplest reading of the issue. A gateway resuming after a restart can use `GET …/invocations?idempotency_key=…` instead, which stays live. Allowing replays would require reaching the store first, which weakens "accept is refused before any write".
- **RESOLVED 2026-10-11 (owner): accepted as proposed; see Owner decisions above.** Reserve and dispatch of rows accepted before the switch stay allowed (see Out of scope). If C5 wants "no new holds" as well as "no new acceptances", that is a separate, broader switch.
