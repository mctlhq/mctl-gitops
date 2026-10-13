# Tasks: issue-571 — DevLoop approvals through a bound `aar_`

mctl-api tasks 1-5 can be one or two PRs; task 6 is mctl-agents#636; 7-8 are
owner-gated rollout. Re-read line numbers on `main` before editing.

- [x] 0. ~~Work-item lookup by surface ref~~ — dropped 2026-10-13 before
  implementation: the create route already dedupes open work on
  `external_key` = the issue URL (§0, R0a-R0c); no mctl-api change.
- [ ] 1. Legacy flag + `approver.legacy_relay` audit (§4). — DoD: flag on:
  relay works, exactly one audit entry per use; flag off: 400
  `legacy_approver_disabled`, audited; mutation: removing the refusal fails
  the flag-off test (R13).
- [ ] 2. `we_`-keyed DevLoop `aar_` (§1): create-time `we_` check; the
  approve route resolves `workflow_id` to its one open `we_` (non-terminal,
  `engine_ref` equal to `workflow_id` or starting with `<workflow_id>#`),
  decides the pending `aar_` and signals `approval_ref`; legacy payload only
  with the flag on; `isHumanAdmin`. — DoD: tests for found/not-found `we_`,
  the dispatched `<workflow_id>#<request_id>` form, two open executions →
  409 `execution_ambiguous`, a store read error → 503 (never the legacy
  payload), no pending `aar_` (flag on/off), service principal refused on
  approve, self-decision refused.
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
- [ ] 6. mctl-agents#636 (counterpart): issue → work item → `we_` at DevLoop
  start (§0, D6: a dispatched run uses its fulfilled `we_`; any
  other start creates with `external_key` = the canonical issue URL and
  attaches `temporal`/`workflow_id`; restart yields the same `we_`; a create
  error, `external_key_in_use` included, stops the run), mint run token, create `aar_` with `we_`, read `approval_ref` from
  the signal, submit with `X-MCTL-On-Behalf-Of: aar_…` and no `approver`,
  typed refusals are hard failures; E2E test fails when the run-token or
  `approval_ref` path is removed.
- [ ] 7. Rollout: mctl-api release (flag on) → mctl-agents release →
  natural DevLoop E2E + audit evidence (A7).
- [ ] 8. Owner OK → mctl-gitops sets the flag `false`; live proof that the
  free-text path is refused; next release deletes the flag; close #571.
