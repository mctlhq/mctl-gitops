# Cloudflare MCP Portal compatibility spike: modern-protocol probe harness, pre-registered OAuth client path, and Phase A+B evidence matrix

## Context

Issue #585 is the `mctl-telegram`-side execution child of `mctlhq/.github#44`
(cross-layer Cloudflare MCP compatibility spike) under roadmap
`mctlhq/.github#35`. The `.github` repository is not an executable
`mctl-agents` service target, so the repository-specific work lands here. The
goal is to make `tg.mctl.ai` testable as the *upstream* behind a Cloudflare MCP
Server Portal on the modern MCP path, and to produce a repeatable, evidence-
bearing probe/report for the Phase A+B gate — not to re-run the direct
stateless-MCP work already owned by `mctl-telegram#568`.

Today the repository has no way to answer the questions `#44` asks. The MCP
handler is built with `mcpserver.NewStreamableHTTPServer` in
`internal/mcp/server.go:308` with no statelessness option, and three separate
call sites treat an `Mcp-Session-Id` as mandatory
(`cmd/canary/main.go:312-315`, `test/load/main.go:244-253`,
`cmd/local/e2e_cli_daemon_test.go:349`). The client protocol version is
hard-coded inconsistently — `2024-11-05` in `cmd/canary/main.go` versus
`2025-03-26` in the `README.md` quick-start curl — and nothing anywhere asserts
or records what the server negotiates back. On the OAuth side the pieces
Cloudflare needs already exist (RFC 9728 metadata at `cmd/server/main.go:367-368`,
the `WWW-Authenticate` `resource_metadata` hint at `internal/auth/middleware.go:29-33`,
mandatory PKCE-S256, RFC 8414 metadata at `internal/oauth/server.go:1103`), but
the only documented way to add a new redirect host is
`OAUTH_ALLOWED_IMPLICIT_HOSTS`, whose defaults are applied *only when the list
is empty* (`internal/oauth/server.go:534-535`, `internal/config/config.go:323`) —
so setting it for a Portal callback silently drops `claude.ai`, `claude.com`
and `chatgpt.com`. That is precisely the regression `#585` asks us to prevent.

This proposal is a spike: it adds observation, a safe pre-registered client
path, tests and documentation. It deliberately does **not** flip the transport
to stateless, because that is `#568`'s decision and changing it here would both
duplicate that issue and break the three existing session-dependent call sites.

## User stories

- AS a platform engineer running the `#44` Phase A+B gate I WANT a single
  repeatable command that probes an MCP endpoint and emits a structured report
  SO THAT the compatibility matrix is filled from measured evidence rather than
  from assumptions.
- AS a platform engineer I WANT the same harness to accept either
  `https://tg.mctl.ai/mcp` or a configured Portal URL through environment
  variables SO THAT the direct and Cloudflare rows of the matrix are produced by
  identical code and are comparable.
- AS an operator configuring the Cloudflare Portal PoC I WANT to pre-register
  the Portal's OAuth client and its exact callback URI through configuration SO
  THAT the Portal works without relying on RFC 7591 dynamic client registration
  continuing to exist.
- AS an operator I WANT adding the Portal callback to be strictly additive SO
  THAT existing `claude.ai` / `chatgpt.com` client redirects keep working.
- AS a security reviewer I WANT the probe output to contain no bearer tokens,
  no Telegram message bodies and no chat identifiers SO THAT reports can be
  attached to a public issue.
- AS the `#568` owner I WANT this spike to consume and cite direct-upstream
  behavior rather than re-assert it SO THAT the two issues do not diverge.
- AS a reviewer of the `#44` gate I WANT every step Cloudflare-only that cannot
  run in CI to be written down as a bounded operator procedure SO THAT no cell
  of the matrix is silently assumed green.

## Acceptance criteria (EARS)

### Probe harness

- WHEN the probe harness is invoked with a base URL, MCP path and bearer token
  supplied through environment variables THE SYSTEM SHALL perform, in order,
  protected-resource-metadata discovery, `initialize`, `server/discover`,
  `tools/list`, and exactly one read-only `tools/call`, recording the outcome of
  each step independently.
- WHEN `initialize` returns THE SYSTEM SHALL record the client-sent
  `protocolVersion`, the server-returned `protocolVersion`, and whether the two
  match.
- WHEN `initialize` returns THE SYSTEM SHALL record whether an `Mcp-Session-Id`
  response header was present, and its length only — never its value.
- WHEN the harness issues `tools/list` and `tools/call` THE SYSTEM SHALL first
  attempt them **without** any `Mcp-Session-Id` header and record whether the
  attempt succeeded, then retry with the minted session id if the session-free
  attempt failed, recording `session_required=true` in that case.
- WHEN the harness sends `Mcp-Method` and `Mcp-Name` request headers THE SYSTEM
  SHALL record whether the upstream echoed, ignored or rejected them.
- IF `server/discover` is answered with JSON-RPC error `-32601` (method not
  found) THEN THE SYSTEM SHALL record `unsupported` for that cell rather than
  failing the run.
- WHILE selecting the `tools/call` target THE SYSTEM SHALL use only a tool whose
  `tools/list` annotations report `readOnlyHint=true`, and SHALL abort the call
  step with an explicit error if the configured tool name does not carry that
  annotation.
- WHEN any HTTP response is `401` THE SYSTEM SHALL classify the failure from the
  status code and the `WWW-Authenticate` challenge parameters (including
  `resource_metadata`) without emitting the `Authorization` request header value.
- WHILE writing its report THE SYSTEM SHALL emit only status codes, protocol
  version strings, tool names, annotation flags, boolean observations, error
  codes and counts — and SHALL NOT emit bearer tokens, refresh tokens,
  authorization codes, Telegram message bodies, chat titles, peer identifiers or
  phone numbers.
- WHEN the harness runs THE SYSTEM SHALL emit both a machine-readable JSON
  report and a Markdown matrix row, labelled with an operator-supplied path
  label (`direct` or `portal`).
- IF no bearer token is configured THEN THE SYSTEM SHALL still run the
  unauthenticated steps (protected-resource metadata, authorization-server
  metadata, and the `401` classification of `initialize`) and mark the
  authenticated cells `skipped`.
- WHILE the harness is part of the repository THE SYSTEM SHALL contain no
  production credential, no production bearer token and no hard-coded Cloudflare
  hostname as a default.

### OAuth for a manual / pre-registered Cloudflare client

- WHEN a Cloudflare Portal OAuth client is configured as a pre-registered client
  with an exact `redirect_uri` THE SYSTEM SHALL accept its `/oauth/authorize`
  request through the registered-client exact-match branch of
  `validateClient` (`internal/oauth/server.go:2648`) without any call to
  `/oauth/register`.
- WHILE a Portal callback host is added to configuration THE SYSTEM SHALL
  continue to accept every redirect host that was accepted before the change,
  including the `claude.ai`, `claude.com`, `chatgpt.com`, `localhost` and
  `127.0.0.1` defaults.
- WHEN a pre-registered client presents a `redirect_uri` that differs from a
  registered one by so much as a path, query or port THE SYSTEM SHALL reject it.
- WHILE the Portal client is in use THE SYSTEM SHALL continue to require
  PKCE-S256 on the MCP-client leg and SHALL continue to reject `plain` or absent
  `code_challenge`.
- WHILE the Portal client is in use THE SYSTEM SHALL leave issuer, resource and
  audience validation of access tokens unchanged from the pre-change behavior,
  as demonstrated by an unchanged, passing existing test suite.
- WHEN the Portal is configured with `Require user auth=ON` and forwards a
  per-end-user access token THE SYSTEM SHALL resolve the Telegram principal from
  that token exactly as it does for a direct client, with no shared or admin
  principal substituted.
- IF a change would make correct operation depend on RFC 7591 dynamic client
  registration remaining available THEN THE SYSTEM SHALL NOT include that change.
- WHILE this proposal is implemented THE SYSTEM SHALL NOT hard-code
  `mcp-enterprise.mctl.ai`, or any other Cloudflare-provided callback host, in
  Go source; the host SHALL come from configuration and test fixtures SHALL use
  a synthetic host.

### Report artifact and bounded operator steps

- WHEN the direct row of the compatibility matrix is produced THE SYSTEM SHALL
  generate it from a CI-runnable test that drives the real MCP handler wired the
  way `cmd/server` wires it, so the recorded direct behavior cannot drift from
  the code.
- IF live Cloudflare Portal credentials or configuration are unavailable to the
  worker THEN THE SYSTEM SHALL mark the Portal cells `PENDING-OPERATOR` and
  SHALL document the exact, bounded, reproducible steps a human must run to fill
  them.
- WHILE the change is in review THE SYSTEM SHALL introduce no HTTP+SSE
  transport, no new dependence on `Mcp-Session-Id` or transport sticky sessions,
  and no adoption of Roots, Sampling, MCP Logging or DCR as new platform
  primitives.
- WHILE documenting Portal deployment THE SYSTEM SHALL record that MTProto
  client ownership remains per-pod (`internal/telegram/clientpool.go`, see
  `docs/hpa.md` "Sticky routing for multi-replica deployments") and that
  protocol-level statelessness does not authorise raising the replica count.

## Out of scope

- Flipping the `/mcp` transport to stateless Streamable HTTP, or changing the
  negotiated protocol version of the running server. That is `mctl-telegram#568`;
  this spike measures and reports what `#568` decides.
- Implementing MCP Tasks (`mctlhq/.github#41`).
- Implementing the Telegram MCP App (`mctl-telegram#569`).
- Enabling Cloudflare Gateway, DLP or Code Mode.
- Changing MTProto session ownership, the client pool, the Local Bridge
  connection model, or the replica count / HPA configuration.
- Removing or disabling `/oauth/register`; this proposal only stops *depending*
  on it.
- Changing the replace-semantics of the existing `OAUTH_ALLOWED_IMPLICIT_HOSTS`
  variable, which would be a breaking change for existing deployments.
- Making `mcp-enterprise.mctl.ai` the final tenant security perimeter.

## Open questions

- **The real Portal callback URI is unknown.** The issue names
  `https://mcp-enterprise.mctl.ai/servers-callback` as a preference, not a fact.
  Resolution taken: the callback is never baked into code; it is a configuration
  value, tests use a synthetic host, and the operator doc instructs the human to
  paste the URI Cloudflare actually displays.
- **Which MCP protocol version the running server negotiates is unverified.**
  `go.mod:14` pins `github.com/mark3labs/mcp-go v1.0.0`; nothing in the
  repository records the negotiated result, and the two in-repo clients disagree
  about what to send. Resolution taken: the harness treats the client version as
  configuration (defaulting to `2026-07-28`) and *records* the server's answer
  rather than asserting a value the spike has not yet observed.
- **Whether `server/discover`, `Mcp-Method` and `Mcp-Name` are implemented at
  all.** A repository-wide grep finds no reference to any of the three.
  Resolution taken: the harness probes them and records `unsupported` as a
  legitimate, non-failing outcome — establishing that baseline is the point of
  the spike.
- **Whether Cloudflare Portal forwards the end-user bearer token or its own.**
  This determines both per-user authorization and whether the JWT-`sub`-keyed
  consistent-hash routing described in `docs/hpa.md` survives behind the Portal.
  Resolution taken: recorded as a first-class risk, with a bounded operator step
  that observes the `sub` shape reaching the upstream for two distinct users.
- **Whether the probe should ship as a container image.** Resolution taken: no.
  It runs via `go run ./cmd/mcpprobe` in CI and from an operator shell, avoiding
  a new Dockerfile stage and a new image to keep patched.
