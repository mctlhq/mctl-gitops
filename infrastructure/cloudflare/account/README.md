# Cloudflare — account-scoped root

Holds resources that are not attached to a single zone: R2 buckets, Access
applications/policies/IdPs and organization settings, Zero Trust gateway and
device settings, and eventually the MCP Portal and its servers.

**Currently empty on purpose.** This root exists so the backend, the state key
and the CI wiring are proven before anything is imported into it. A plan here
should report no changes.

Imports arrive with:

- `#1088` — Access applications, policies, organization settings, Email Routing
- `#1092` — MCP Portal and MCP servers (blocked on `.github#35` / `#44`)

Not to be added here: the tunnel and cache ruleset owned by `mac-mini-infra`
(see the boundary table one directory up) — those move under `#1090`, into
their own root.
