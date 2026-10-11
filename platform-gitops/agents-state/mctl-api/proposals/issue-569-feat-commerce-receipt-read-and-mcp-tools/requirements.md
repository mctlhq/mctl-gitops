# Commerce receipt read and MCP tools for tenant-scoped commerce reads

## Context

mctl-api already runs the ADR 020 commerce ledger (`internal/commerce`, routes under
`/api/v1/commerce/tenants/{tenant}` in `internal/api/router.go`). Tenants can read their
budget balance (`GET .../budget`), list invocations (`GET .../invocations`) and read one
invocation row (`GET .../invocations/{invocation_id}`). There is no receipt read, the
ADR 020 sec. 12 projection of an invocation that names what was agreed, what happened and
which approval and policy decision covered it. None of the commerce reads is reachable from
the MCP server (`internal/mcp`).

mctl-agents C5 (mctlhq/mctl-agents#620) depends on these reads to show tenants what they
spent and to prove a paid call end to end. This proposal adds the receipt route and three
read-only MCP tools over the tenant-scoped reads. It keeps the ledger's existing rules: a
foreign tenant answers the same as a missing id, amounts are integer minor units, and no
read returns arguments, results, payment proofs or `external_ref` contents.

## User stories

- AS a tenant admin I WANT to read the receipt of one of my invocations SO THAT I can see the
  terms, quote, outcome and charge it was settled under, and which approval covered it.
- AS a tenant admin using an MCP client I WANT `mctl_get_commerce_budget`,
  `mctl_list_commerce_invocations` and `mctl_get_commerce_receipt` SO THAT an agent can
  answer "what did I spend and why" without calling REST by hand.
- AS mctl-agents C5 I WANT a stable, versioned receipt shape SO THAT I can verify a paid
  invocation without seeing its arguments or results.
- AS a platform operator I WANT these reads to leak nothing across tenants SO THAT one
  tenant cannot learn whether another tenant's invocation id exists.

## Acceptance criteria (EARS)

Receipt route

- WHEN a caller with commerce tenant authority on `{tenant}` and a resolved principal sends
  `GET /api/v1/commerce/tenants/{tenant}/invocations/{invocation_id}/receipt` for an
  invocation of that tenant THE SYSTEM SHALL answer 200 with a receipt carrying
  `schema_version`, `invocation_id`, `quote_id`, `terms_id`, `terms_version`,
  `capability_id`, `provider_id`, `tenant_id`, `payer_account_id`, `principal_id`,
  `subject_principal_id`, `delegation_grant_id` (when set), `quote_digest`, `price_mode`,
  `price` (`currency`, `amount_minor`), `funds_mode`, `phase`, `reason_code` (when set),
  the five facts (`execution_outcome`, `usage_quantity`, `charge_status`,
  `payment_status`, `settlement_status`), the timestamps (`created_at`, `updated_at`,
  `quote_expires_at`, and when set `reservation_deadline`, `dispatch_deadline`,
  `finalized_at`, plus `reconciliation_deadline`), `approval_id` (when set),
  `execution_id` and a `policy_decision` reference.
- WHEN the invocation carries an `approval_id` and the action approval is readable THE
  SYSTEM SHALL set `policy_decision` to `{"status":"recorded","approval_id",
  "policy_rule_id","policy_version"}` taken from that approval.
- WHEN the invocation carries no `approval_id` THE SYSTEM SHALL set `policy_decision` to
  `{"status":"none"}`.
- IF the invocation carries an `approval_id` but the approval store is not configured or the
  read fails THEN THE SYSTEM SHALL still answer 200 with `policy_decision`
  `{"status":"unavailable","approval_id":...}` and never omit or blank the reference.
- IF the approval named by the invocation no longer exists THEN THE SYSTEM SHALL set
  `policy_decision.status` to `"missing"` with the `approval_id`.
- IF `{tenant}` is outside the caller's tenants, or the invocation id does not exist, or the
  invocation belongs to another tenant THEN THE SYSTEM SHALL answer 404 with the identical
  body `not found`.
- IF the commerce ledger is not configured THEN THE SYSTEM SHALL answer 503, never 404.
- IF the caller has no resolved canonical principal THEN THE SYSTEM SHALL answer 403
  `identity-unresolved`, as every other tenant-scoped commerce route does.
- WHILE serving any receipt THE SYSTEM SHALL express every amount as an integer number of
  minor units and SHALL use no floating-point field.
- WHILE serving any receipt THE SYSTEM SHALL NOT include `idempotency_key`, `args_digest`,
  `provider_operation_key`, a reservation's `authorization_id` or `capture_id`, any argument
  or result payload, any payment proof, or any `external_ref` content.

MCP tools

- WHEN `mctl_get_commerce_budget` is called with `tenant` THE SYSTEM SHALL call
  `GET /api/v1/commerce/tenants/{tenant}/budget` with the caller's own token and return the
  balance, which carries `available_minor`, `reserved_minor`, `committed_minor`,
  `pending_liability_minor`, `currency` and `funds_mode`.
- WHEN `mctl_list_commerce_invocations` is called with `tenant` and optional
  `capability_id`, `phase`, `since`, `until`, `limit` THE SYSTEM SHALL call
  `GET /api/v1/commerce/tenants/{tenant}/invocations` with those query parameters
  (URL-encoded) and return the listing.
- WHEN `mctl_get_commerce_receipt` is called with `tenant` and `invocation_id` THE SYSTEM
  SHALL call the receipt route and return the receipt.
- IF the API answers 404 for a foreign tenant or a missing id THEN THE SYSTEM SHALL return
  the same tool error text for both.
- IF a required argument is missing or `tenant` / `invocation_id` is not a plain identifier
  THEN THE SYSTEM SHALL return a tool error without calling the API.
- WHILE registered THE SYSTEM SHALL annotate the three tools read-only and non-destructive,
  record them in `internal/mcp/annotations_test.go`, and list each in
  `docs/portal-allowlist.json` with an explicit decision.

Invocation list hygiene

- WHILE serving `GET .../invocations` or `GET .../invocations/{invocation_id}` THE SYSTEM
  SHALL keep returning no arguments, results, payment proofs or `external_ref` contents
  (existing behaviour, pinned by a test in this change).

## Out of scope

- Real money, payment rails, a marketplace, shared-tenant enablement.
- Any change to the tenant role model; the final model belongs to mctl-api#377 / #489 and
  mctl-agents#631. The existing milestone rule (`commerceTenantRole`) is reused unchanged.
- New write routes, new MCP write tools, or MCP tools for budget changes, transitions, quotes
  or the admin-only overdue listing.
- Storing a policy decision on the invocation row (a schema migration).
- Enabling the new tools on the shared portal; the allowlist entries ship `enabled: false`
  until an owner decision.

## Open questions

- The issue lists budget fields as `available`, `reserved`, `committed`,
  `pending_liability`. The existing `commerce.Balance` names them with a `_minor` suffix.
  This proposal keeps the `_minor` names (they state the unit and are already published in
  `internal/openapi/openapi.yaml`); C5 should consume the suffixed names.
- The issue says "tenant admin". The code's milestone constant is
  `commerceTenantRole = operations.RoleOwner` (its comment calls it tenant admin, and
  `docs/commerce-ledger.md` calls it tenant owner). This proposal reuses the constant
  unchanged; the reviewer should confirm that is the intended rule.
- ADR 020 sec. 12 lives in mctl-agents and was not readable from this clone. The receipt
  field list is derived from the issue text and `commerce.Invocation`; whether the receipt
  must also carry a captured amount separate from `price` is unconfirmed. This proposal
  carries `price` and the `charge_status` fact, not a separate charged amount.
- "Policy decision references" are interpreted as the action approval's `policy_rule_id`
  and `policy_version`, read at receipt time. Whether ADR 020 wants a decision id from
  another system is unconfirmed.
- Whether the three MCP tools should be enabled on the shared portal is an owner decision;
  they ship disabled.
