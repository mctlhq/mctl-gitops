# Design: issue-296-mctl-whoami-reports-the-internal-loopbac

## Current state

**One `Server` struct, one URL, two jobs.** `internal/mcp/server.go:36-52`:

```go
type Server struct {
    apiURL     string
    apiToken   string
    httpClient *http.Client
    mcpServer  *server.MCPServer
}

func NewServer(apiURL, apiToken string) *Server {
    return &Server{apiURL: strings.TrimRight(apiURL, "/"), ...}
}
```

`apiURL` is used for two unrelated purposes:

1. As the upstream base for every REST call the tools make back into the API —
   `apiGet`/`apiPostJSON`/`apiDelete` concatenate `s.apiURL+path`
   (`internal/mcp/server.go:2428`, `:2444`, `:2453`).
2. As a display string in `toolWhoami` (`internal/mcp/server.go:212-213`):

```go
msg := fmt.Sprintf("Authenticated to %s\n\nUser: %s\nAdmin: %v\nTeams: %v\nAccessible namespaces: %v",
    s.apiURL, identity.ID, identity.IsAdmin, identity.Groups, identity.Namespaces)
```

**The two callers disagree about what `apiURL` means.**

- In-process (production, serves `api.mctl.ai` and everything behind the
  Cloudflare portal): `cmd/api/main.go:307` —
  `mcpSrv := mctlmcp.NewServer("http://localhost:"+cfg.Port, "")`, deliberately
  loopback ("avoid hairpin routing and public egress issues", per the comment
  right above it). The handler is mounted at `/mcp` by
  `internal/api/router.go:373-378` via `NewStreamableHTTPHandler`, inside the
  authenticated route group, with the caller's token forwarded through the
  request context (`effectiveToken`, `internal/mcp/server.go:2420`).
- Standalone stdio: `cmd/mcp/main.go:12-18` — `MCTL_API_URL`, defaulting to
  `https://api.mctl.ai`. Here `apiURL` *is* the caller-facing address, which is
  why the line has looked correct in local testing.

**The public URL already exists in the process.** `cmd/api/main.go:114-147`
builds `auth.NewOAuthServer(cfg.SelfURL, ...)`; `internal/auth/oauth_server.go:48`
documents `BaseURL` as "the public base URL of this server, e.g.
`https://api.mctl.ai`", and `:575` uses it as the OIDC `Issuer` that tokens are
verified against (`:678`, `internal/auth/oidc.go:266`). `cfg.SelfURL` comes from
`envOr("SELF_URL", "https://api.mctl.ai")` (`cmd/api/main.go:617`). So the value
the issue asks for is available at the exact call site that constructs the MCP
server — it is simply not passed in.

**Second leak, same root cause.** On upstream failure the whoami handler returns
`mcplib.NewToolResultError(fmt.Sprintf("Failed to get identity: %v", err))`
(`internal/mcp/server.go:200-202`). `doRequest` wraps transport errors as
`fmt.Errorf("request failed: %w", err)` (`internal/mcp/server.go:2466`) and Go's
`*url.Error` renders the full URL, so a failing in-process call answers
`... Get "http://localhost:8080/api/v1/whoami": dial tcp ...`. Any acceptance
check phrased as "the response contains no loopback address" has to cover this
path too.

**Test surface today.** `internal/mcp/server_test.go` constructs servers with
`NewServer("http://localhost:8080", "")` and drives tools through
`mcpSrv.HandleMessage(ctx, json.RawMessage(...))` with `tools/call` envelopes
(see the `callTool*` helpers, e.g. `:344`, `:1026`); `internal/mcp/stateless_test.go`
does the same over a real `httptest` server. There is no whoami test at all.
Note that `NewServer` is called from ~12 test helpers, so changing its signature
is a wide, low-value diff.

## Proposed solution

Separate the two meanings of `apiURL` — *upstream base* (internal, loopback by
design) and *public issuer* (what a human is told) — and give `cmd/api` a shared,
testable construction path.

### 1. A `publicURL` field on `mcp.Server`

`internal/mcp/server.go`:

```go
type Server struct {
    apiURL     string // upstream base for REST calls; loopback in-process, by design
    publicURL  string // caller-facing base URL shown to users; never loopback
    ...
}
```

`NewServer(apiURL, apiToken)` keeps its signature and sets
`publicURL = apiURL` (trimmed). That preserves the stdio binary's correct
behaviour (`cmd/mcp/main.go` passes `https://api.mctl.ai`) and leaves all
existing test helpers compiling unchanged.

### 2. A shared in-process constructor — the "production path" the test drives

Add to `internal/mcp/server.go`:

```go
// NewInProcessServer builds the Server that cmd/api embeds: REST calls go back
// over loopback (no hairpin routing, no public egress), while user-facing text
// names the deployment's public base URL — the OAuth issuer the caller
// authenticated against (auth.OAuthServer.BaseURL / SELF_URL).
func NewInProcessServer(port, publicURL string) *Server {
    s := NewServer("http://localhost:"+port, "")
    s.publicURL = strings.TrimRight(publicURL, "/")
    return s
}
```

`cmd/api/main.go:307` becomes
`mcpSrv := mctlmcp.NewInProcessServer(cfg.Port, publicBaseURL(cfg, oauthServer))`.

**Amended during review (2026-09-12).** The original text passed `cfg.SelfURL` a
second time and argued the two values "cannot drift apart" because they happen
to come from the same config field. That is an argument, not a guard: a later
edit at either call site diverges silently and no test fails. Source the value
from the object that already holds it instead, and extract the choice into a
helper so `package main` can test it:

```go
// publicBaseURL is the caller-facing base URL shown by mctl_whoami. When the
// OAuth server is enabled it IS the issuer the caller's token was verified
// against -- read it from there rather than re-deriving it from config, so the
// two cannot name different deployments. With OAuth disabled there is no
// issuer, and cfg.SelfURL is the only public URL the process knows.
func publicBaseURL(cfg config, oauth *auth.OAuthServer) string {
    if oauth != nil && oauth.BaseURL != "" {
        return oauth.BaseURL
    }
    return cfg.SelfURL
}
```

`oauthServer` is already in scope at `:307` (declared `:114`, built `:116-126`),
and `cmd/api` already has `package main` tests (`cmd/api/main_test.go`), so this
helper is directly testable -- see T7. This function is the
seam the acceptance test needs: the test calls the *same* constructor
production calls, with arbitrary ports, instead of re-deriving the wiring.

### 3. Render the line only when the public URL is trustworthy

```go
func (s *Server) displayURL() string {
    if s.publicURL == "" || isLoopbackURL(s.publicURL) {
        return ""
    }
    return s.publicURL
}
```

`isLoopbackURL` parses with `net/url` and reports true for host `localhost`
(case-insensitive) or any `net.ParseIP(host).IsLoopback()` — covering `127.0.0.1`,
the whole `127.0.0.0/8` block, and `::1`. `internal/auth` has a similar
unexported `isLoopbackRedirectURI` (`internal/auth/oauth_server.go:467`) but its
semantics are redirect-URI specific (requires scheme `http`, rejects userinfo and
backslashes) and it is not exported; a five-line local helper in `internal/mcp`
is the honest reuse boundary. `internal/api.isLoopbackRemote`
(`internal/api/router.go:388`) works on `RemoteAddr`, not URLs.

`toolWhoami` then composes:

```go
identityBlock := fmt.Sprintf("User: %s\nAdmin: %v\nTeams: %v\nAccessible namespaces: %v",
    identity.ID, identity.IsAdmin, identity.Groups, identity.Namespaces)
msg := identityBlock
if u := s.displayURL(); u != "" {
    msg = "Authenticated to " + u + "\n\n" + identityBlock
}
```

The identity block is byte-identical to today's tail, satisfying the
"identity fields unchanged" acceptance criterion.

### 4. Close the error path

Add a tiny helper and use it in `toolWhoami` only:

```go
// redactUpstream strips the internal upstream base URL from an error rendered
// to a caller. The full error still goes to slog for operators.
func (s *Server) redactUpstream(err error) string {
    return strings.ReplaceAll(err.Error(), s.apiURL, "the mctl API")
}
```

`toolWhoami`'s failure branch logs `slog.Error("whoami upstream call failed", "error", err)`
(JSON `slog` is the repo convention per `CLAUDE.md`) and returns
`NewToolResultError("Failed to get identity: " + s.redactUpstream(err))`. Because
`s.apiURL` is exactly the prefix `apiGet` concatenated, the substring replacement
is exact, not heuristic. Widening this to the other tools is deliberately left
out of scope (see requirements).

### 5. Documentation

Update the `mctl_whoami` tool description in `internal/mcp/server.go:191-195`
only if wording implies a URL is always returned; no README/docs file in the
clone contains the string `Authenticated to` (grepped), so no docs change is
expected.

## Alternatives

1. **Drop the first line entirely** (the issue's second option). Smallest diff,
   trivially satisfies the acceptance property, and needs no new plumbing.
   Dropped because the issue itself argues the issuer is the more useful
   outcome: a user with portal, direct, and preview connectors loses the only
   line that distinguishes them. Kept as the *fallback* behaviour when no
   non-loopback public URL is configured, so the useful case and the safe case
   are both covered.
2. **Derive the URL per request from the incoming HTTP request** (`Host` /
   `X-Forwarded-Host`, injected into the context by the existing
   `server.WithHTTPContextFunc` hook at `internal/mcp/server.go:67-70`). Most
   accurate behind the portal and for previews, but it renders an
   attacker-controlled header into a trust-establishing line ("which mctl am I
   authenticated to"), and it yields nothing for the stdio transport, which has
   no request. Dropped: the OAuth issuer is server-controlled and is the value
   the caller's token was actually verified against.
3. **Change `NewServer`'s signature to `NewServer(apiURL, publicURL, apiToken)`.**
   Explicit, no "default publicURL to apiURL" subtlety. Dropped: it touches ~12
   call sites in `internal/mcp/*_test.go` plus `cmd/mcp/main.go` with no
   behavioural gain, and it would let a future caller pass the loopback URL as
   the public one just as easily. The named `NewInProcessServer` constructor
   encodes the intent instead, and doubles as the test seam.
4. **Read `SELF_URL` directly inside `internal/mcp`.** Dropped: config parsing
   lives in `cmd/api/main.go` (`envOr`, `:617`); a package reaching into the
   environment behind its constructor breaks the interface-based, injectable
   design the repo follows (`internal/api/interfaces.go`).

## Platform impact

- **Migrations:** none. No schema, no API contract, no gitops values change.
- **Backward compatibility:** the `mctl_whoami` response text changes (first
  line shows the public URL instead of `http://localhost:<port>`, or is absent
  when no public URL is configured). It is human-facing prose returned as MCP
  text content — no machine parses it; no other tool, prompt
  (`internal/mcp/prompts.go`), or resource (`internal/mcp/resources.go`)
  consumes it. The stdio binary's output is unchanged. Tool count is unchanged,
  so `server_test.go`'s 74-tool expectation and `recordedHints` in
  `annotations_test.go` stay as they are.
- **Resource impact:** none — one extra string field per process and a URL parse
  per whoami call.
- **Risks + mitigations:**
  - *`SELF_URL` unset or wrong in a preview deployment* → the whoami line would
    name `https://api.mctl.ai` (the `envOr` default) from a preview. Mitigation:
    the value is the same one used as the OAuth issuer, so it is already wrong in
    a more consequential place if misconfigured; recorded as an open question
    for a gitops follow-up, not fixed here.
  - *Loopback `SELF_URL` in local dev* → line silently disappears. Mitigation:
    intentional and tested; documented in requirements' open questions.
  - *Regression by future edit* → the mutation-validated test (T1/T2 below)
    fails the moment `s.apiURL` returns to the message.
  - *Redaction helper misfiring* when `apiURL` is empty (a `NewServer("", "")`
    call in a test would make `strings.ReplaceAll` with an empty `old` insert the
    replacement between every character). Mitigation: guard
    `if s.apiURL == "" { return err.Error() }` in `redactUpstream`, covered by a
    unit test.
