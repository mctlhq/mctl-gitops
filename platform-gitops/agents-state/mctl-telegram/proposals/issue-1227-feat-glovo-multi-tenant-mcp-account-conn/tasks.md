# Tasks: issue-1227-feat-glovo-multi-tenant-mcp-account-conn

Approval of this proposal authorises **Part A (M0)** only. Part B (M1) is fully specified
so it can be reviewed now, but it is built only after gates G1 and G2 are recorded and a
separate M1 approval is given. M2 and M3 are gate definitions, not tasks here. No task in
this file deploys anything, publishes an image, provisions `glovo.mctl.ai`, logs in to a
real Glovo account or writes to a provider basket.

## AMEND 2026-11-08 — extra acceptance gates (documentation-only M0)

- [ ] M0-A. Replace any `human-input approval` assertion with `aar_` action approval + receipt gate; record exact binding of tenant, owner, one execution `we_`, connection, install revision, fingerprint, hashed basket intent and target. Negative test fixture must show `hir_` answer never authorizes a provider mutation.
- [ ] M0-B. Describe G2 as a **separate mctl-api implementation** proposal+approved/merged PR with tests for tenant and same-tenant owner separation, subject resolution, order/connection registry, revocation and `aar_` receipt. Do not count mctl-api#948/#950 (contract-only) as delivery.
- [ ] M0-C. State precise secret lifecycle: durable master+HKDF-derived key is NOT crypto-erasure on ciphertext deletion. Use random per-connection DEK with wrapping and revocation/backup retention evidence, or weaken claim to data deletion only. Add revoke+backup+cache test criteria.
- [ ] M0-D. Explicit two Temporal namespaces and cross-namespace Nexus or authenticated mctl-api bridge decision/gate; negative test provider identity cannot signal control/DevLoop.
- [ ] M0-E. Make M1 `glovo_connect_account` explicitly fake-only. G3 requires legally/technically reviewed real account access and verified mobile basket continuity, no checkout/order/payment, no hosted/shared `session.json`.
- [ ] M0-F. Explicitly preserve independent M1, image publication, GitOps, real-account, basket-write and pilot activation approvals. A #1227 M0 approval grants no execution of the M1 checklist.

## Part A: M0 (this approval)

- [ ] 1. Write `docs/reports/glovo-connector-feasibility.md`, following the labelling
  style of `docs/reports/mcp-apps-spike.md`. It has an evidence table with these rows:
  Glovo Discover MCP (search-only); `denya/glovo-skill` v0.2.1 (MIT, Node 18+, Chrome
  session bootstrap, `session.json`, basket read/add/change/remove after approval, no
  checkout); official or partner API; session lifecycle and refresh; mobile basket
  continuity; Montenegro coverage; Glovo consumer terms; MIT license obligations. It
  also compares reference vs subprocess vs reimplementation. — DoD: every cell is
  labelled `SOURCE` (link and date), `OBSERVED` or `UNVERIFIED`; nothing unverified is
  stated as fact; no credential, cookie or endpoint secret appears.
- [ ] 2. Write `docs/adr/0010-glovo-multitenant-connections.md` (status Proposed). 0009
  is reserved by PR #1187's tenancy ADR, so link to it rather than duplicate it. The ADR
  covers the system boundary, the frozen identity chain, the separate records (principal,
  membership, install/revision, connection, provider identity, secret), the connection
  and secret state machine, the five authorization checkpoints, the typed refusal codes,
  the decision `GO_FAKE_MULTITENANT` / `BLOCKED_PROVIDER_ACCESS` and the gate table
  G0-G6 (depends on 1). — DoD: it matches design.md; the dependency graph names
  .github#324, mctl-gitops#2456 and #2457, #1048, mctl-api#948 and .github#309.
- [ ] 3. Write `docs/contracts/glovo-mcp-tools.json` (`$id` with `v1alpha1`). It holds
  closed input and output JSON Schemas for the seven tools in design.md, plus the
  protected-resource metadata (`resource`, `scopes_supported`) (depends on 2). — DoD:
  every object has `additionalProperties: false`; every tool has a `required_scope`;
  `glovo_connect_account` is described as a "delegated account connection", never
  "OAuth".
- [ ] 4. Write `docs/agent-runtime/glovo-threat-model.md` in the shape of
  `docs/agent-runtime/threat-model.md`: assets, actors, trust boundaries, and threats
  with mitigation and test ID (T1-T16 below). It covers bootstrapping, session storage
  and rotation, CSRF, SSRF, remote browser, egress, abuse, token expiry, confused deputy
  and replay (depends on 2). — DoD: every threat row names a test ID from this file.
- [ ] 5. Add `docs/glovo_contract_test.go` (package of `docs/`, run by
  `go test ./docs/...`). It (a) parses `glovo-mcp-tools.json` and enforces the
  seven-tool allowlist, closed schemas, the forbidden tool-name pattern
  `place|pay|checkout|purchase|submit_order`, and the forbidden input properties
  (`tenant`, `tenant_id`, `principal`, `principal_id`, `namespace`, `task_queue`,
  `workflow_id`, `url`, `endpoint`, `cookie`, `session`, `password`, `token`); (b) checks
  that every test ID in the threat model appears in this tasks list and ADR; (c) scans
  the four new docs for credential-shaped strings (JWT, `Cookie:` or `Set-Cookie:`, long
  hex or base64) (depends on 3, 4). — DoD: the test passes, and a deliberately broken
  local copy (an extra `glovo_place_order`) makes it fail.
- [ ] 6. Draft the follow-up issue texts in the report's appendix only (do not open
  issues): the mctl-api contract (scope resolve, connections CRUD, orders, pilot
  allowlist) for G2, mctl-gitops namespace and identity work for G5, and the Glovo
  partner or legal outreach for G3 (depends on 2). — DoD: each draft names its gate and
  states "separate approval required".
- [ ] 7. Verify there is no regression: `go build ./...`, `go vet ./...` and
  `go test ./...` at the root; root `go.mod` and `go.sum`, `Dockerfile`,
  `Dockerfile.agent-worker` and `.github/workflows/*` unchanged (depends on 1-6). — DoD:
  `git diff --stat` touches only the four docs, the JSON contract and the new docs test.

## Part B: M1 (fake provider; requires G1 and G2 plus a separate approval; not built under this approval)

- [ ] 8. Create the module `providers/glovo/` with its own `go.mod`
  (`github.com/mctlhq/mctl-telegram/providers/glovo`). — DoD: `go build ./...` at the
  root does not enter it; root `go.mod` is unchanged.
- [ ] 9. `adapter/`: the `Adapter` interface (no place or pay methods) and the `fake`
  implementation, with synthetic stores, per-session carts, fault injection and a canary
  session (depends on 8). — DoD: unit tests cover every method, and each error maps to
  `ErrConnectorUnavailable` or `ErrExpired`.
- [ ] 10. `conn/`: the connection state machine (the six states and the allowed
  transitions only), new `gcn_` on reconnect, sealed secret store
  (`HKDF info="mctl-glovo-connection-v1"`, per `(tenant, connection)`), crypto-shred on
  revoke, Postgres and SQLite implementations in `glovo_*` tables (depends on 8). —
  DoD: illegal transitions are refused; a revoked blob is unreadable.
- [ ] 11. `authz/`: the `ScopeResolver` interface for the mctl-api contract, typed
  refusals, an in-memory resolver for tests, and `RevalidateScope` at the five
  checkpoints, with no tenant fallback (depends on 8). — DoD: there is no code path that
  reads a tenant from config or from args.
- [ ] 12. `mcpfacade/` plus `cmd/glovo-mcp`: the seven tools from the JSON contract,
  bearer validation (aud `https://glovo.mctl.ai/mcp`), protected-resource metadata, scope
  narrowing, idempotency keys and rate limits; the redaction handler reuses the
  `internal/audit/redact.go` keys plus `glovo_session`, `handoff_token` and
  `sealed_secret` (depends on 9-11). — DoD: the tool list served equals the JSON
  contract (a golden test).
- [ ] 13. `cmd/glovo-provider-worker` plus the control workflow under the Temporal
  `testsuite`: an order snapshot of IDs only, consent bound to
  `(order_id, fingerprint, install_revision, connection_id)`, `OUTCOME_UNKNOWN`, and
  derived workflow IDs with `RejectDuplicate` (depends on 9-11). — DoD: histories hold
  no canary.
- [ ] 14. `Dockerfile.glovo-mcp` and `Dockerfile.glovo-provider-worker` (non-root 1000,
  alpine), built in a CI job but not published (depends on 12, 13). — DoD: the CI job
  builds both; release-please config is unchanged.

## Tests

M0 (Part A):

- [ ] T0. `go test ./docs/...` passes `glovo_contract_test.go`: the tool allowlist,
  closed schemas, forbidden names and properties, threat-to-test cross-references and
  the credential-shape scan.

M1 (Part B, written in M1; IDs fixed now and referenced by the threat model). Synthetic
personas only: Alice (tenant-alpha), Bob (tenant-beta), Carol (tenant-alpha, second
user), Dana (no install). Run `git grep` on any numeric id before use.

- [ ] T1. Two tenants: Bob's token cannot read, prepare or query Alice's connection,
  orders or basket. The refusal is `not_authorized` and no adapter call is made.
- [ ] T2. Cross-tenant ID guessing: Bob passes Alice's `order_id` or `preview_id`. The
  answer is `not_found`, the same as a nonexistent ID.
- [ ] T3. Same tenant, different user: Carol cannot use Alice's connection; both connect
  independently and get distinct `gcn_` values and distinct sealed keys.
- [ ] T4. Revoke while a workflow is active: Alice revokes after consent but before
  `MutateBasket`. Checkpoint 3 refuses, the provider sees no write, and the state is
  `connection_revoked`.
- [ ] T5. Stale install: a reinstall at a new revision invalidates pending consents and
  in-flight orders (`stale_install`).
- [ ] T6. Confused deputy: a tool argument carrying `tenant_id`, `workflow_id` or
  `principal_id` is rejected by schema; a forged internal request to the worker without
  a valid snapshot is refused.
- [ ] T7. Handoff and consent replay: a second use of a handoff or consent token is
  refused (CAS); an expired token is refused; a CSRF POST without matching origin is
  refused.
- [ ] T8. Repeated connection: a reconnect after `expired` or `revoked` mints a new
  `gcn_`; the old one stays `revoked`; old consents do not apply.
- [ ] T9. Leak scan: the canary session strings never appear in Temporal histories,
  logs, tool replies or audit rows.
- [ ] T10. Egress: the provider adapter refuses a non-allowlisted or private address
  (`netsafe` semantics).
- [ ] T11. Injection: a menu item name containing instructions is returned as a bounded
  field and causes no write without human consent.
- [ ] T12. Fan-out: per-principal and per-tenant rate limits and the history
  `limit<=20` cap hold; the circuit breaker trips on repeated 429s from the fake.
- [ ] T13. Expiry: the fake reports an expired session, the connection moves to
  `expired`, and the tools report `connection_expired`, not success.
- [ ] T14. Ambiguous and personal scope: a principal with two tenants and no selection
  gets `ambiguous_tenant`; personal scope gets `scope_unsupported`; nothing falls back
  to `labs` or `mctl`.
- [ ] T15. No regression: root `go test ./...` passes and the `tg.mctl.ai` tool
  descriptors (`docs/tool-descriptors*.json`) are unchanged.
- [ ] T16. Duplicate actions: the same `idempotency_key` returns the original
  `order_id`, and a duplicate workflow start is rejected.

## Rollback

- Part A is documentation and one docs test. Revert the merge commit
  (`git revert -m 1 <sha>`). Nothing is deployed, nothing is migrated, and the runtime
  is unaffected.
- Part B lives in a separate module and adds unpublished images. Revert the merge
  commit; the root module, the server image and `tg.mctl.ai` are untouched. If a later
  deploy exists (M3, not here), the layered kill switches are: `GLOVO_MCP_ENABLED=false`,
  provider worker `replicaCount: 0`, `GLOVO_PROVIDER_REAL=false`, revoking the provider
  Temporal identity, and removing the mctl-api pilot allowlist. Revoked connections are
  crypto-shredded and are not restored by a rollback.
