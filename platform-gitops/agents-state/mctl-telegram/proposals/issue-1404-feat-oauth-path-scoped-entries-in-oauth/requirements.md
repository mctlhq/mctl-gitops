# Path-scoped entries in OAUTH_CIMD_ALLOWED_HOSTS for multi-tenant CIMD hosts

## Context

`OAUTH_CIMD_ALLOWED_HOSTS` admits a Client ID Metadata Document (CIMD)
`client_id` only by host: an exact host name or a `.suffix` entry.
`cimd.ParseAllowedHosts` (`internal/oauth/cimd/cimd.go`) refuses any entry that
contains `/`. `Resolver.hostAllowed` receives only `u.Hostname()`, both in
`Resolve` and in `fetchKeys` (`internal/oauth/cimd/assertion.go`). A
multi-tenant platform such as Hermes Agent on `agentspodium.com` publishes one
client document per tenant pod on a shared host, for example
`https://agentspodium.com/oauth/mcp/clients/<pod>/<server>.json`. Admitting
that host admits every pod's `client_id`. A pod with no `MCP_CLIENT_PROFILES`
record then gets the default scope surface and the same display name on the
consent page, so an attacker-controlled pod could send a victim an authorize
link and receive the code at its own callback. Two reviews on
mctlhq/mctl-gitops#2928 block the host-wide change for this reason.
`OAUTH_PREREGISTERED_CLIENTS` is not an alternative, because
`internal/config/config.go` refuses URL-shaped pre-registered client IDs while
CIMD is on.

This proposal implements part A of the issue: an allowlist entry may be
`host/path-prefix/`, and it admits only `client_id`s whose normalized path
starts with that prefix on whole segments. Host-only entries keep their
current meaning. Part B of the issue (a fail-closed default scope for
unmapped CIMD clients) is marked "may be a follow-up" in the issue and is
deferred to a separate proposal.

## User stories

- AS a platform operator I WANT to admit one tenant's CIMD documents on a shared host SO THAT I can onboard a multi-tenant agent platform without trusting every tenant on it.
- AS a Telegram user I WANT a sibling tenant on the same host to be refused SO THAT an attacker's pod cannot get an authorization code for my account by sending me a link.
- AS an operator of an existing deployment I WANT my host-only entries to keep working unchanged SO THAT Town, ChatGPT, Claude and VS Code are not affected by the upgrade.
- AS an operator I WANT to see in the log which allowlist entry admitted or failed to admit a client SO THAT I can audit and debug admissions without reading the client document.

## Acceptance criteria (EARS)

Parsing (startup):

- WHEN `OAUTH_CIMD_ALLOWED_HOSTS` contains an entry of the form `host/seg1/.../segN/` THE SYSTEM SHALL accept it as a path-scoped entry with the host lowercased and the path prefix kept byte for byte.
- IF a path-scoped entry's prefix does not end with `/` THEN THE SYSTEM SHALL refuse to start with an error naming `OAUTH_CIMD_ALLOWED_HOSTS` and the entry.
- IF a path-scoped entry contains an empty segment (`//`), a `.` or `..` segment, a `%` character, `\`, `?`, `#`, `@`, `*`, whitespace, or a port THEN THE SYSTEM SHALL refuse to start with an error naming the entry.
- IF a path-scoped entry's host part starts with `.` (a suffix with a path) or is an IP literal THEN THE SYSTEM SHALL refuse to start.
- IF the path prefix is only `/` (for example `example.com/`) THEN THE SYSTEM SHALL refuse to start, because that entry is a host-wide entry written differently.
- WHEN the list holds only host-only and `.suffix` entries THE SYSTEM SHALL parse it exactly as it does today, including the existing refusal of an empty list, an empty entry, an IP literal, `*.a.com`, `a.com:443`, and public-suffix `.suffix` entries.

Matching (every resolve):

- WHEN a CIMD `client_id` has a host equal to a path-scoped entry's host (case-insensitive) and its escaped path starts with the entry's prefix (case-sensitive, whole segments) THE SYSTEM SHALL admit it.
- WHEN a CIMD `client_id` names a sibling path on the same host (for example another pod) that no entry covers THE SYSTEM SHALL refuse it with an error that satisfies `errors.Is(err, cimd.ErrNotAllowed)` and fetch nothing over the network.
- WHILE a host is named only by path-scoped entries THE SYSTEM SHALL NOT admit that host at host level.
- WHEN a host-only entry and a path-scoped entry name the same host THE SYSTEM SHALL admit every path on that host, since the host-only entry already does.
- IF the `client_id`'s escaped path contains `%2f`, `%5c` or `%25` (any case) THEN THE SYSTEM SHALL NOT admit it through a path-scoped entry.
- IF the `client_id` fails `parseCIMDURL` (dot segments including `%2e` forms, userinfo, query, fragment, a port other than 443, an IP literal) THEN THE SYSTEM SHALL refuse it as today, before any allowlist match.
- WHEN a `private_key_jwt` client's `jwks_uri` is fetched THE SYSTEM SHALL apply the same matcher to the `jwks_uri`, so a key set outside the admitted prefixes is refused with `ErrNotAllowed`.
- WHEN a CIMD client is re-resolved at the authorization_code or refresh_token grant and its admitting entry has been removed THE SYSTEM SHALL refuse the grant, as it does today for a removed host.

Logging:

- WHEN a CIMD client is admitted at `/oauth/authorize` THE SYSTEM SHALL log the matching allowlist entry and the `client_id`, and SHALL NOT log the client document.
- WHEN a CIMD client is refused because no entry matches THE SYSTEM SHALL log at WARN the `client_id` and, if the host is named by path-scoped entries only, that fact, and SHALL NOT log the client document.
- WHILE refusing a CIMD client THE SYSTEM SHALL keep the caller-facing answer unchanged (`errCIMDRefused`, HTTP 400), so the reason is not disclosed to the caller.

Documentation:

- WHEN the change is released THE SYSTEM's documentation SHALL describe path-scoped entries in `SECURITY.md`, `.env.example`, `README.md`, `docs/runbooks/admitting-an-agent-platform.md` (CIMD step and rollback) and `docs/platforms/compatibility.md` (Hermes Agent row note).

## Out of scope

- Part B of the issue: a fail-closed default (for example `core-readonly`, or denial) for a CIMD client that is allowed but has no `MCP_CLIENT_PROFILES` record. It needs its own setting and its own proposal.
- Wildcard hosts, path entries under `.suffix` hosts, glob or regex path patterns.
- Any change to DCR, `OAUTH_ALLOWED_IMPLICIT_HOSTS` semantics or `OAUTH_PREREGISTERED_CLIENTS`.
- Per-tenant secrets. Clients stay public with PKCE S256, or `private_key_jwt` as today.
- Changing the per-host fetch rate budget to a per-entry budget.
- The mctl-gitops change (mctlhq/mctl-gitops#2928) and the hosted Hermes test (Gate B). They follow the release and need owner approval.

## Open questions

- Does `jwks_uri` have to be covered by the same entry that admitted the `client_id`, or is any matching entry enough? This proposal uses "any entry in the allowlist matches the `jwks_uri`", which is fail-closed for a sibling pod that is not listed. Hermes is expected to use `none`, so this affects no known client today.
- Should the "admitted" log be INFO at `/oauth/authorize` only (proposed), or also at token grants? Logging at every refresh would be noisy, so this proposal logs only at authorize.
- Should the path prefix be compared case-sensitively? This proposal compares it case-sensitively (RFC 3986 paths are case-sensitive) and compares the host case-insensitively. The issue lists "case differences" as a test without naming the expected result.
- Part B is deferred. Until it ships, an admitted pod without an `MCP_CLIENT_PROFILES` record still gets the default scope surface. The rollout in mctlhq/mctl-gitops#2928 must therefore pair the path entry with the `core-readonly` binding, as the issue plans.
