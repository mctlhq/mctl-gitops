# Design: issue-585-spike-cloudflare-mcp-execute-44-protocol

## Current state

### The `/mcp` endpoint and its middleware chain

`/mcp` is mounted in `cmd/server/main.go:559-571` at a configurable path
(`cfg.MCPPath`, env `MCP_PATH`, default `/mcp` — `internal/config/config.go:25,226`).
Outermost first, a request passes:

1. chi globals — `RequestID`, `RealIP`, metrics, `Recoverer`, `Timeout(60s)`
   (`cmd/server/main.go:341-350`);
2. `web.BrowserRedirect` (`internal/web/landing.go:113-137`) — a GET whose
   `Accept` contains `text/html` and neither `application/json` nor
   `text/event-stream` gets a 303 to `/`, **before** auth;
3. `web.OriginGuard` (`internal/web/origin.go:22-37`) — DNS-rebinding guard;
   absent `Origin` passes, mismatched `Origin` is 403;
4. `auth.Middleware` (`internal/auth/middleware.go:78-118`) — on 401 it emits
   `WWW-Authenticate: Bearer realm="mctl-telegram", resource_metadata="<base>/.well-known/oauth-protected-resource/mcp"`
   (`:26-39`, `:100`, `:108`) and injects `*auth.Identity` into the context;
5. `limiter.Middleware` (`internal/audit/ratelimit.go:132-155`) — per-identity
   token bucket keyed on `id.Subject`;
6. `mcpSrv.HTTPHandler()`.

`HTTPHandler` (`internal/mcp/server.go:177-314`) registers 30 tools and returns
`mcpserver.NewStreamableHTTPServer(srv, mcpserver.WithHTTPContextFunc(...))`
(`:308-313`). Three facts follow directly from that call:

- **`WithStateLess` is never passed.** The endpoint runs `mcp-go v1.0.0`'s
  default in-memory session manager: `initialize` mints an `Mcp-Session-Id` and
  later calls are expected to carry it. Three in-repo clients encode that
  assumption — `cmd/canary/main.go:312-316` treats a missing header as a hard
  error, `test/load/main.go:252-253,272` documents that "the Streamable HTTP
  transport rejects `tools/call` without a valid `Mcp-Session-Id`", and
  `cmd/local/e2e_cli_daemon_test.go:290-370` does init-then-call.
- **The context func is a no-op** (`:310-312`, it returns `r.Context()`
  unchanged). No request header — including a hypothetical `Mcp-Method` or
  `Mcp-Name` — is reachable from any tool handler.
- **No protocol version is declared anywhere in this repository.**
  `NewMCPServer` (`:182-186`) receives only a name, the *software* version
  string and `WithToolCapabilities(true)`. There is no `MCP-Protocol-Version`
  header handling, no `2025-06-18`, no `2026-07-28`. The repo's own clients
  disagree with its docs: `cmd/canary/main.go:283` and `test/load/main.go:219`
  send `2024-11-05`, while `README.md:66` and `internal/web/docs.html:254`
  tell users `2025-03-26`. Nothing asserts what the server answers.

`server/discover`, `tools/list`, `Mcp-Method` and `Mcp-Name` have zero hits
repo-wide; `initialize` and `tools/list` are entirely `mcp-go` internals. The
only discovery-shaping code is registration-time filtering: `toolPassesFilter`
(`internal/mcp/server.go:160-175`) with `TOOL_FILTER=read-only` registers only
tools whose `Annotations.ReadOnlyHint` is true, wired at
`cmd/server/main.go:447` and guarded by `internal/mcp/annotations_test.go:65-98`.

Eleven tools are read-only. `get_my_send_status` (`internal/mcp/tools.go:859-865`,
`readOnly=true`, `destructive=false`, `openWorld=false`) returns only booleans
(`can_send`, `reason`, `server_allow_send`, `has_send_scope`, `send_enabled`,
`connected`) and touches no peer — the one tool that can be called in a probe
without any risk of emitting Telegram content.

### Existing probe precedent

`cmd/canary` is the closest thing to a harness: env-configured
(`CANARY_BASE_URL`, `CANARY_BEARER_TOKEN`, `CANARY_MCP_PATH`,
`CANARY_PROBE_UNREAD`, `cmd/canary/main.go:59-100`), `slog` JSON output, and a
four-step run — `probeOAuthMetadata` (`:184`) → `initMCPSession` (`:275`) →
`probeMCPTool("list_dialogs")` (`:509`) → optional `get_unread_messages`. It is
an **alerting** probe: it pushes `mctl_telegram_canary_success` to a Pushgateway,
is deployed as a CronJob from `mctl-gitops`, and pages through
`docs/runbooks/canary.md`. `test/load/main.go` is a load generator built on the
same JSON-RPC plumbing, duplicated. `cmd/local/e2e_cli_daemon_test.go:123-137`
is the only in-process test that actually mounts `/mcp` on a chi router and
speaks real JSON-RPC over `httptest`. No `scripts/` directory exists, "conformance"
has zero hits, and `.github/workflows/` has no MCP protocol job.

### OAuth surface

Everything Cloudflare needs for discovery already ships:

- RFC 8414 metadata at `/.well-known/oauth-authorization-server`
  (`internal/oauth/server.go:1103`, `:1152+`), advertising
  `registration_endpoint` (`:1159`);
- RFC 9728 protected-resource metadata at both
  `/.well-known/oauth-protected-resource` and its `+MCPPath` alias
  (`cmd/server/main.go:367-368`, `:1007-1042`, covered by
  `cmd/server/protected_resource_test.go`);
- the `resource_metadata` challenge hint on 401 (`internal/auth/middleware.go:29-33`);
- mandatory PKCE-S256 on the MCP-client leg, constant-time `pkceVerify`
  (`internal/oauth/server.go`, `SECURITY.md:61`), single-use 10-minute codes
  bound to (`client_id`, `redirect_uri`, `code_challenge`).

Redirect acceptance has exactly two branches, both in `validateClient`
(`internal/oauth/server.go:2648-2690`):

- **registered client** — DB lookup (`GetClientReg`) or the in-memory
  `s.clients` map; the supplied `redirect_uri` must **exactly equal** a
  registered one. The DB-miss path deliberately falls through to the in-memory
  map so pre-registered built-ins are recognised (`:2660-2668`);
- **implicit client** (only when `AllowImplicitClient`) —
  `validateImplicitRedirectURI` (`:2570-2618`): no backslash, no userinfo,
  `https` only except loopback, then a hostname match against
  `cfg.AllowedImplicitHosts` (bare entry matches any port; `host:port` entry
  requires an exact match), with loopback always accepted. The same function is
  applied to every `redirect_uri` at RFC 7591 registration (`:2452`), so DCR
  cannot smuggle a host past the list.

`AllowedImplicitHosts` defaults to `claude.ai, claude.com, chatgpt.com,
localhost, 127.0.0.1` **only when the configured list is empty**
(`internal/oauth/server.go:534-535`); the env var is parsed by `parseStringCSV`
at `internal/config/config.go:323` and `SECURITY.md:65` states plainly that
"setting it replaces that default rather than extending it".

`ConnectClientID = "mctl_self_connect"` (`internal/oauth/server.go:720-722`) is
the existing precedent for a pre-registered, non-DCR client: it is seeded
directly into `s.clients` at `:671` with its own redirect URIs and never touches
`/oauth/register`. `/oauth/register` itself is unauthenticated and defended only
by a rate limiter and body cap (`:2379`, `:330`, `:341`).

### The affinity constraint a Portal must not break

`internal/telegram/clientpool.go` keeps a **per-process** `user_id → *telegram.Client`
map. `docs/hpa.md` ("Sticky routing for multi-replica deployments") specifies
Layer-1 ingress consistent-hash routing keyed on the JWT `sub` claim
(`tg:<telegram_id>`) extracted into `X-Mctl-Route-Key`, precisely so a user does
not open a new MTProto session — and trigger a Telegram "New login" notification
— on every replica. If a Cloudflare Portal presents one shared token upstream
instead of forwarding the end-user's, every request collapses onto a single
`sub`, the hash ring degenerates to one pod, and per-user authorization is lost.
This is the single most important thing the spike must measure, and it is not
observable from the OAuth code alone.

## Proposed solution

The spike is **additive and observational**. It does not change the transport,
the negotiated protocol version, the replica count, or any existing default.

### 1. `internal/mcpprobe` — one probe library, one binary

Add `internal/mcpprobe/` holding the JSON-RPC/Streamable-HTTP plumbing that
`cmd/canary` and `test/load` currently duplicate, plus the new observations, and
`cmd/mcpprobe/` as a thin env-configured `main` in the style of `cmd/canary`
(`MCPPROBE_BASE_URL`, `MCPPROBE_MCP_PATH`, `MCPPROBE_BEARER_TOKEN`,
`MCPPROBE_PROTOCOL_VERSION` defaulting to `2026-07-28`, `MCPPROBE_LABEL`,
`MCPPROBE_TOOL` defaulting to `get_my_send_status`, `MCPPROBE_TIMEOUT`,
`MCPPROBE_OUT`). No flag or default may carry a credential or a Cloudflare
hostname.

A run produces one `Report` struct with a per-step result:

| step | recorded |
|---|---|
| `prm` | status of `/.well-known/oauth-protected-resource{,+path}`, `resource`, `authorization_servers` |
| `as_metadata` | status, `issuer`, endpoints present |
| `unauth_probe` | status of a token-less `initialize`, parsed `WWW-Authenticate` params incl. `resource_metadata` |
| `initialize` | client `protocolVersion` sent, server `protocolVersion` returned, match boolean, `serverInfo.name/version`, capabilities keys |
| `session` | `mcp_session_id_present`, its **length only**, and `session_required` |
| `discover` | `server/discover` result, or `unsupported` on JSON-RPC `-32601` |
| `tools_list` | tool names and their `readOnlyHint` / `destructiveHint` / `openWorldHint` flags |
| `tools_call` | the one read-only call: JSON-RPC ok/error code, `isError`, structured-content key names — never values |
| `mcp_headers` | whether `Mcp-Method` / `Mcp-Name` request headers were echoed, ignored or rejected |

The **statelessness discipline is inverted relative to `cmd/canary`**: the probe
issues `tools/list` and `tools/call` *without* a session header first and only
retries with the minted id if that fails, setting `session_required=true`. That
is what makes the harness usable against a future stateless upstream and against
a Portal that will not replay a session header, and it is why it must not simply
reuse `initMCPSession`'s mandatory-header contract.

Two safety rails are structural, not documentary. First, the probe reads
`tools/list` before calling anything and refuses to `tools/call` a tool whose
`readOnlyHint` is not true — so a misconfigured `MCPPROBE_TOOL` cannot send a
Telegram message. Second, the report type carries only scalars, booleans, status
codes, error codes, names and counts; there is no field into which a token,
message body, chat title or peer id can be placed. Logging goes through the
existing `slog` redaction handler (`internal/audit/redact.go`).

`cmd/canary` is refactored to call `internal/mcpprobe` for its JSON-RPC plumbing
so the `2024-11-05` / `2025-03-26` split stops being two independent truths, but
its own behavior — mandatory session, Pushgateway metrics, `list_dialogs` — is
left exactly as-is. Changing a paging probe inside a spike is how the spike
becomes an incident.

### 2. Direct-row evidence is generated by CI, not written by hand

Add `internal/mcpprobe/integration_test.go`: stand up an `httptest` server
mounting `mcp.New(...).HTTPHandler()` behind the same chain `cmd/server` uses,
following the existing pattern at `cmd/local/e2e_cli_daemon_test.go:123-137`,
run the probe against it, and assert the report is *well-formed* — not that the
protocol version equals a particular string. The test writes the direct row of
the matrix as a golden artifact. When `#568` flips the transport, this test's
golden output changes, which is the intended signal: the matrix cannot silently
drift from the code.

Unit tests use `httptest` fakes for the four upstream shapes the Portal work
cares about: stateful (mints a session, rejects session-free calls), stateless
(no session header, accepts calls directly), `401` with a full
`WWW-Authenticate` challenge, and `server/discover` answering `-32601`.

### 3. OAuth: a pre-registered Portal client, no new DCR dependence

Cloudflare's supported path is a manually configured OAuth client, and the issue
forbids adding reliance on RFC 7591. The design therefore routes the Portal
through the **registered-client exact-match branch** of `validateClient`, which
already exists and is the stricter of the two:

- add `OAUTH_PREREGISTERED_CLIENTS` to `internal/config` — a parsed list of
  `client_id` plus one or more exact `redirect_uris` — and seed it into
  `s.clients` in `cmd/server/main.go` immediately next to the existing
  `ConnectClientID` seeding at `internal/oauth/server.go:671`, reusing the same
  `clientReg` shape. Unset, behavior is byte-for-byte today's.
- The Portal client consequently never calls `/oauth/register`, never enters the
  implicit-host branch, and gets exact-match redirect validation including path,
  query and port.

Separately, to defuse the documented footgun, add `OAUTH_EXTRA_IMPLICIT_HOSTS`,
parsed with the same `parseStringCSV` and **appended** to whatever
`AllowedImplicitHosts` resolves to (including the built-in defaults) rather than
replacing it. `OAUTH_ALLOWED_IMPLICIT_HOSTS` keeps its existing replace
semantics — changing them would be a breaking change for current deployments and
is out of scope — but an operator adding a Portal host now has an additive knob
and a test that proves `claude.ai` and `chatgpt.com` survive. No Cloudflare
hostname appears in Go source; tests use a synthetic `portal.example.test`.

Issuer, resource, audience, PKCE and scope logic are **not touched**. The
evidence that they are unchanged is the existing suite continuing to pass, which
tasks.md makes an explicit gate.

### 4. `docs/cloudflare-portal-compat.md`

One document holding: the exact mctl-side configuration contract (which env vars
to set, with the callback URI pasted from what Cloudflare actually displays and
`Require user auth=ON` called out as mandatory); the Phase A+B matrix with the
direct row filled from the CI artifact and Portal cells marked
`PENDING-OPERATOR`; the bounded operator procedure for each pending cell,
including the two-user check that the `sub` reaching the upstream differs per
end user; and the `docs/hpa.md` affinity caveat stated as a Portal-specific risk
with its Telegram "New login" consequence.

## Alternatives

**Extend `cmd/canary` in place.** Cheapest in lines. Dropped: the canary is an
SLO/paging probe deployed as a CronJob from `mctl-gitops` with alert rules and a
runbook (`docs/runbooks/canary.md`). Teaching it to probe a Cloudflare Portal
would make an on-call page depend on Cloudflare's availability and on
exploratory, deliberately-failing steps like `server/discover`. Separate binary,
shared library, is the right split — and the library extraction still removes
the duplication between `cmd/canary` and `test/load`.

**A shell/curl script plus fixtures.** Fast to write and matches the `README.md`
smoke test. Dropped: it cannot reuse the `slog` redaction handler, gives no
structural guarantee that a token or a chat title stays out of the report,
cannot be run by `go test` in CI, and the repository's established idiom for
probing this endpoint is already a Go binary.

**Flip the transport to stateless now, then probe.** Would answer the `#44`
questions in their final form. Dropped on three grounds: it duplicates
`mctl-telegram#568`, which owns that decision; it changes production semantics
inside a spike; and it would break `cmd/canary`, `test/load` and
`cmd/local/e2e_cli_daemon_test.go`, all of which currently require a minted
session. The probe is built so that when `#568` lands, the same command produces
the updated row with no change.

**Register the Portal via RFC 7591 DCR.** Zero new configuration — Cloudflare
would self-register. Dropped: the issue explicitly forbids new DCR dependence,
`/oauth/register` is unauthenticated (`internal/oauth/server.go:2379`), and DCR
would land the Portal in the implicit-host branch, which is looser than exact
redirect matching for a long-lived enterprise client.

## Platform impact

**Migrations.** None. The pre-registered client is seeded into the in-memory
`s.clients` map exactly as `ConnectClientID` already is; no schema change, no
`internal/db` migration.

**Backward compatibility.** Every new configuration value is optional and
defaults to today's behavior. `OAUTH_ALLOWED_IMPLICIT_HOSTS` semantics are
unchanged. `cmd/canary`'s runtime behavior, metrics and env contract are
unchanged; only its internal plumbing moves to the shared package, so
`docs/runbooks/canary.md` stays correct. No route, middleware or tool is added,
removed or reordered on `/mcp`.

**Resource impact.** One new binary built by `go build ./...`. It is not added
to `Dockerfile` and ships no image — it runs from `go run ./cmd/mcpprobe` in CI
and from an operator shell. The CI integration test is in-process and adds
seconds.

**Risks and mitigations.**

- *A probe token leaks into a public report.* The report type has no field that
  can hold one; logging goes through `internal/audit/redact.go`; a test asserts
  the serialized report never contains the fixture token string.
- *The probe sends a real Telegram message.* Prevented structurally by the
  `readOnlyHint` precondition read from `tools/list`, with `get_my_send_status`
  as the default target — a tool that returns booleans and touches no peer. The
  send path additionally remains behind its own triple gate (`ALLOW_SEND`,
  scope, per-account `send_enabled`).
- *Adding a Portal host silently drops `claude.ai`.* This is a live hazard today
  (`internal/oauth/server.go:534-535`). Mitigated by the additive
  `OAUTH_EXTRA_IMPLICIT_HOSTS` var, by routing the Portal through the
  pre-registered-client path where the implicit list is not consulted at all,
  and by a regression test asserting the union.
- *The Portal presents a shared principal upstream, collapsing per-user auth and
  the `sub`-keyed hash ring.* Cannot be settled in CI. Recorded as the headline
  Portal risk with a bounded two-user operator check, and stated in the doc
  alongside the `docs/hpa.md` "New login" consequence.
- *A Portal-shaped guess gets baked in.* No Cloudflare hostname in Go source;
  configuration and synthetic test fixtures only.
- *The spike is mistaken for `#568` being done.* The matrix marks
  `session_required` and the negotiated protocol version as *observations of
  current behavior*, and the doc states that changing them is `#568`'s work.
