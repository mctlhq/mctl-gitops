# Cloudflare — account-scoped root

Holds resources that are not attached to a single zone: R2 buckets, Access
applications/policies/IdPs and organization settings, Zero Trust gateway and
device settings, and eventually the MCP Portal and its servers.

**Holds one application.** The root was empty until `projects.mctl.ai` landed
in `projects-mcp.tf`: an Access application created here rather than
imported, which is the one thing this root could take before `#1088` without
colliding with it. Everything else is still to be imported.

A second application bypassing Access for the bare `/` path existed
2026-09-19 – 2026-09-20, so a public HTML landing page there (explaining how
to connect) was readable with no identity at all. Removed: unnecessary — a
browser hitting the domain already gets Access's own interactive login page,
not a bare 401 — and wrong, since the actual goal was "no project grant
required", not "no identity required". `/` is back under the one application
below, same as `/mcp` and `/whoami`.

`projects-mcp.tf` is the Cloudflare half of the connector customers use to ask
about their own product. Access is the OAuth authorization server for that
application; the origin only verifies the assertion Access forwards.

**Access authenticates here; it does not authorize.** The policy admits any
account from either provider below, and what each of those people may see
is decided by the server alone, from a grants list in Vault
(`secret/teams/labs/projects-mcp`, field `grants_yaml`) that this root does not
read. A caller with no grant reaches the server and is told nothing: an empty
project list, and every slug answering exactly as a slug that does not exist.

Until 2026-09-19 the policy named one address per person, built from that list
where it then lived — in `platform-gitops/services/labs/projects-mcp/values.yaml`,
committed in this PUBLIC repository. Moving the list to Vault is what ended
that, and it could not stay an input to this root afterwards: `plan` runs on
every pull request, a pull request that adds a root is code this repository
runs with that job's credentials, so a Vault token here is a Vault token any
branch can take — and the one thing it reads is the list being protected. The
policy gave up naming people rather than hand that out.

What that costs is worth stating: the origin is now reachable by anyone who can
sign in with Google or receive a one-time PIN, not by a named few. The server
holds no credential for anybody's documentation and serves it from a copy baked
into its image, and `tests/leak.test.ts` in `mctlhq/projects-mcp` sweeps every
tool for a caller with no grant at all.

Sign-in is Google, and only Google between 2026-09-18 and 2026-09-19. A
one-time PIN mailed to the address was allowed at first, on the argument that a
customer's work address is not necessarily a Google account; it was dropped
because a code sent to whoever controls an inbox is a weaker thing to hold this
behind than an account — then restored the next day, once grants (in Vault,
never in this repo) actually existed for non-Google customer domains this org
cannot confirm are Google-backed, and the alternative was a grant that is
admitted by the policy and still cannot log in. The trade is accepted
knowingly, address by address: whoever holds a granted inbox authenticates as
it.

The provider is named by UUID: a data source was tried and removed, because the
read-only plan identity cannot see the account's identity configuration and
returned an empty list instead of an error — a plan that proposed an application
with no providers at all.

The apply identity for this root needs `Access: Apps and Policies Write`; the
plan identity is `CF_ACCOUNT_READ_TOKEN`, because the repository-wide read token
is zone-scoped and answers 1010 on an account-level application.

Every input to this root is now inside `infrastructure/cloudflare/`, so
`cloudflare-plan.yml`'s change filter no longer needs to name anything else.
It named that values file while the grants list was an input, because a pull
request could otherwise admit an address to the Access policy and never plan
it; with the policy naming nobody, there is no such pull request to catch.

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
