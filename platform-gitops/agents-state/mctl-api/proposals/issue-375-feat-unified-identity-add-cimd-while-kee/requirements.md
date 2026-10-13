# Requirements: issue-375 — CIMD for MCP clients, client identity kept separate

Source: mctlhq/mctl-api#375 (parent mctlhq/.github#91). Hand-written
proposal (Claude Code session for the owner), not an issue-investigator run.
Line references are to mctl-api `main` at `9eeff3a` and must be re-read
before editing.

## Context

A grant has two identities that must never be merged:

- the **client identity**: which MCP/OAuth client asks for authorization;
- the **principal identity**: the human or service the upstream IdP
  (ZITADEL or GitHub) authenticated, resolved to the canonical `prn_…`.

Today the authorization server knows three kinds of client: pre-registered
(`OAUTH_PREREGISTERED_CLIENTS`, `staticClient`), dynamically registered
(`dcr_…`, RFC 7591, in-memory or `oauth_registered_clients`), and an
unregistered `client_id` whose `redirect_uri` is on the global allowlist or
is a loopback callback (`IsRedirectURIAllowed`, `oauth_server.go:1146-1192`).
There is no Client ID Metadata Document (CIMD) support, no consent screen
(authorize redirects straight to the IdP, `oauth_handlers.go:126-221`), no
audit record of an issued grant, and no SSRF-safe outbound fetch primitive
anywhere in the repository.

The Cloudflare MCP Portal uses DCR or static upstream credentials, so DCR
stays. CIMD is additive.

## Requirements (EARS)

### Advertising and enablement

- R1. WHILE `OAUTH_CIMD_ENABLED` is `true` THE SYSTEM SHALL advertise
  `client_id_metadata_document_supported: true` in
  `/.well-known/oauth-authorization-server`, and SHALL omit the field
  otherwise.
- R2. WHILE CIMD is disabled THE SYSTEM SHALL resolve clients exactly as
  today, including an `https://` `client_id`, so enabling the build changes
  nothing until the flag is set.

### Client resolution

- R3. WHEN CIMD is enabled and `client_id` is a CIMD URL (R5) THE SYSTEM
  SHALL resolve the client only from its metadata document, and SHALL decide
  `redirect_uri` against that document alone, before and instead of the
  global allowlist and the loopback rule — the same precedence a
  pre-registered client already has (`oauth_server.go:1147-1154`).
- R4. WHEN the metadata document cannot be fetched or fails validation THE
  SYSTEM SHALL refuse the authorization with a direct 400 (never a redirect
  to the requested `redirect_uri`, which is unverified at that point) and
  SHALL NOT fall back to any other resolution path.
- R5. THE SYSTEM SHALL accept as a CIMD URL only: scheme `https`; a host
  name (no IP literal); port absent or 443; a non-empty path other than
  `/`; no userinfo, query, fragment, or `.`/`..` segments; at most 512
  bytes.
- R6. THE SYSTEM SHALL refuse a CIMD URL whose host is not on the domain
  allowlist `OAUTH_CIMD_ALLOWED_HOSTS` (exact host, or a `.suffix` entry),
  before any network access. The allowlist is mandatory: an empty list
  admits no host, and the API SHALL refuse to start with
  `OAUTH_CIMD_ENABLED=true` and an empty or unparsable allowlist, so a
  misconfiguration is a visible boot failure rather than either "any public
  host" or a silently disabled feature.

### Fetch (fail closed)

- R7. THE SYSTEM SHALL fetch a metadata document only through an SSRF-safe
  client that: refuses every non-public destination (loopback, private,
  link-local, unspecified, multicast, CGNAT `100.64.0.0/10`, benchmarking
  `198.18.0.0/15`, reserved `240.0.0.0/4`, IPv6 ULA/link-local/
  documentation, IPv4-mapped and NAT64 `64:ff9b::/96` forms of any of
  these); checks the address actually being connected to (the socket
  control hook), so a DNS answer that changes between lookup and connect
  (rebinding) cannot reach a refused address; ignores proxy environment
  variables; follows no redirect (any 3xx is a failure); verifies TLS for
  the URL's host name.
- R8. THE SYSTEM SHALL bound every fetch: total timeout 5 s, response body
  cap 64 KiB (a larger body is a failure, not a truncation), status 200
  only, `Content-Type` `application/json` (parameters allowed) only.
- R9. THE SYSTEM SHALL rate-limit fetches per host and cap concurrent
  fetches globally, SHALL collapse concurrent fetches of one URL into one,
  and SHALL cache a valid document (honouring `Cache-Control: max-age`
  clamped to [5 min, 24 h], default 1 h) and a failure (5 min). A cached
  failure refuses exactly like a fresh one.

### Document validation

- R10. THE SYSTEM SHALL refuse a document that is not a JSON object, whose
  `client_id` is not byte-for-byte equal to the URL it was fetched from,
  whose `redirect_uris` is absent, empty or not a list of absolute URIs,
  whose `token_endpoint_auth_method` is anything but `none`, or that carries
  `client_secret` or `client_secret_expires_at`.
- R11. THE SYSTEM SHALL accept a `redirect_uri` for a CIMD client only when
  it matches an entry of the document's `redirect_uris`:
  - by exact string match; or
  - (RFC 8252 §7.3) WHEN both the requested URI and the document entry use
    scheme `http` and the IP-literal host `127.0.0.1` or `[::1]`, by an exact
    match of every component except the port, which may differ (a native
    client binds an ephemeral port). Scheme, host, path and query must match
    exactly; userinfo, a fragment or a backslash refuses the URI. The host
    name `localhost` gets no port exemption (RFC 8252 §8.3); it matches only
    exactly.
  The port exemption applies only against the client's own document, never
  to an entry the document does not list, and does not change the existing
  rule for pre-registered clients, which match their loopback entries with
  the port.
- R12. THE SYSTEM SHALL keep requiring PKCE S256 for CIMD clients (it is
  already mandatory for every client, `oauth_handlers.go:165-172`) and SHALL
  bind the issued code and refresh token to the CIMD `client_id` exactly as
  for any other client.

### Separation of identities

- R13. THE SYSTEM SHALL derive the principal of a CIMD grant only from the
  upstream IdP callback (`signinPrincipal`), exactly as for every other
  client: nothing in a metadata document can name, select or influence a
  principal, a tenant or a group.
- R14. WHEN a CIMD client is authorized THE SYSTEM SHALL show, on every
  authorization (consent is never remembered), after the upstream sign-in
  and before a code is issued, a consent page naming the
  client (`client_name`, else the URL host), the `client_id` URL and the
  redirect host, visibly separate from the signed-in account. Denial
  redirects `access_denied`; the consent token is single-use, expires in 5
  minutes and is bound to the browser that signed in.
- R15. WHEN any authorization code is issued THE SYSTEM SHALL write one
  `oauth.grant_issued` audit entry through the existing audit logger, with
  the principal in the existing principal column and the client in
  parameters (`client_id`, `client_kind` = `static` | `dcr` | `cimd` |
  `allowlisted`, `client_name`, `redirect_host`, `upstream`). No new table,
  no second trail.

### Compatibility

- R16. Pre-registered clients, DCR (including the Cloudflare MCP Portal)
  and allowlisted/loopback clients SHALL behave unchanged, with or without
  CIMD enabled, and need no configuration change.

## Acceptance (from #375, made testable)

- A1. Private/loopback/link-local targets are unreachable through a direct
  address, a DNS answer, a rebinding answer, or a redirect (unit tests with
  a stub resolver and a local TLS server).
- A2. Oversized, non-JSON, non-200 and slow responses fail closed.
- A3. A document naming another `client_id`, or a `redirect_uri` it does
  not list, is refused. A loopback IP-literal entry accepts the same URI on
  another port and refuses another path, host or scheme; a `localhost`
  entry on another port is refused.
- A4. The same human signing in through a CIMD client, a DCR client and a
  pre-registered client resolves to the same `prn_`; the token carries no
  client-chosen identity.
- A5. Mutation pins: removing the CIMD branch from client resolution makes
  the CIMD tests fail; removing DCR still breaks the DCR compatibility
  tests.
- A6. Live, after rollout: the metadata document advertises the flag; a
  CIMD client hosted on a public HTTPS URL completes a flow and appears in
  `oauth.grant_issued` with `client_kind=cimd` next to the human's
  principal; a CIMD URL resolving to a private address is refused; the
  Cloudflare MCP Portal still connects.

## Owner decisions (2026-10-13)

- CIMD hosts: mandatory allowlist `OAUTH_CIMD_ALLOWED_HOSTS` (R6), not
  "any public host".
- Consent: shown on every authorization, nothing persisted (R14).
- Loopback redirects: RFC 8252, any port for `127.0.0.1` / `[::1]` with
  scheme, host and path matched exactly (R11).

## Out of scope

- Confidential CIMD clients (`private_key_jwt`), `jwks`/`jwks_uri`, software
  statements.
- Remembering consent across authorizations.
- A `client_id` claim in the access JWT (the refresh token is already bound
  to the client; the audit entry records it).
- Any change to ZITADEL or GitHub sign-in, principals, tenants or groups.
