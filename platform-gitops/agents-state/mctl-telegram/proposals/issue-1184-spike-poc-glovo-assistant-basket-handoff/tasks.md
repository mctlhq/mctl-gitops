# Tasks: issue-1184-spike-poc-glovo-assistant-basket-handoff

- [ ] 1. D1 baseline report `docs/reports/glovo-assistant-spike.md`.
  - Temporal inventory with mctl-gitops paths, marked deployed or candidate: `tenant-namespace-job.yaml`, `networkpolicy.yaml`, `services/admins/mctl-agents-worker*/values.yaml`, `bootstrap/templates/mctl-platform/mctl-api.yaml`, `services/labs/mctl-telegram/values.yaml`.
  - Duplicate map to #1002, #1048, #1088, .github#318/#173/#309, mctl-agents#198/#333 and mctl-gitops#1810/#1818.
  - Provider evaluation (Discover MCP, `denya/glovo-skill`, partner APIs), with Montenegro, terms and continuity marked UNVERIFIED.

  DoD: every claim cites a path or URL; no cookies or tokens appear anywhere.
- [ ] 2. D2 ADR candidate `docs/adr/0009-assistant-temporal-tenancy.md` (status Proposed), plus an index entry in `docs/adr/README.md`. (depends on 1)
  - Options A, B (shared `mctl-assistants`, including the per-tenant-queue variant) and C, compared on queues, Kubernetes namespaces, worker sizing, retention, authorizer and NetworkPolicy prerequisites, blast radius and cost.
  - Identity chain, with fail-closed cases.
  - Promotion criteria from B to C.
  - The BLOCKER statement.

  DoD: `go test ./docs/...` passes; the ADR names one target and the blocking prerequisites.
- [ ] 3. D3 contract `docs/contracts/glovo-checkout-handoff.md`. (depends on 2)
  - Provider adapter interface (no pay or place).
  - `OrderSnapshot`, `GlovoOrderWorkflow` states, the fingerprint definition and consent binding.
  - Handoff token (hash-only, single-use, TTL).
  - `OUTCOME_UNKNOWN` semantics.
  - Schedule-to-workflow ID scheme with RejectDuplicate.
  - Retry discipline: reads only, writes verified by read-back.
  - Telegram UI and the portable MCP tool shapes.

  DoD: the contract agrees with requirements.md and names the owner repo for each part.
- [ ] 4. Create the separate Go module `test/glovo-poc/` (own `go.mod`, `go.temporal.io/sdk` there only), with an `httptest` fake Glovo API (stores, menus, past orders, modifiers, fees, availability flips, timeouts, per-session carts). (depends on 3)

  DoD: `go build ./...` at the repo root is unchanged; the module refuses non-loopback addresses.
- [ ] 5. In-memory control-plane stand-in in `test/glovo-poc/controlplane`. (depends on 4)
  - Identity chain resolver, order index and scope check on `(tenant_id, owner_principal_id, order_id)`.
  - Handoff tokens.
  - Mock Automation Control Plane schedule fire.
  - Synthetic tenants alpha (Alice), beta (Bob) and gamma (Carol, unauthorized).

  DoD: personas follow CLAUDE.md; IDs are checked with `git grep`.
- [ ] 6. `GlovoOrderWorkflow` and activities in `test/glovo-poc/workflows`. (depends on 5)
  - `RevalidateScope` before every write, signal and fire.
  - Opaque refs only in workflow inputs.
  - A data converter that rejects payloads containing canary secrets.

  DoD: runs on the Temporal SDK test environment.
- [ ] 7. Implement tests T1 to T18 below, plus a `leakcheck` that exports histories and logs and searches them for canaries. (depends on 6)

  DoD: `cd test/glovo-poc && go test ./...` is green offline.
- [ ] 8. D5 risk matrix and decision in the report. (depends on 7)
  - Threat model entries extending `docs/agent-runtime/threat-model.md` T3, T10 and T12.
  - Decision value (expected `MOCK_ONLY_PENDING_CONNECTOR`, target `GO_SHARED_AFTER_HARDENING`).
  - Real-phone continuity: UNVERIFIED unless a consented, no-payment manual proof is recorded without personal data.
  - Child issues by owner repo:
    - mctl-api: order index, assistant install keyed by tenant and principal, personal scope;
    - mctl-gitops: `mctl-assistants` namespace, client auth and authorizer, provider worker namespace and NetworkPolicy;
    - mctl-telegram: owner-channel Glovo commands and UI;
    - .github#318: schedule contract;
    - mctl-agents: reuse of human input.

  DoD: the report has a decision line, and every follow-up is a draft issue text, not a PR.

## Tests

All tests are in `test/glovo-poc`, offline, against the fake API and Temporal test env.

- [ ] T1. Catalog and search: a store and menu search returns structured items; raw menu text never reaches workflow history.
- [ ] T2. Repeat a previous order: "last Wednesday without drink" resolves to the past order minus the drink item, with the correct fingerprint.
- [ ] T3. Modifiers: a required modifier missing leads to an ask; an invalid modifier is rejected before quote.
- [ ] T4. Basket diff or collision: the existing provider cart content is shown as a diff and is never silently overwritten.
- [ ] T5. Availability or fee change between consent and verify leads to `basket_changed` and a re-ask, with no handoff.
- [ ] T6. Safe revalidation: an install revision bump mid-order leads to `stale_install`, with no provider write.
- [ ] T7. Single-use handoff: the second use is refused and the first use moves to `handoff_opened` then `OUTCOME_UNKNOWN`, never `paid`.
- [ ] T8. Expired consent or handoff TTL leads to `consent_expired`, and the token is refused.
- [ ] T9. A cancelled or revoked install mid-wait stops the order; encrypted order state and the session ref are deleted.
- [ ] T10. Duplicate schedule fire (same occurrence, including after a simulated crash and restart) produces exactly one workflow run.
- [ ] T11. Provider timeout: reads are retried with backoff; a write timeout is followed by a read-back verify, never a blind re-mutation.
- [ ] T12. A duplicate button press (the same consent signal twice) is applied once and the second is acknowledged.
- [ ] T13. Unknown checkout outcome: with no confirmation evidence the status is `OUTCOME_UNKNOWN` indefinitely.
- [ ] T14. Cross-tenant: Bob (beta) cannot list, query, signal, consent or open the handoff for Alice's (alpha) order through the control-plane surface. The response does not reveal whether the order exists.
- [ ] T15. Unauthorized and ambiguous identity: Carol (gamma, no install), an unlinked Telegram ID, a revoked link, and a principal with two tenants and no explicit choice all fail closed. None is assigned the default `mctl` tenant.
- [ ] T16. No direct Temporal route: the surface API has no parameter naming a namespace, workflow ID or run ID. Supplying one is refused.
- [ ] T17. Secret non-disclosure: the canary session token, address and cart contents are absent from exported histories, search attributes, logs and LLM tool results.
- [ ] T18. Provider isolation: a fake provider stuck returning 429 for tenant alpha opens the provider breaker without stalling the control queue for a second, fake provider; per-tenant limits keep beta progressing.

## Rollback

Nothing is deployed and no flag, schema or GitOps file changes. To roll back, revert
the commit or commits that add the three docs, the ADR index entry and the
`test/glovo-poc/` module, or delete those paths. The root module and the server
binary are unaffected either way.
