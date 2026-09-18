# Cloudflare — account-scoped root

Holds resources that are not attached to a single zone: R2 buckets, Access
applications/policies/IdPs and organization settings, Zero Trust gateway and
device settings, and eventually the MCP Portal and its servers.

**Holds one application.** The root was empty until `projects.mctl.ai` landed
in `projects-mcp.tf`: an Access application created here rather than imported,
which is the one thing this root could take before `#1088` without colliding
with it. Everything else is still to be imported.

`projects-mcp.tf` is the Cloudflare half of the connector customers use to ask
about their own product. Access is the OAuth authorization server for that
application; the origin only verifies the assertion Access forwards. Who may
reach it is the grants list inside
`platform-gitops/services/labs/projects-mcp/values.yaml`, read here to build the
policy and mounted into the pod so the server decides what each caller sees from
the same lines — one list, not two. The chart renders ConfigMap content inline
from values, which is why the list lives in a values file and is decoded twice.

Sign-in is Google, and only Google since 2026-09-18. A one-time PIN mailed to
the address was allowed at first, on the argument that a customer's work address
is not necessarily a Google account; it was dropped because a code sent to
whoever controls an inbox is a weaker thing to hold this behind than an account.
The consequence is worth knowing before adding an address: a person in the
grants list without a Google account is admitted by the policy and still cannot
log in, and what they see is a product that does not work rather than a provider
that is missing.

The provider is named by UUID: a data source was tried and removed, because the
read-only plan identity cannot see the account's identity configuration and
returned an empty list instead of an error — a plan that proposed an application
with no providers at all.

The apply identity for this root needs `Access: Apps and Policies Write`; the
plan identity is `CF_ACCOUNT_READ_TOKEN`, because the repository-wide read token
is zone-scoped and answers 1010 on an account-level application.

That values file is the one input to this root that lives outside
`infrastructure/cloudflare/`, so `cloudflare-plan.yml` names it explicitly in
its change filter. Without that a pull request could admit an address to the
Access policy and never plan it.

Imports arrive with:

- `#1088` — Access applications, policies, organization settings, Email Routing
- ~~`#1092` — MCP Portal and MCP servers~~ — the MCP servers landed in
  `../portal/` instead, which is its own root with its own write token: the
  one-token-per-root rule means putting them here would have widened this
  root's credential to `MCP Portals`. The portal object itself is still
  unimported; it carries the tool allowlists owned by three other
  repositories, so adopting it is a separate decision.

Not to be added here: the tunnel and cache ruleset owned by `mac-mini-infra`
(see the boundary table one directory up) — those move under `#1090`, into
their own root.
