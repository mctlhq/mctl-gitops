# Design: issue-570-feat-commerce-accept-only-kill-switch-th

## Current state

- `cmd/api/main.go` (around line 480): the commerce ledger is built only when
  `cfg.CommerceDisabled` is false and `COMMERCE_DB_URL` or `AUDIT_DB_URL` is
  set. Otherwise `commerceStore` stays nil, and a warning says every
  `/api/v1/commerce*` route will return 503. The store goes into
  `mctlapi.Options{Commerce: commerceStore}` (around line 924).
- `cmd/api/main.go` `config` struct (around line 1213): `CommerceDisabled bool`
  is read with `killSwitchOn(os.Getenv("COMMERCE_DISABLED"))` (line 1323).
  `killSwitchOn` (line 1890) treats `""`, `false`, `f`, `0`, `no` and `off` as
  off and anything else as on. `config.validate` (around line 1585) skips the
  dispatch-key check while `CommerceDisabled` is on.
- `internal/api/router.go` (around line 735): `/commerce` routes. Quotes are
  served by `h.MintCommerceQuote` and accepts by `h.AcceptCommerceInvocation`.
  The reconciler is `h.ReconcileCommerceExpired`, and the money edges are
  `…/reserve`, `…/dispatch`, `…/finalize` and `…/release`.
- `internal/api/router.go` `Options.Commerce *commerce.Store` (line 161): nil
  means 503 on every route.
- `internal/api/handlers_commerce.go`:
  - `requireCommerce` answers 503 "commerce ledger not configured" when the
    store is nil.
  - `requireCommerceTenant` adds tenant access (404 on no access),
    `requireTenantRole` (owner) and the `identity-unresolved` 403. The 403 is
    audited as `denied`.
  - `MintCommerceQuote` (line 385) and `AcceptCommerceInvocation` (line 445)
    call `requireCommerceTenant`, decode the body, then call
    `Store.MintQuote` / `Store.AcceptInvocation`.
  - `writeErrorCode` (`internal/api/handlers_read.go:874`) writes the
    `{"code": …}` envelope. `writeCommerceError` maps store errors to the
    ADR 020 sec. 13 codes, and `dispatch-unavailable` there is a 503.
- `internal/commerce/types.go:127`: `ReasonUnsupportedExecution =
  "unsupported-execution"` is already defined and not used anywhere yet.
- `internal/api/handlers_commerce_budget.go:279`: `ReconcileCommerceExpired`
  calls `Store.ExpireStale`. It refuses `accepted` rows whose quote has expired
  (`quote-expired`) and releases `reserved` rows past their deadline
  (`reservation-expired`).
- Tests: `internal/api/handlers_commerce_test.go` (`newCommerceFixture`, which
  needs `TEST_DATABASE_URL`, plus `TestCommerceHandlers_NilStoreIs503`),
  `internal/api/handlers_commerce_budget_test.go`, and
  `cmd/api/main_test.go:326`, which covers the `CommerceDisabled` validate
  skip. The budget test already forces expiry with
  `UPDATE commerce_invocations SET quote_expires_at = now() - interval '1 minute'`.
- Docs: `docs/commerce-ledger.md` "Configuration" table and README.md env
  table (lines 148-151).
- MCP: `internal/mcp` exposes no commerce tool, so the tool count in
  `server_test.go` does not change.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`:
  `replicaCount: 2`, and `AUDIT_DB_URL` is set. No `COMMERCE_*` variable is
  set, so in production the commerce ledger runs on the `AUDIT_DB_URL`
  fallback and `COMMERCE_DISABLED` is off. Because there are 2 replicas, a
  switch flip only takes full effect once both pods have rolled.
- `$MCTL_GITOPS_ROOT/services/`: mctl-api is not a tenant service. It is
  deployed from `bootstrap/templates/mctl-platform/`, not
  `services/<tenant>/mctl-api`.
- `helm/values.yaml` (in the clone): `env:` lists `MCTL_FEDERATION_DISABLED: ""`
  as the documented kill-switch pattern. No commerce variable appears there.
- I made no mctl MCP calls. I did not need to observe runtime logs or status
  to design an env-gated handler change, so the live pod env is unverified
  beyond the gitops template.

## Proposed solution

### 1. Configuration (`cmd/api/main.go`)

- Add `CommerceAcceptDisabled bool` to `config`, next to `CommerceDisabled`,
  loaded with `killSwitchOn(os.Getenv("COMMERCE_ACCEPT_DISABLED"))`.
- In the commerce switch block, when the store was built successfully and
  `cfg.CommerceAcceptDisabled` is on, log
  `slog.Warn("COMMERCE_ACCEPT_DISABLED is set; commerce quotes and invocation accepts are refused with unsupported-execution; reads, reconcile, release and finalize stay live")`.
  When `CommerceDisabled` is also on, the existing warning wins and the
  accept switch is moot, because the store is nil.
- Pass `CommerceAcceptDisabled: cfg.CommerceAcceptDisabled` into
  `mctlapi.Options`.
- `config.validate` stays unchanged. The dispatch key is still validated when
  only the accept switch is on, because dispatch stays live.

### 2. Options (`internal/api/router.go`)

- Add `CommerceAcceptDisabled bool` to `Options`. Its comment says it refuses
  only `MintCommerceQuote` and `AcceptCommerceInvocation`, and that
  `Commerce == nil` takes precedence.

### 3. Handler gate (`internal/api/handlers_commerce.go`)

Add one helper:

```go
// refuseIfAcceptDisabled implements COMMERCE_ACCEPT_DISABLED (mctl-api#570):
// it stops new paid acceptances only. Called after requireCommerceTenant, so
// a caller without access still gets 404 and an unresolved one still gets
// identity-unresolved, and before the body is decoded, so nothing is written.
func (h *Handlers) refuseIfAcceptDisabled(w http.ResponseWriter, r *http.Request, user *auth.User, tenant, operation string) bool {
	if !h.opts.CommerceAcceptDisabled {
		return false
	}
	h.logAudit(r, audit.Entry{UserID: user.ID, Operation: operation, Status: "denied",
		RiskLevel: string(operations.RiskMedium), Parameters: map[string]string{"tenant": tenant},
		Message: "COMMERCE_ACCEPT_DISABLED is on; new paid acceptances are refused"})
	// 422, not 503 (owner decision 2026-10-11): mctl-agents reads every 5xx
	// as "ledger unknown", and this is a final refusal with nothing held.
	writeErrorCode(w, http.StatusUnprocessableEntity, commerce.ReasonUnsupportedExecution,
		"commerce is not accepting new paid invocations", nil)
	return true
}
```

Call it in `MintCommerceQuote` and `AcceptCommerceInvocation` right after
`requireCommerceTenant` succeeds. No other handler changes. In particular,
`ReconcileCommerceExpired`, `Release…`, `Finalize…`, `Reserve…`, `Dispatch…`,
`Transition…`, the budget routes and all reads are untouched.

The gate sits in the HTTP layer, not in `commerce.Store`, because it is a
deployment policy for this API surface, not a ledger invariant. The store's
tests and its phase machine stay as they are.

Status code: **422** (owner decision 2026-10-11, replacing the 503 first
proposed). The mctl-agents client reads every 5xx as `UNKNOWN`, which would
report a paused acceptance as `outcome-unknown`; a 422 carrying the code is
a clean `unsupported-execution` refusal. The code is `unsupported-execution`.

### 4. Documentation

- `docs/commerce-ledger.md` "Configuration": add a row for
  `COMMERCE_ACCEPT_DISABLED`. Add a new section, "Pausing acceptance",
  covering:
  - What is refused (the two POSTs, 422 `unsupported-execution`, audited
    `denied`) and what stays live (every other route, listed).
  - Precedence: `COMMERCE_DISABLED` wins.
  - **Disable order:**
    1. Set `COMMERCE_ACCEPT_DISABLED=true` and roll out every replica (two in
       production).
    2. Drain: run `POST /reconcile/expired` until it reports nothing left. The
       gateway or an operator finalizes or releases `dispatching`,
       `dispatched` and `outcome_unknown` rows through
       `…/finalize` / `…/release`. Time never moves those rows.
    3. Confirm that `GET /invocations/overdue` is empty and that no
       non-terminal rows remain.
    4. Only then, if the ledger must go fully dark, set
       `COMMERCE_DISABLED=true`.
  - **Enable order:**
    1. Unset `COMMERCE_DISABLED` first, keeping `COMMERCE_ACCEPT_DISABLED` on.
    2. Verify that reads, `/dispatch-keys` and `/reconcile/expired` answer.
    3. Unset `COMMERCE_ACCEPT_DISABLED`.
  - Note that flipping `COMMERCE_DISABLED` on while liability is open freezes
    it: nothing can reconcile until the ledger is back.
- README.md env table: add a `COMMERCE_ACCEPT_DISABLED` row next to
  `COMMERCE_DISABLED`.
- `helm/values.yaml`: add `COMMERCE_ACCEPT_DISABLED: ""` under `env:` with a
  one-line comment, following the `MCTL_FEDERATION_DISABLED` precedent. It
  stays off.

## Alternatives

1. **Reuse `COMMERCE_DISABLED` with a mode value** (e.g.
   `COMMERCE_DISABLED=accept`). Dropped: `killSwitchOn` treats any
   non-false value as "fully on", so an existing `accept` value would silently
   mean "everything off". That conflates two procedures the runbook must keep
   separate, and the issue asks for a separate variable.
2. **Gate in `commerce.Store`** (a flag on the store, with
   `MintQuote`/`AcceptInvocation` returning a new sentinel error). Dropped:
   it adds a store-level error and mapping for what is a deployment policy,
   and the gate would sit after body decoding and validation. That changes
   which errors a caller sees first and spreads the change across two
   packages for no added safety.
3. **A router middleware on the two routes.** Dropped: it would run before
   `requireCommerceTenant`, so an unauthorized caller would get
   `unsupported-execution` instead of 401/404. That leaks that the tenant
   path is valid and that commerce is paused, against ADR 020 sec. 12's
   "same answer as missing".
4. **Also refusing `…/reserve` and `…/dispatch`.** Dropped for this issue:
   the issue says everything else is unchanged, and accepted rows must be able
   to proceed or be released. Recorded as an open question for C5.

## Platform impact

- **Migrations:** none. No schema change.
- **Backward compatibility:** the default (unset) behaves exactly as today.
  The response envelope is the existing `writeErrorCode` shape, and the code
  is already in the ADR 020 vocabulary. No MCP tool changes, so the
  `server_test.go` count is unchanged.
- **Resources:** none. One bool check per request on two routes.
- **Risks and mitigations:**
  - *An operator flips `COMMERCE_DISABLED` instead and freezes liability.*
    The documented disable order and the startup warnings mitigate this.
  - *Partial rollout (2 replicas):* one pod may still accept during the
    rollout. The docs say acceptance stops only once every replica has
    rolled.
  - *The gateway retries a 5xx as unknown:* avoided by answering 422, which
    the gateway treats as a final refusal (owner decision 2026-10-11).
  - *Dispatch-key validation still runs under the accept switch, so a bad key
    still refuses boot:* this is intended, because dispatch stays live. The
    escape hatch remains `COMMERCE_DISABLED`.
