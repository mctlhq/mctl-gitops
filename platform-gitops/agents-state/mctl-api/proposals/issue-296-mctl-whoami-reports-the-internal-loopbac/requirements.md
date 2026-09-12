# mctl_whoami must report the public deployment URL, never the internal loopback address

## Context

`mctl_whoami` is the first tool every MCP client calls to confirm *which* mctl
deployment it is talking to. Today its first line is built from `s.apiURL`
(`internal/mcp/server.go:212`), which is the upstream base URL the MCP server
uses to call the REST API back over loopback — not the address the caller
reached. In the in-process server that serves every production caller,
`cmd/api/main.go:307` constructs it as
`mctlmcp.NewServer("http://localhost:"+cfg.Port, "")`, so the printed value is
always `http://localhost:<port>`, regardless of how the request arrived
(direct connector, Cloudflare MCP portal at `https://mcp.mctl.ai/mcp`, or a
preview). Verified end to end on 2026-09-12 in production through the ChatGPT
app. Only the standalone stdio binary (`cmd/mcp/main.go`, `MCTL_API_URL`) prints
something meaningful, and that binary does not serve `api.mctl.ai`.

The identity fields below the first line (user, admin, teams, namespaces) are
correct and must stay byte-identical. The fix is to source the displayed URL
from the deployment's public base URL — the same value that
`auth.OAuthServer.BaseURL` carries ("the public base URL of this server, e.g.
`https://api.mctl.ai`", `internal/auth/oauth_server.go:48`), fed from
`cfg.SelfURL` in `cmd/api/main.go:117` — and to omit the line entirely when no
trustworthy public URL is configured. A second, less visible leak shares the
same root cause: when the upstream call fails, the whoami handler returns
`Failed to get identity: request failed: Get "http://localhost:8080/api/v1/whoami": ...`
(`internal/mcp/server.go:201` over `doRequest`, `internal/mcp/server.go:2466`),
which puts the loopback address back in the user-visible response.

## User stories

- AS an MCP client user with several mctl connectors (portal aggregate, direct
  connector, preview) I WANT `mctl_whoami` to name the deployment I am
  authenticated to SO THAT I can tell those connectors apart before running a
  write operation.
- AS a platform operator I WANT the tool response to never expose the server's
  internal upstream address SO THAT the output is meaningful to callers and
  leaks no deployment-internal topology.
- AS a maintainer I WANT a test that drives `mctl_whoami` through the same
  construction path `cmd/api` uses SO THAT reintroducing `s.apiURL` into the
  message fails CI instead of shipping.

## Acceptance criteria (EARS)

- WHEN a client calls `mctl_whoami` against a server built by the in-process
  (`cmd/api`) construction path THE SYSTEM SHALL return a response containing
  no `localhost`, no `127.0.0.1`, and no `::1`, for any value of `PORT`.
- WHEN a public base URL is configured and is not a loopback address THE SYSTEM
  SHALL render the first line as `Authenticated to <public base URL>`, where the
  public base URL is the value `cmd/api` passes to `auth.NewOAuthServer`
  (`cfg.SelfURL`), i.e. the OAuth issuer the caller authenticated against.
- IF no public base URL is configured, or the configured value has a loopback
  host, THEN THE SYSTEM SHALL omit the `Authenticated to ...` line and its
  following blank line, returning only the identity block.
- WHILE serving any request THE SYSTEM SHALL keep the identity fields of the
  response unchanged in wording, order, and formatting: `User:`, `Admin:`,
  `Teams:`, `Accessible namespaces:`, with the same values sourced from
  `GET /api/v1/whoami`.
- IF the upstream `GET /api/v1/whoami` call fails (transport error or non-2xx)
  THEN THE SYSTEM SHALL return an error result that names no loopback address
  and no internal upstream URL, while the full underlying error remains
  available to operators via server-side `slog` logging.
- WHEN the standalone stdio binary (`cmd/mcp/main.go`) is used with
  `MCTL_API_URL=https://api.mctl.ai` THE SYSTEM SHALL keep printing that URL, so
  today's only correct configuration does not regress.
- WHEN the test suite runs THE SYSTEM SHALL fail if the whoami message is
  reverted to formatting `s.apiURL` (mutation check), rather than merely
  asserting that some string was produced.
- WHILE the OAuth server is enabled THE SYSTEM SHALL source the URL shown by
  `mctl_whoami` from the same object that carries the OAuth issuer
  (`auth.OAuthServer.BaseURL`), so the displayed URL and the issuer a caller's
  token was verified against cannot name different deployments.
- WHEN the test suite runs THE SYSTEM SHALL fail if `cmd/api` is rewired to pass
  any value other than the enabled OAuth server's `BaseURL` into the MCP
  server's public URL — passing `cfg.SelfURL` a second time, independently, is
  not sufficient, because nothing then fails when the two diverge.

## Out of scope

- The hard-coded `serverInfo.version` `"0.1.0"` in
  `internal/mcp/server.go:78` — explicitly excluded by the issue.
- Redacting the upstream URL from the error paths of the other ~73 tools
  (`internal/mcp/server.go` handlers all wrap `apiGet`/`apiPost` errors the same
  way). Only `mctl_whoami` is in scope; a follow-up can widen the helper.
- Deriving the displayed URL per request from `Host`/`X-Forwarded-Host` headers.
- Changing `SELF_URL` defaults, Helm values, or any deployment configuration in
  `platform-gitops`.
- Any change to `/api/v1/whoami` REST response shape (`internal/api`), to the
  OAuth server, or to the MCP transport/statelessness contract
  (`internal/mcp/stateless_test.go`).

## Open questions

- Local development sets `SELF_URL` to a loopback URL in some setups; under the
  rule above such a deployment shows no `Authenticated to` line at all. That is
  accepted deliberately (the invariant "never print a loopback address" wins
  over "always print a line"); flag during review if operators would rather see
  the loopback value locally.
- `SELF_URL` is not currently set in `helm/` (the chart passes `.Values.env`
  through, `helm/templates/deployment.yaml:39`), so production relies on the
  `envOr("SELF_URL", "https://api.mctl.ai")` default in `cmd/api/main.go:617`.
  That default is correct for `api.mctl.ai`, but a preview deployment would
  advertise the production URL unless its values set `SELF_URL`. Out of scope to
  fix here; worth a gitops follow-up.
