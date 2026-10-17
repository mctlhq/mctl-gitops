# Proposed content: commerce-entitlements-and-tools

> **Apply to:** `mctl-docs/docs/guides/commerce.md` (CREATE); add sidebar entry; add link block in `docs/mcp/tools-reference.md`
> **Source:** mctl-api@4fbee56, 44a1961, 197575d

---

```md
---
title: Commerce, budgets and entitlements
---

# Commerce, budgets and entitlements

Paid capabilities are metered per workspace (tenant). You can inspect balances and
invocations through MCP; admins grant finite service packages.

## Reading your balance

| Tool | Parameters | Returns |
|---|---|---|
| `mctl_get_commerce_budget` | `tenant` | `available_minor`, `reserved_minor`, `committed_minor`, `pending_liability_minor`, `currency`, `funds_mode` |
| `mctl_get_commerce_receipt` | `tenant`, `invocation_id` (`inv_…`) | terms, quote digest, price, outcome/usage/charge/payment/settlement facts, phase, timestamps |
| `mctl_list_commerce_invocations` | `tenant`; optional `capability_id`, `phase`, `since`, `until`, `limit` (1-500) | invocation rows |

Amounts are integer minor units of the stated currency. A tenant you cannot access
answers "not found", the same as a missing id. All three tools are read-only.

## Entitlements

An entitlement is a finite package of units for one capability, with an invoice
reference and an expiry time. Entitlement checks run **before** budget is reserved,
and holds are released if authorization is denied.

Admin grant request body:

\`\`\`json
{
  "capability_id": "mctl://projects/projects_search",
  "units": 100,
  "invoice_ref": "INV-0001",
  "expires_at": "2026-12-31T00:00:00Z",
  "reason": "Prepaid package"
}
\`\`\`

`expires_at` must be RFC 3339. Tenant members can list and read their entitlements.
<TODO: confirm with author of 4fbee56 the REST routes and response fields>
```

---
