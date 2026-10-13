# Tasks: issue-571 — DevLoop approvals through a bound `aar_`

mctl-api tasks 1-5 can be one or two PRs; task 6 is mctl-agents#636; 7-8 are
owner-gated rollout. Re-read line numbers on `main` before editing.

- [ ] 1. Legacy flag + `approver.legacy_relay` audit (§4). — DoD: flag on:
  relay works, exactly one audit entry per use; flag off: 400
  `legacy_approver_disabled`, audited; mutation: removing the refusal fails
  the flag-off test (R13).
- [ ] 2. `we_`-keyed DevLoop `aar_` (§1): create-time `we_` check,
  `ExecutionByEngineRef`, approve decides the pending `aar_` and signals
  `approval_ref`; legacy payload only with the flag on; `isHumanAdmin`.
  — DoD: tests for found/not-found `we_`, no pending `aar_` (flag on/off),
  service principal refused on approve, self-decision refused.
- [ ] 3. Grant-authorized `mctl-agents-approve` (§2) + allowlist route. —
  DoD: A1-A4 as handler tests through the router with a real run token:
  bound grant succeeds once; other `we_` → `grant_not_bound`; second use →
  consumed; wrong target, expired, denied, pending → refused, nothing
  submitted; body `approver` refused; agent without grant and non-admin
  human still refused. Mutations: dropping the target check, the CAS, or
  the kind check each fails a test.
- [ ] 4. Subject from `prn_` (§3). — DoD: ZITADEL-only subject delegates
  (A6); empty id refuses; disabled principal refuses; store error 503;
  mutation: reinstating the `github:` requirement fails A6.
- [ ] 5. Docs/OpenAPI/Helm/README: `docs/principals.md` (grant-authorized
  approval), env var, error codes. `go vet`, `gofmt`, `golangci-lint`,
  `go test ./...` green.
- [ ] 6. mctl-agents#636 (counterpart): attach `we_` at DevLoop start (per
  Q1), mint run token, create `aar_` with `we_`, read `approval_ref` from
  the signal, submit with `X-MCTL-On-Behalf-Of: aar_…` and no `approver`,
  typed refusals are hard failures; E2E test fails when the run-token or
  `approval_ref` path is removed.
- [ ] 7. Rollout: mctl-api release (flag on) → mctl-agents release →
  natural DevLoop E2E + audit evidence (A7).
- [ ] 8. Owner OK → mctl-gitops sets the flag `false`; live proof that the
  free-text path is refused; next release deletes the flag; close #571.
