# Design: issue-569-feat-commerce-receipt-read-and-mcp-tools

## Current state

Ledger and types

- `internal/commerce/types.go` defines `SchemaVersion = 1`, the phase and fact vocabularies,
  `Money{Currency, AmountMinor int64}` (no floats in the package) and `Invocation`. An
  `Invocation` carries ids, `Identities` (tenant, principal, subject, delegation grant,
  payer account, execution id), `quote_digest`, `terms_id`/`terms_version`, `price`,
  `funds_mode`, `phase`, the five facts (`execution_outcome`, `usage_quantity`,
  `charge_status`, `payment_status`, `settlement_status`), `reason_code`, `approval_id`,
  and timestamps. It also carries `idempotency_key`, `args_digest` and
  `provider_operation_key`, which are inputs and correlation keys, not receipt facts.
- `internal/commerce/store.go` `Store.GetInvocation(ctx, tenantID, invocationID)` selects
  `WHERE invocation_id = $1 AND tenant_id = $2` and returns `ErrInvocationNotFound` for both
  a missing and a foreign-tenant row. `ListInvocations` filters by tenant, capability, phase,
  period, idempotency key and principal.
- `internal/commerce/budget.go` `Balance` carries `schema_version`, `tenant_id`,
  `payer_account_id`, `currency`, `funds_mode`, `period`, `monthly_limit_minor`,
  `per_request_max_minor`, `committed_minor`, `reserved_minor`, `pending_liability_minor`,
  `available_minor`, `as_of`. `GetBalance` computes it in one read-only repeatable-read
  transaction. `Reservation` carries `authorization_id` and `capture_id` (payment adapter
  references), which this proposal treats as payment proofs and keeps out of the receipt.
- No commerce table stores a policy decision. `approval_id` points at an action approval in
  `internal/workitems/action_approvals.go`; `ActionApprovalRequest` carries
  `policy_rule_id`, `policy_version`, `state`, `decided_at`. `Store.ActionApproval(ctx, id)`
  returns `workitems.ErrApprovalNotFound` for a missing id. `checkApprovalOwner` in
  `internal/api/handlers_commerce.go` already reads it through `h.opts.WorkItems` at accept
  time.
- `external_ref` appears nowhere in `internal/commerce`; no commerce read can return it today.

HTTP layer

- `internal/api/router.go` lines ~735-764 mount `/commerce` routes; the tenant subtree has
  `GET /budget`, `GET /invocations`, `GET /invocations/{invocation_id}`,
  `GET /invocations/{invocation_id}/transitions`.
- `internal/api/handlers_commerce.go`: `requireCommerce` answers 503 when
  `h.opts.Commerce == nil`; `requireCommerceTenant` normalizes the tenant, answers 404
  `not found` when `!user.HasTenantAccess(tenant)` (same as a missing tenant), checks
  `commerceTenantRole` (`operations.RoleOwner`, documented as the ADR 020 sec. 12 milestone
  rule) through `requireTenantRole`, and refuses an unresolved principal with 403
  `identity-unresolved`. `writeCommerceError` maps `ErrInvocationNotFound` to 404
  `not found`. `GetCommerceInvocation` writes the raw `Invocation`.
- `internal/api/handlers_commerce_budget.go` `GetCommerceBudget` writes the `Balance`.
- `internal/openapi/openapi.yaml` documents the commerce routes and
  `internal/openapi/embed_test.go` pins the documented path/method set (lines 40-48).
- `docs/commerce-ledger.md` "Routes" table lists who may call each route.

MCP layer

- `internal/mcp/server.go` registers every tool via `srv.AddTool(s.toolX())` (around line
  196 onward). `apiGet`/`apiGetStatus`/`doRequest` (~line 2275) call the REST API with
  `s.effectiveToken(ctx)`, i.e. the caller's own token, so tenant checks are the API's.
- `internal/mcp/workitems.go` is the closest pattern: read-only tools with
  `WithReadOnlyHintAnnotation(true)`, `WithDestructiveHintAnnotation(false)`, id validation
  in `idArg`/`requiredIDArg` (`workItemIDPattern`), and `workItemCall`, which preserves the
  API's status and body in the tool error (`Failed to <what> (HTTP 404): ...`).
- `internal/mcp/annotations_test.go` `recordedHints` must list every tool with its hints
  (`TestNewMCPServer_ToolCount` in `server_test.go` compares counts), and
  `TestReadOnlyToolsAreTheRecordedSet` spells out the read-only set.
- `internal/mcp/portal_allowlist_test.go` `TestPortalAllowlist_CoversEveryRegisteredTool`
  requires every registered tool to appear in `docs/portal-allowlist.json` with an explicit
  `enabled` and a tool-specific reason of at least 40 characters. Disabled entries are
  allowed (16 exist today).

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/` lists tenants `admins`, `karabu`, `labs`, `ovk`; there is no
  `services/*/mctl-api/values.yaml`, and `grep -i commerce` over `services/` and `tenants/`
  found nothing. mctl-api's own deployment config is not in this checkout.
- `mctl_get_service_config(admins, mctl-api)` returned `service not found: admins/mctl-api`.
- `mctl_list_services(admins)` (complete=true) lists mctl-agents-worker*, mctl-design,
  mctl-docs, mctl-web; mctl-api is not a catalogue service.
- Therefore whether `COMMERCE_DB_URL` / `COMMERCE_DISABLED` are set in production, and
  whether `WorkItems` is configured beside commerce, could not be observed. The design does
  not depend on either: an unconfigured ledger already answers 503, and an unconfigured
  approval store is reported as `policy_decision.status = "unavailable"`.

## Proposed solution

1. Receipt type (`internal/commerce/receipt.go`, new)

   ```go
   type PolicyDecisionRef struct {
       Status        string `json:"status"` // none | recorded | missing | unavailable
       ApprovalID    string `json:"approval_id,omitempty"`
       PolicyRuleID  string `json:"policy_rule_id,omitempty"`
       PolicyVersion string `json:"policy_version,omitempty"`
   }

   type Receipt struct {
       SchemaVersion int    `json:"schema_version"`
       InvocationID  string `json:"invocation_id"`
       QuoteID       string `json:"quote_id"`
       QuoteDigest   string `json:"quote_digest"`
       TermsID       string `json:"terms_id"`
       TermsVersion  int64  `json:"terms_version"`
       CapabilityID  string `json:"capability_id"`
       ProviderID    string `json:"provider_id"`
       TenantID, PayerAccountID, PrincipalID, SubjectPrincipalID string
       DelegationGrantID string `json:"delegation_grant_id,omitempty"`
       ExecutionID   string `json:"execution_id"`
       ApprovalID    string `json:"approval_id,omitempty"`
       PriceMode     string `json:"price_mode"`
       Price         Money  `json:"price"`
       FundsMode     string `json:"funds_mode"`
       Phase         string `json:"phase"`
       ReasonCode    string `json:"reason_code,omitempty"`
       ExecutionOutcome string `json:"execution_outcome"`
       UsageQuantity *int64 `json:"usage_quantity,omitempty"`
       ChargeStatus, PaymentStatus, SettlementStatus string
       QuoteExpiresAt, CreatedAt, UpdatedAt, ReconciliationDeadline time.Time
       ReservationDeadline, DispatchDeadline, FinalizedAt *time.Time // omitempty
       PolicyDecision PolicyDecisionRef `json:"policy_decision"`
   }

   func ReceiptOf(inv Invocation, policy PolicyDecisionRef) Receipt
   ```

   `Receipt` is an explicit allowlist, not an embedding of `Invocation`: a field added to
   `Invocation` later cannot leak into the receipt by accident. It deliberately omits
   `idempotency_key`, `args_digest`, `provider_operation_key`, `version` and every
   reservation field. `ReceiptOf` is pure, so it is unit-testable without a database. Same
   `SchemaVersion` constant as every other commerce record.

2. Handler (`internal/api/handlers_commerce.go`)

   `GetCommerceReceipt`:
   - `requireCommerceTenant(w, r, "commerce-invocation-read")` - same authority, same 404
     for a foreign tenant, same 503 and `identity-unresolved` behaviour as the other reads.
   - `h.opts.Commerce.GetInvocation(ctx, tenant, invocation_id)`; errors through
     `writeCommerceError` (404 `not found` for missing and foreign-tenant rows alike).
   - `h.policyDecisionOf(ctx, inv.ApprovalID)`:
     empty id -> `{status:"none"}`; `h.opts.WorkItems == nil` -> `unavailable`;
     `ErrApprovalNotFound` -> `missing`; other error -> `unavailable` (logged with slog,
     approval id only); success -> `recorded` with `policy_rule_id`, `policy_version`.
     The receipt is never failed because the approval store is down: the money facts are
     the ledger's and are available; the reference is reported as unknown, never as absent.
   - `writeJSON(w, 200, commerce.ReceiptOf(*inv, ref))`.

   Route: `r.Get("/invocations/{invocation_id}/receipt", h.GetCommerceReceipt)` beside the
   existing invocation reads in `internal/api/router.go`.

3. OpenAPI and docs

   - `internal/openapi/openapi.yaml`: add the path with a `CommerceReceipt` schema
     (integers for `amount_minor`, `terms_version`, `usage_quantity`, `schema_version`), 404,
     403, 503 responses; add the path to `embed_test.go`'s pinned set.
   - `docs/commerce-ledger.md`: add the route to the "Routes" table (tenant owner or admin,
     resolved principal) and a short "Receipts" section listing what is excluded.

4. MCP tools (`internal/mcp/commerce.go`, new)

   - `mctl_get_commerce_budget(tenant)` -> `GET /api/v1/commerce/tenants/{tenant}/budget`.
   - `mctl_list_commerce_invocations(tenant, capability_id?, phase?, since?, until?, limit?)`
     -> `GET .../invocations?...`, query built with `url.Values` so a capability URI is
     encoded. `phase` is passed through; the API refuses an unknown phase with
     `invalid-request` rather than returning an empty list. The `idempotency_key` filter is
     not exposed: it is a gateway-resume tool, not a tenant question.
   - `mctl_get_commerce_receipt(tenant, invocation_id)` -> `GET .../invocations/{id}/receipt`.
   - `tenant` is validated with a lowercase DNS-label pattern and `invocation_id` with the
     existing `idArg` pattern (`inv_` ids satisfy it) before any request, so no path
     injection reaches the API. `tenant` is path-escaped anyway.
   - All three: `WithReadOnlyHintAnnotation(true)`, `WithDestructiveHintAnnotation(false)`,
     a title annotation, and a description stating that a foreign tenant and a missing id
     give the same not-found answer and that amounts are integer minor units.
   - Calls go through the existing `workItemCall` helper (renamed or wrapped as `apiCall` if
     the reviewer prefers; behaviour identical): caller's own token, API status and body
     preserved in the tool error, so a 404 for a foreign tenant and for a missing id yield
     byte-identical tool errors because the API bodies are identical.
   - Registered in `NewMCPServer` next to the work-item tools.
   - `internal/mcp/annotations_test.go`: three `recordedHints` entries
     (`readOnly: true, destructive: false, idempotent: false`, matching existing read
     tools) and the three names added to `TestReadOnlyToolsAreTheRecordedSet`.
   - `docs/portal-allowlist.json`: three entries with `"enabled": false` and a specific
     reason (for example "Reads one tenant's commerce receipt: ids, digests, the five facts
     and the approval/policy reference; no arguments, results or payment proofs"). Enabling
     them on the shared portal is a separate owner decision.

## Alternatives

- Return the raw `Invocation` from `/receipt`, or add a `?view=receipt` flag on the existing
  read. Dropped: the existing shape includes `idempotency_key`, `args_digest` and
  `provider_operation_key`, and any future column would flow straight into the "receipt".
  An explicit struct is the only way to make "no read returns ..." a property of the type.
- Persist `policy_rule_id`/`policy_version` on `commerce_invocations` at accept time.
  More durable, but it needs a schema change, rows accepted before it would still need a
  read-time fallback, and the approval's policy fields do not change after creation. Kept
  as a follow-up if ADR 020 wants the reference frozen in the ledger.
- Fail the receipt with 503 `approval-unavailable` when the approval cannot be read (the
  accept path does this). Dropped for reads: the ledger facts are authoritative and present;
  hiding them behind another store's outage helps nobody, while an explicit
  `status: "unavailable"` keeps "could not read" distinct from "none".
- MCP tools that query the commerce store in-process. Dropped: every other MCP tool goes
  through the REST API with the caller's token, which keeps authorization in one place
  (`requireCommerceTenant`).

## Platform impact

- Migrations: none. No table or column changes.
- Backward compatibility: additive only - one new GET route, three new MCP tools. Existing
  responses are unchanged. The MCP tool count rises by three; the count, annotation and
  allowlist tests are updated in the same change.
- Resources: the receipt read is one indexed primary-key select plus at most one approval
  lookup by id; negligible.
- Security and privacy risks:
  - Cross-tenant probing: mitigated by reusing `requireCommerceTenant` and the
    tenant-scoped `GetInvocation`; a handler test asserts byte-identical 404 bodies for a
    foreign tenant, a foreign tenant's real invocation id, and a nonexistent id.
  - Field leakage: mitigated by the explicit `Receipt` struct and a test that marshals a
    fully populated receipt and compares the JSON key set to a fixed allowlist.
  - The approval lookup has no tenant on the approval (`checkApprovalOwner` notes approvals
    carry no tenant yet); it is reached only through an invocation already scoped to the
    caller's tenant, and only the policy rule id and version are returned.
  - Shared portal exposure: tools ship disabled in `docs/portal-allowlist.json`.
- Operational: with `COMMERCE_DISABLED` or no database the new route answers 503 like its
  siblings; the MCP tool surfaces that as a tool error.
