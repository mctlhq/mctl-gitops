# Design: issue-1404-feat-oauth-path-scoped-entries-in-oauth

## Current state

- `internal/oauth/cimd/cimd.go`
  - `ParseAllowedHosts(raw)` splits on `,`, lowercases each entry, and refuses
    an entry that contains any of `/:@*? #\`, is an IP literal, or is a
    `.suffix` that does not sit below a public suffix (`belowPublicSuffix`). It
    returns `[]string`. An empty list is a startup error.
  - `NewResolver` copies `Options.AllowedHosts` into `Resolver.allowed
    []string` after lowercasing and trimming each entry.
  - `Resolver.hostAllowed(host string)` matches an exact host, or a `.suffix`
    entry when the host is strictly longer than the suffix.
  - `Resolver.Resolve` calls `parseCIMDURL(clientID)` and then
    `hostAllowed(u.Hostname())` before any cache lookup or network access. A
    miss returns the bare `ErrNotAllowed` ("cimd: host is not allowed").
  - `parseCIMDURL` requires https, a host name (no IP), port absent or 443, a
    non-empty path other than `/`, no userinfo, query or fragment, and no
    `.`, `..`, `%2e` or `%2e%2e` segment variants. It does not refuse `%2f`,
    `%5c` or `%25` inside a segment.
  - `parseDocument` requires a `private_key_jwt` document's `jwks_uri` to be on
    the `client_id`'s host (`strings.EqualFold` of the host names only).
- `internal/oauth/cimd/assertion.go`: `fetchKeys` calls
  `parseCIMDURL(jwks_uri)` and `r.hostAllowed(u.Hostname())`, so key sets use
  the same host allowlist.
- `internal/oauth/cimd_client.go`: `resolveCIMDClient` calls
  `s.cfg.CIMD.Resolve`. `cimdFailure` logs `where`, `client_id` and `err` at
  WARN and maps the error to the opaque `errCIMDRefused` (400),
  `errCIMDUnavailable` (503) or `errCIMDAuthFailed`. `authenticateCIMDClient`
  re-resolves the client at both token grants. `handleTokenRefresh` in
  `internal/oauth/server.go` (around line 2808) relies on that re-resolve:
  removing a host from the allowlist cuts off that client's refresh families.
- `internal/config/config.go:962` calls `cimd.ParseAllowedHosts` when
  `OAUTH_CIMD_ACCEPT=true`. Lines 1034-1039 refuse URL-shaped
  `OAUTH_PREREGISTERED_CLIENTS` while CIMD is on.
  `cmd/server/main.go:1631` builds the resolver from
  `cfg.OAUTHCIMDAllowedHosts`, and line 1313 logs the list at startup.
- Prior art for path scoping: `(*Server).validateImplicitRedirectURI` in
  `internal/oauth/server.go` (around line 3616) splits each
  `OAUTH_ALLOWED_IMPLICIT_HOSTS` entry with `strings.Cut(allowed, "/")`,
  refuses dot segments and `%2e`, applies `path.Clean`, and checks the
  prefix. That logic is redirect-specific (it also accepts `-`-terminated
  prefixes) and is not reused verbatim.
- Tests: `internal/oauth/cimd/cimd_test.go` (`TestParseAllowedHosts`,
  `TestAllowlistBeforeAnyNetwork`, fixture helpers `newFixture`, `f.resolver`),
  `internal/config/config_cimd_test.go`, and
  `internal/oauth/cimd_client_test.go`
  (`TestCIMD_RealResolverRefusesUnlistedHostOffline` wires a real
  `cimd.NewResolver` with a `roundTripFunc` transport, and
  `TestCIMD_FullFlowAndHostRemoval` models host removal with `stubCIMD`).
- Docs that describe the allowlist: `SECURITY.md` (line 70), `.env.example`
  (lines 50-55), `README.md` (line 309),
  `docs/runbooks/admitting-an-agent-platform.md` (sections 2 and 5), and
  `docs/platforms/compatibility.md` (the Hermes Agent row, line 39).

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`, read in this
  run. It sets `OAUTH_CIMD_ACCEPT: "true"`, `OAUTH_CIMD_ADVERTISE: "true"`,
  `OAUTH_CIMD_ALLOWED_HOSTS: chatgpt.com,claude.ai,vscode.dev,www.town.com`
  (host-only entries, with no `agentspodium.com`), and `MCP_CLIENT_PROFILES`
  with a single Town `client_id` record bound to `core-reply`. The deployed
  list is therefore compatible with the new parser as is.
- `docs/platforms/compatibility.md` in the clone has the Hermes Agent row:
  DCR from per-user pod subdomains under `agentspodium.com`, not tested. The
  issue states that the newer CIMD document layout is path-per-pod on the
  apex host. I did not fetch it in this run.
- No mctl MCP tool calls were made. The gitops file was enough for the
  allowlist setting, and nothing in this design depends on runtime state.

## Proposed solution

### 1. Entry model (`internal/oauth/cimd/cimd.go`)

Add an internal type:

```go
type allowEntry struct {
    raw    string // normalized entry text, for logs
    host   string // lowercased host, without the leading "." for suffixes
    suffix bool   // ".example.com" form
    prefix string // "" for host-level entries; "/a/b/" for path-scoped ones
}
```

Add `parseAllowEntry(e string) (allowEntry, error)`, which holds all
validation:

- Split once with `strings.Cut(e, "/")`. The host part is lowercased, and the
  path part (re-prefixed with `/`) is kept byte for byte.
- The host part goes through the existing checks unchanged: no `:@*? #\`, not
  an IP, and a `.suffix` must be below a public suffix.
- If a path is present:
  - The host must not be a `.suffix`. A suffix with a path is refused (no
    wildcard hosts).
  - The prefix must be longer than `/` and must end with `/`.
  - It must not contain `%`, `\`, `?`, `#`, `@`, `*` or whitespace.
  - Its segments, after removing the trailing empty segment, must be
    non-empty and must not be `.` or `..`.
  - Optional hardening: build `"https://" + host + prefix + "x"` and require
    `parseCIMDURL` to accept it, which reuses the URL rules as the issue asks.

`ParseAllowedHosts` keeps its signature and return type (`[]string` of
normalized entries), so `internal/config` and `cmd/server/main.go` do not
change. It now calls `parseAllowEntry` for each entry. Its error messages stay
prefixed with `OAUTH_CIMD_ALLOWED_HOSTS:`, and new messages name the entry,
for example `%q: path prefix must end with "/"`.

`NewResolver` parses `Options.AllowedHosts` into `[]allowEntry` with the same
`parseAllowEntry`. It skips unparsable entries, which fails closed and keeps
today's behaviour, where tests can pass raw strings. `Resolver.allowed`
becomes `[]allowEntry`.

### 2. Matcher

Replace `hostAllowed(host string) bool` with:

```go
// match returns the first entry that admits u, or ok=false.
func (r *Resolver) match(u *url.URL) (entry string, ok bool)
```

The rules:

- `host := strings.ToLower(u.Hostname())`.
- Host-level entries (`prefix == ""`) apply today's exact and suffix logic,
  and their path is ignored.
- Path-scoped entries apply only when `host == e.host` and the URL path is
  "clean", that is, `strings.ToLower(u.EscapedPath())` contains none of
  `%2f`, `%5c` or `%25`. When that holds, the entry matches if
  `strings.HasPrefix(u.EscapedPath(), e.prefix)`. Because the prefix ends with
  `/`, the match is always on whole segments: `/clients/pod-a/` does not match
  `/clients/pod-ab/x.json`. Dot segments are already refused by
  `parseCIMDURL` before `match` runs, so `path.Clean` is not needed. Running
  it would also conflict with the "byte for byte" `client_id` identity used
  by the cache and by `MCP_CLIENT_PROFILES`.
- Host-level entries are checked first. They are broader, and the reported
  entry should be the one that actually decided the match.

Call sites:

- `Resolve`: if `match(u)` fails, return
  `fmt.Errorf("%w%s", ErrNotAllowed, r.missDetail(host))`. Here `missDetail`
  returns `"; host has path-scoped entries only"` when some path entry names
  the host, and `""` otherwise. `errors.Is(err, ErrNotAllowed)` still holds,
  and the message still starts with `cimd: host is not allowed`, as the
  issue's server-level criterion expects. The check stays before the cache,
  singleflight and fetch, so an unlisted pod uses no rate budget and no
  network.
- `fetchKeys` (`assertion.go`): `match(u)` on the `jwks_uri`. A key set
  outside every admitted prefix is refused. `parseDocument`'s same-host rule
  is unchanged.

### 3. Exposing the matched entry for the accept log

Add `AllowEntry string` to `cimd.Document`, set in `Resolve` from `match` on
every return path, including cache hits, because the cached `Document` is
returned by value. In `internal/oauth`, the authorize-path caller of
`resolveCIMDClient` (`validateClient` / the authorize handler, with `where ==
"authorize"`) logs at INFO
`"oauth: cimd client admitted", "client_id", id, "allow_entry", doc.AllowEntry`.
The document body, redirect URIs and client name are not logged. Refusals
already go through `cimdFailure`, whose `err` now carries the detail. The
caller-facing answer is still the opaque `errCIMDRefused`. Allowlist entries
are configuration and not user data, so `internal/audit/redact.go` needs no
new field.

### 4. Config and startup

`internal/config/config.go` stays as it is. Update the
`OAUTHCIMDAllowedHosts` doc comment (around line 136) to mention
`host/path-prefix/`. The startup log at `cmd/server/main.go:1313` already
prints the list.

### 5. Documentation (same PR)

- `SECURITY.md`, CIMD paragraph: what path entries admit, that
  segment-boundary and encoded-separator rules apply, that a host with only
  path entries is not admitted at host level, and that removing an entry cuts
  off refreshes exactly like removing a host. Add a caution that an admitted
  pod without an `MCP_CLIENT_PROFILES` record still gets the default scope
  surface until part B ships, so path entries should be paired with a
  profile binding.
- `.env.example`: an example such as
  `OAUTH_CIMD_ALLOWED_HOSTS=platform.example.test,pods.example.test/oauth/mcp/clients/pod-a/`.
- `README.md` table row for `OAUTH_CIMD_ALLOWED_HOSTS`.
- `docs/runbooks/admitting-an-agent-platform.md`: step 2 gets a
  multi-tenant variant (a path entry plus a `client_id` profile binding), and
  section 5 adds "removing the path entry cuts off that tenant's refreshes".
- `docs/platforms/compatibility.md`: a note on the Hermes Agent row that a
  path-scoped CIMD entry is now possible (status unchanged until Gate B).
  `docs/compatibility_test.go` and `docs/runbook_test.go` may assert document
  structure, so run `go test ./docs/...`.

## Alternatives

1. **Reuse `validateImplicitRedirectURI`'s matcher.** Dropped. It lives in
   `package oauth`, accepts `-`-terminated prefixes (redirect-specific), and
   uses `path.Clean`, which normalizes the path. A CIMD `client_id` is an
   identity compared byte for byte (cache key, `MCP_CLIENT_PROFILES`), so the
   matcher must test the exact escaped path that `parseCIMDURL` has already
   proven free of dot segments.
2. **A separate setting such as `OAUTH_CIMD_ALLOWED_CLIENT_PREFIXES`.**
   Dropped. The issue asks for the entry form in the existing variable,
   mirroring `OAUTH_ALLOWED_IMPLICIT_HOSTS`. A second list would also make the
   "a host with only path entries is not host-admitted" rule harder to
   reason about.
3. **Allow pre-registered URL-shaped client IDs, or exact `client_id` entries
   only.** Dropped. An exact-URL list would need an operator change for every
   new server document under a pod, and lifting the
   `OAUTH_PREREGISTERED_CLIENTS` guard reintroduces the ambiguity that the
   guard exists to prevent. A trailing-`/` prefix covers a pod's documents
   and still keeps sibling pods out.

## Platform impact

- **Migrations:** none. No database or schema change. Refresh families are
  re-resolved against the new matcher at the next grant.
- **Backward compatibility:** every list the current parser accepts is
  accepted and matched identically, because host-level entries ignore the
  path. The deployed list (`chatgpt.com,claude.ai,vscode.dev,www.town.com`)
  is unaffected. Only entries containing `/`, which are refused at startup
  today, gain a meaning. The error type and message prefix of `ErrNotAllowed`
  are preserved.
- **Resource impact:** negligible. One more string comparison per entry on
  each resolve. The rate budget stays per host. Unlisted pods are refused
  before they reach the budget, so a sibling pod cannot exhaust the
  admitted pod's budget through `Resolve`.
- **Risks and mitigations:**
  - *Prefix confusion (`pod-a` vs `pod-ab`).* The mandatory trailing `/`
    ensures whole-segment matching, and a unit test covers it.
  - *Encoding tricks (`%2f`, `%252f`, `%2e%2e`).* `parseCIMDURL` refuses
    dot-segment variants. The matcher refuses `%2f`, `%5c` and `%25` for path
    entries, and entries themselves may not contain `%`. Tests cover each
    case.
  - *Admitted pod gets the default scope surface (part B not shipped).* This
    is documented in `SECURITY.md` and the runbook, and the gitops rollout
    pairs the entry with the `core-readonly` `client_id` binding.
  - *Shared host budget.* An admitted pod's own documents share the per-host
    fetch budget with other admitted pods. That is unchanged behaviour and
    acceptable at current scale.
- **Rollout:** release, then mctlhq/mctl-gitops#2928 switches to the path
  entry plus binding, with owner approval for admission.

## Open questions

- Whether `jwks_uri` must match the same entry as the `client_id`. This design
  accepts any matching entry, and only `private_key_jwt` clients are
  affected.
- Whether the accept log should also fire at token grants. This design logs
  it at authorize only.
- Case handling for the path. This design compares it case-sensitively,
  following RFC 3986.
- The Hermes document URL layout comes from the issue text. I did not
  observe it in this run.
