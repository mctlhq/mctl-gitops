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
reach it is `projects-mcp-grants.yaml`, read by Terraform to build the policy
and by the server to decide what each caller sees — one list, not two. The file
moves next to the service when it is deployed, and the `projects_mcp_grants_file`
variable moves with it.

Sign-in is Google or a one-time PIN mailed to the address. The PIN is there
because a customer's work address is not necessarily a Google account. Both
providers are named by UUID: a data source was tried and removed, because the
read-only plan identity cannot see the account's identity configuration and
returned an empty list instead of an error — a plan that proposed an application
with no providers at all.

The apply identity for this root needs `Access: Apps and Policies Write`.

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
