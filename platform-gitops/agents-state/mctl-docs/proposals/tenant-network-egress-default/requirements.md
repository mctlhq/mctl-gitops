# Document the tenant network-egress default (now closed) and the `allow_internet_egress` override

## Context
`mctl-api@6cc17bb` ("fix(tenant): default internet egress to closed, and let
MCP set it", shipped in release 4.32.5, confirmed live in production via
`mctl-gitops` commit `73629ed`/`063fca6`) flipped the default of the
`allow_internet_egress` parameter on the `create-tenant` operation from
`"true"` to `"false"`. The old default was a bug: it did not match the
tenant Helm chart's own default (`false`), so every tenant created through
`mctl_create_tenant` silently got open outbound internet egress regardless
of intent. Argo Workflow pods are unaffected either way — they keep
internet access through a separate, unconditional policy so builds and
deploys keep working.

`docs/guides/tenants.md` is the canonical "how to create a tenant" page and
currently makes zero mention of network policy, egress, or the
`allow_internet_egress` parameter. This is a full gap, not a stale claim —
but a high-impact one, since the new default silently blocks any workload
that needs to call an external API unless the tenant owner knows to
override it.

## User stories
- AS a tenant owner I WANT to know that internet egress is denied by
  default when I create a tenant SO THAT I don't get blocked by an
  unexpected NetworkPolicy when my service needs to call an external API.
- AS a tenant owner I WANT to know how to allow outbound internet access
  SO THAT I can set `allow_internet_egress` correctly at creation time
  (or ask the platform team to update it) instead of debugging a silent
  network timeout.
- AS a platform admin I WANT the exception for Argo Workflow pods
  documented SO THAT users don't mistakenly believe builds/deploys are
  also blocked.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/guides/tenants.md` THE SYSTEM SHALL state that
  new tenants default to denying outbound internet egress.
- IF a reader wants their tenant's pods to reach external APIs THEN THE
  SYSTEM SHALL show how to set `allow_internet_egress` (natural-language
  MCP example and the underlying parameter name/values).
- WHILE describing tenant network policy THE SYSTEM SHALL clarify that
  Argo Workflow pods (builds, deploys) keep internet access regardless of
  this setting.

## Out of scope
- A migration note for tenants created before this change — their
  behavior is unchanged (existing tenants that already set the flag
  explicitly are unaffected; only the *default* for new tenants changed).
- Low-level Kubernetes `NetworkPolicy` manifest detail — this proposal
  documents the user-facing default and override, not the chart internals.
