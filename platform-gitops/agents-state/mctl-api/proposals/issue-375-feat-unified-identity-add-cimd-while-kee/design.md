# Design: issue-375 — CIMD for MCP clients

Additive to the existing authorization server; no change to sign-in,
principals, tenants or the DCR/pre-registered paths. Line references are to
mctl-api `main` at `9eeff3a`.

## 1. `internal/netsafe` — the SSRF-safe fetch primitive

No such primitive exists today (`internal/domains/verify.go` dials a DNS
resolver, `internal/vault/client.go` a fixed address; neither guards
destinations). New package, no dependency on `auth`:

```go
// Client returns an *http.Client that can reach public addresses only.
func Client(opts Options) *http.Client
type Options struct {
    Timeout      time.Duration // total, default 5s
    AllowedPorts []int         // default [443]
    Resolver     Resolver      // net.DefaultResolver; tests inject a stub
}
func PublicAddr(ip netip.Addr) bool
```

- `Transport.Proxy = nil` (proxy environment variables never apply).
- `DialContext` resolves the host through `Resolver`, keeps only addresses
  `PublicAddr` accepts, and dials them by IP with a `net.Dialer` whose
  `Control` hook re-checks the address of the socket actually being
  connected. That second check is what defeats rebinding: the decision is
  made on the connected address, not on an earlier answer.
- `PublicAddr` unmaps IPv4-mapped IPv6 and the NAT64 prefix
  `64:ff9b::/96` before testing, and refuses loopback, private, link-local
  (unicast and multicast), unspecified, multicast, `0.0.0.0/8`,
  `100.64.0.0/10`, `192.0.0.0/24`, `198.18.0.0/15`, `240.0.0.0/4`,
  documentation ranges, `fc00::/7`, `fe80::/10`, `2001:db8::/32`.
- `CheckRedirect` returns an error: any 3xx fails.
- TLS: default verification against the URL host (SNI preserved because
  the dial is by IP but the TLS config keeps `ServerName`).
- `ReadLimited(resp, max)` reads at most `max+1` bytes and fails if it got
  more.

## 2. `internal/auth/cimd` — resolver

```go
type Document struct {
    ClientID, ClientName string
    RedirectURIs         []string
}
type Resolver struct { /* http client, cache, limiter, allowlist */ }
func (r *Resolver) Resolve(ctx context.Context, clientID string) (Document, error)
func IsCIMDURL(s string) bool // R5 shape only, no network
```

- `IsCIMDURL` implements R5. `Resolve` checks the allowlist (R6) before any
  network access, then the cache, then a `singleflight` fetch.
- Fetch: GET with `Accept: application/json`, status 200, media type
  `application/json`, `ReadLimited` 64 KiB, strict JSON object decode into
  a raw map, then R10: exact `client_id`, `redirect_uris` non-empty list of
  absolute URIs (each at most 2 KiB, at most 20), `token_endpoint_auth_method
  == "none"`, no `client_secret*`. `client_name` is optional, trimmed to 100
  runes, and only ever rendered HTML-escaped.
- Cache: positive (max-age clamped to [5m, 24h], default 1h), negative 5m,
  bounded LRU (1024 entries). Per-host limiter (10 fetches/min) and a global
  semaphore (8 concurrent). Rate-limited or semaphore-full counts as a
  failure, never as a pass.
- Every failure is a typed error (`ErrNotAllowed`, `ErrFetch`,
  `ErrInvalidDocument`, `ErrRateLimited`) for logs and metrics
  (`oauth_cimd_resolve_total{result}`); the HTTP answer is the same 400.

## 3. Wiring into `OAuthServer`

- `OAuthServer.CIMD *cimd.Resolver` (nil = disabled, R2).
- `IsRedirectURIAllowed` (`oauth_server.go:1146`) gains a branch right after
  the pre-registered one and before the global allowlist:

  ```go
  if s.CIMD != nil && cimd.IsCIMDURL(clientID) {
      doc, err := s.CIMD.Resolve(ctx, clientID)
      return err == nil && slices.Contains(doc.RedirectURIs, uri)
  }
  ```

  The method gains a `ctx` (call sites: authorize, DCR registration with
  `""`). A CIMD `client_id` therefore never reaches the allowlist or
  loopback rules, which is the property R3 needs.
- `GetClient` returns a `RegisteredClient{ClientID, ClientName,
  RedirectURIs}` built from the document for a CIMD URL, so the token
  endpoint's log enrichment and everything else that reads a client keep
  working; `ClientForLog` reports a CIMD URL as not consulted (no fetch on
  the token path).
- `ClientKind(clientID) string` (`static`, `dcr`, `cimd`, `allowlisted`)
  for audit, computed from the same predicates, never from a document.
- `handleOAuthMeta` sets `ClientIDMetadataDocumentSupported` (new
  `omitempty` bool) when `CIMD != nil`.

## 4. Consent interstitial (CIMD only)

The signed-in human is known only after the upstream callback, so consent
sits between the callback and `IssueCode`:

1. Both callbacks (`oauth_handlers.go:303`, `oauth_upstream.go:363`) call
   one helper `h.issueOrConsent(...)`. For a non-CIMD client it issues the
   code exactly as today (R16).
2. For a CIMD client it stores `{login, principalID, groups, clientID,
   redirectURI, codeChallenge, clientState, upstream}` in the existing
   `flowstore` under a random 256-bit token (TTL 5 min, single use via
   `takeFlow`), sets a `__Host-mctl_consent` cookie (HttpOnly, Secure,
   SameSite=Lax) holding the token's SHA-256, and renders a static HTML page
   (no external assets, CSP `default-src 'none'; style-src 'unsafe-inline';
   form-action 'self'`).
3. `POST /oauth/consent` (form: `token`, `decision`) takes the flow entry,
   requires the cookie hash to match, then either issues the code and
   redirects, or redirects `access_denied`. A missing, replayed, expired or
   cookie-mismatched token is a direct 400.

## 5. Audit

`oauth.grant_issued`, written by the same helper for every client kind
through `h.logAudit` with `audit.Entry{UserID: login, PrincipalID:
principalID, Operation: "oauth.grant_issued", RiskLevel: low, Parameters:
{client_id, client_kind, client_name, redirect_host, upstream}}`. The
principal stays in the principal column; the client only ever in
parameters (R13, R15). No new table.

## 6. Configuration

| Env | Default | Meaning |
|---|---|---|
| `OAUTH_CIMD_ENABLED` | `false` | Build the resolver and advertise CIMD |
| `OAUTH_CIMD_ALLOWED_HOSTS` | empty (any public host) | Comma list; `.example.com` matches subdomains |

Helm `deployment.yaml` and the README env table gain both. Rollout ships
disabled, then flips in mctl-gitops (owner decision on the allowlist).

## 7. Failure semantics

Every unknown is a refusal: resolver error, rate limit, cache miss under a
full semaphore, malformed document, allowlist miss. Nothing degrades to the
allowlist/loopback path, and nothing degrades to "unknown client accepted".
The token endpoint never fetches.

## 8. Risks

- **Outbound traffic from the API pod.** Bounded by R8/R9; the allowlist
  can narrow it to known vendors. NetworkPolicy egress already allows
  443 to the internet for the GitHub/ZITADEL calls (verify in rollout).
- **Phishing via a convincing `client_name`.** Mitigated by showing the
  URL host and redirect host next to the name, and by the optional
  allowlist.
- **Long `client_id` values** in the token form: 512-byte CIMD cap is far
  below `maxOAuthFormBytes` (16 KiB).
