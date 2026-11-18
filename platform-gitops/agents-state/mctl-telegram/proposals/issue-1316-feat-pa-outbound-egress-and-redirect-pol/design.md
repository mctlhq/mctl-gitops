# Design: issue-1316-feat-pa-outbound-egress-and-redirect-pol

## Current state

- `internal/netsafe/netsafe.go` provides `Client(Options)`, `PublicAddr`, `ReadLimited` and errors `ErrNonPublic`, `ErrTooLarge`, `ErrRedirect`. It already:
  - resolves once in a custom `DialContext`, filters answers with `PublicAddr`, and dials the accepted IP literal (no rebinding window); a `net.Dialer.Control` hook (`controlPublic`) re-checks as defence in depth;
  - denies loopback, private (RFC 1918, `fc00::/7` via `IsPrivate`), unspecified, multicast, link-local, CGNAT `100.64.0.0/10`, `0.0.0.0/8`, documentation, 6to4, Teredo, NAT64 local-use, site-local, and unwraps IPv4-mapped and `64:ff9b::/96` NAT64 addresses;
  - sets `Transport.Proxy = nil` (proxy env vars ignored), restricts ports (default 443), refuses every redirect via `CheckRedirect`, and sets total/handshake/header timeouts;
  - leaves body caps to the caller (`ReadLimited`).
- It does **not**: enforce the `https` scheme (a plain `http://host:443` URL would be dialled), check a host allowlist, allow any redirect hop, deny cluster ranges outside RFC 1918/CGNAT, or cap bodies at the transport (a streaming MCP response read by a library bypasses `ReadLimited`).
- Its only production users are `internal/oauth/cimd/cimd.go` (line ~276, `netsafe.Client(netsafe.Options{Timeout: 5 * time.Second})`, `netsafe.ReadLimited` at ~525) and `internal/oauth/cimd/assertion.go`.
- Existing tests in `internal/netsafe/netsafe_test.go`: `TestPublicAddr`, `TestResolvedNonPublicRefused`, `TestDirectIPAndPortRefused`, `TestControlHookRefusesNonPublic`, `TestRedirectRefusedAndLoopbackServerUnreachable`, `TestRedirectIsFailure`, `TestProxyEnvIgnored`, `TestReadLimited`, `TestTimeoutFailsClosed`. Note `TestTimeoutFailsClosed` replaces `c.Transport` with a plain transport, so it does not exercise the netsafe transport; `TestProxyEnvIgnored` only checks the field, not behaviour.
- No PA package exists yet. ADR 0011 places it "as a new package next to `internal/bot` and `internal/agentworker`". `mark3labs/mcp-go v1.4.0` is in `go.mod`; the MCP client package is used today only in `internal/auth/telegramoidc`.
- The threat model (T9, lines ~458-489) defines S1-E1..E7; its "Gate evidence" paragraph requires a checked-in manifest mapping each ID to a test, CI failure on a missing ID, and a recorded mutation run. No such manifest exists in the clone. A precedent for mutation tooling is `scripts/gate-889/mutations.py` (prints `caught`/`SURVIVED`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: service runs in tenant `labs`, ingress hosts `tg.mctl.ai` and `labs-mctl-telegram.mctl.ai`. No `PA_*` env vars and no proxy env vars configured (grep for `PA_`, `proxy` found none).
- `$MCTL_GITOPS_ROOT/services/labs/mctl-alice/values.yaml`: ingress host `alice.mctl.ai`.
- `$MCTL_GITOPS_ROOT/tenants/labs/values.yaml`: `networking.allowClusterEgress: true`, `allowInternetEgress: true`, `allowIntraNamespace: true` — so the cluster layer does not block in-cluster SSRF; the application layer must.
- Cluster pod/service CIDRs: not found in any file read; recorded as an open question. mctl MCP tools were not used (gitops files were sufficient for the above).
- `go env GOMODCACHE` lookup of mcp-go sources returned nothing (module cache unavailable); mcp-go client-transport options are unverified.

## Proposed solution

New package `internal/pa/egress` (the PA package root `internal/pa` is created by sibling issues; this one only adds the `egress` subpackage). It composes `internal/netsafe` rather than forking it.

### 1. Extend `internal/netsafe` (backward compatible)

- `Options.ExtraDeny []netip.Prefix`: additional denied prefixes (cluster pod/service CIDRs). Checked in the `DialContext` loop and in `controlPublic` (via a closure) after `PublicAddr`, with the same IPv4-mapped/NAT64 unwrapping (factor out `unwrap(ip)`).
- `Options.CheckRedirect func(*http.Request, []*http.Request) error`: when nil the current refuse-all behaviour is kept, so CIMD is unchanged.
- No other behaviour change; existing tests stay green.

### 2. `internal/pa/egress`

```go
type Kind int // KindDiscovery, KindDCR, KindToken, KindRevocation, KindMCP

type ServerPolicy struct {
    Name  string   // catalog server name, e.g. "tg", "alice"
    Hosts []string // exact lowercase hostnames (no wildcards), e.g. "tg.mctl.ai"
}

type Limits struct{ MaxBody int64; Timeout time.Duration }

type Config struct {
    ClusterDeny []netip.Prefix   // from PA_EGRESS_DENY_CIDRS, required non-empty parse
    Limits      map[Kind]Limits  // defaults below
    Resolver    netsafe.Resolver // tests inject a stub
}

func New(cfg Config) (*Egress, error)
func (e *Egress) Client(server ServerPolicy, kind Kind) *http.Client
```

`Client` returns an `*http.Client` whose transport is a chain:

1. **`guardRoundTripper`** (outermost): before delegating, rejects `req.URL.Scheme != "https"` (`ErrScheme`), userinfo, explicit port other than 443, IP-literal hosts, and hosts not in `server.Hosts` after lowercasing and trailing-dot trimming (`ErrHostNotAllowed`). This runs before DNS, so S1-E1/E2 never resolve or dial. It applies `context.WithTimeout(limits.Timeout)` to the request and cancels on body close.
2. **`capBody`**: wraps `resp.Body` in a reader that returns `ErrTooLarge` once more than `MaxBody` bytes are read (reads at most `MaxBody+1`). Because it is on the transport, it also caps streamed MCP responses read by mcp-go. Each SSE/streamable response is capped per response.
3. **netsafe transport**: `netsafe.Client(netsafe.Options{Timeout, AllowedPorts: {443}, Resolver, ExtraDeny: cfg.ClusterDeny, CheckRedirect: ...})`, providing resolve-check-pin dialling, proxy-off and the Control hook.

Redirects: for `KindDiscovery`, `CheckRedirect` allows at most 2 prior hops (`len(via) >= 2` returns `ErrRedirect` on the third), and each hop request passes again through `guardRoundTripper` (scheme, allowlist) and the netsafe dialer (address), because `http.Client` re-enters the transport for each hop. For every other kind, `CheckRedirect` returns `netsafe.ErrRedirect`. `CheckRedirect` additionally rejects a downgrade to `http` explicitly so the error is specific.

Default limits (owner to confirm, see Open questions): discovery 64 KiB / 5 s; DCR 64 KiB / 10 s; token 16 KiB / 10 s; revocation 16 KiB / 10 s; MCP 1 MiB / 30 s.

Configuration: `PA_EGRESS_DENY_CIDRS` (comma-separated prefixes) parsed in `internal/config` alongside the other `PA_*` switches. Malformed values fail PA startup. The value is always unioned with a built-in list (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `100.64.0.0/10`) so a missing variable cannot open the cluster.

Static guard: a Go test in `internal/pa` (AST walk over non-test files under `internal/pa/...` excluding `egress`) fails on `http.DefaultClient`, `http.Get/Post/Head/PostForm`, `http.DefaultTransport`, or composite literals of `http.Client`/`http.Transport`. This makes "every PA request goes through egress" checkable.

### 3. S1 manifest and mutation evidence

- `docs/agent-runtime/pa-s1-manifest.json` (created if absent; sibling issues append): `{"S1-E1": "internal/pa/egress.TestS1E1_HTTPRefused", ...}`.
- `internal/pa/egress/manifest_test.go`: loads the manifest, fails if an `S1-E*` ID has no test of that name in the package, or a `TestS1E*` test has no ID.
- `scripts/pa-s1/mutations.sh`: for each S1-E ID, applies a named source mutation (e.g. drop the scheme check; return true from the allowlist; skip `PublicAddr`; resolve again in dial; follow all redirects; remove `capBody`; drop the timeout; set `Proxy: http.ProxyFromEnvironment`), runs the one test, and prints `caught`/`SURVIVED`, exiting non-zero on a survivor. Pattern follows `scripts/gate-889/mutations.py`.

## Alternatives

1. **Use `netsafe.Client` directly per call site.** Dropped: no scheme or host allowlist, no discovery hops, body caps depend on every caller remembering `ReadLimited`, and mcp-go reads bodies itself. Each call site would re-implement policy.
2. **Fork netsafe into a PA-only client.** Dropped: duplicates the address deny list, which then drifts between CIMD and PA. Extending netsafe with two optional fields keeps one list and leaves CIMD behaviour unchanged.
3. **Enforce at the cluster with NetworkPolicy / egress gateway only.** Dropped as the primary control: tenant `labs` has `allowClusterEgress: true` for other workloads, a policy cannot express per-server host allowlists or redirect rules, and S1 must run in CI without a deployment. It remains a reasonable defence-in-depth follow-up.

## Platform impact

- **Migrations:** none. No schema change.
- **Backward compatibility:** `netsafe.Options` gains optional fields with zero-value defaults equal to today's behaviour; CIMD fetch path is untouched and its tests remain green.
- **Configuration:** new optional `PA_EGRESS_DENY_CIDRS`; only read when the PA is enabled (`PA_ENABLED`). Not added to gitops in this proposal (HOLD).
- **Resources:** negligible. `DisableKeepAlives: true` (inherited from netsafe) costs a TLS handshake per request; acceptable at PA Phase 1 volume (8 tool calls per run). If MCP session latency matters later, a keep-alive pool can be allowed because the dialled IP is already pinned per connection.
- **Risks and mitigations:**
  - Hairpin to `tg.mctl.ai` resolving to an in-cluster address would be refused: verified on preview before Phase 1 leaves; fix is DNS, not an allowlist exception.
  - Over-tight caps breaking legitimate MCP responses: caps are per-kind config with metrics on `ErrTooLarge`.
  - A future PA code path bypassing the egress client: the static guard test.
  - Rollback: PA is behind fail-closed `PA_ENABLED`; netsafe changes are additive.
