# Troubleshooting page for the error families clients actually hit

## Context

`docs/` today carries an alert-driven operational runbook (`docs/runbook.md`,
2312 lines, one section per alert rule), an SLO page (`docs/slo.md`) and the
Local Bridge guide set (`docs/local-bridge.md` plus `docs/local-bridge/*.md`).
None of them answer the question a client or an LLM agent actually asks: "the
tool returned this string, what do I do now". Issue #669 reports a 30-day pass
over production `audit_logs` in which almost every non-ok row falls into eight
families, and roughly 70 % of them are the peer family — an agent passing a
bare `channel:<id>` that carries no access hash.

The friendly text already exists in three separate places: the MTProto catalog
added by #70 (`internal/mcp/errorcatalog.go`), the session sentinels
(`sessionErrText` in `internal/mcp/tools.go`), and hand-written fallbacks in
`internal/telegram/messages.go` and `internal/telegram/media_download.go`.
Several families never reach a tool response at all — send-code `FLOOD_WAIT`,
the exhausted login budget and `invalid_redirect_uri` are log-only events in
`internal/oauth/enable_access.go` and `internal/oauth/server.go`. This proposal
adds one page, `docs/troubleshooting.md`, that covers all eight families, links
it from `README.md`, `docs/runbook.md` and `docs/public/llms.txt`, and adds
tests that fail when the page and the source strings drift apart. It also
tightens the peer-family catalog text, which today names the accepted id forms
but never tells the caller to get the id from `list_dialogs`.

## User stories

- AS an LLM agent driving the MCP tools I WANT a single document that maps the
  exact error string I received to the next call I should make SO THAT I
  recover on the next turn instead of retrying the same failing call.
- AS a connector user I WANT to know whether `AUTH_KEY_UNREGISTERED` or
  `JWT expired` is something I can fix SO THAT I reconnect when reconnecting is
  the remedy and wait when waiting is.
- AS an operator on call I WANT to know which families have no server-side
  remedy SO THAT I do not spend an incident looking for one.
- AS a client developer registering an OAuth client I WANT the redirect-URI
  rules stated up front SO THAT I do not discover at `/oauth/register` that a
  `cursor://` scheme is refused.
- AS a maintainer I WANT CI to fail when the doc quotes a catalog string that
  no longer exists SO THAT the page cannot rot into a lie.

## Acceptance criteria (EARS)

- WHEN the repository is checked out THE SYSTEM SHALL contain
  `docs/troubleshooting.md` with one section per family: peer id
  (`PEER_ID_INVALID` / `CHANNEL_INVALID` / `CHAT_ID_INVALID`), `get_media`
  confirmation, send-code `FLOOD_WAIT`, `AUTH_KEY_UNREGISTERED`, exhausted
  login budget, `JWT expired`, `invalid_redirect_uri`, and `RPC_CALL_FAIL`.
- WHILE `docs/troubleshooting.md` exists THE SYSTEM SHALL give every family
  section the same four subsections in the same order: Symptom, Cause, What the
  client or agent should do, What the operator can do.
- WHEN `docs/troubleshooting.md` quotes a string produced by
  `mtprotoErrCatalog` or `mtprotoTransientCatalog` in
  `internal/mcp/errorcatalog.go` THE SYSTEM SHALL mark that quote with an HTML
  comment naming the MTProto code, and a test in package `mcp` SHALL fail if
  the named code is absent from either map or if its `message` (and non-empty
  `action`) does not appear verbatim in the page.
- WHEN a code is present in `mtprotoErrCatalog` or `mtprotoTransientCatalog`
  but deliberately not documented THE SYSTEM SHALL list it in an explicit
  in-test allowlist, so that adding a catalog entry without either documenting
  it or allowlisting it fails the build.
- WHEN `docs/troubleshooting.md` quotes the session text for a revoked session
  THE SYSTEM SHALL quote exactly what `sessionErrText(db.ErrSessionRevoked)`
  returns, asserted by calling that function from the test rather than by
  copying its literal.
- WHEN `docs/troubleshooting.md` states the confirmation lifetime THE SYSTEM
  SHALL render the value of `mcp.ConfirmationTTL` (`internal/mcp/confirm.go`,
  10 minutes today) and a test SHALL fail if the constant changes without the
  page changing.
- WHEN `docs/troubleshooting.md` states the redirect-URI scheme rule THE SYSTEM
  SHALL quote the error text `validateRedirectURIShape`
  (`internal/oauth/server.go`) returns for a custom scheme, asserted by a test
  in package `oauth` that calls the function with a `cursor://` URI.
- WHEN the documentation link tests run THE SYSTEM SHALL fail unless
  `README.md`, `docs/runbook.md` and `docs/public/llms.txt` each reference the
  troubleshooting page, and unless `docs/runbook.md` lists it in its table of
  contents.
- IF an agent receives a peer error from `internal/mcp/errorcatalog.go` THEN
  THE SYSTEM SHALL tell it to call `list_dialogs` and pass an id exactly as
  returned there, matching the wording already produced by
  `internal/telegram/messages.go` and `internal/telegram/media_download.go`.
- WHEN `mtprotoErrCatalog` is extended with `CHANNEL_INVALID` and
  `CHAT_ID_INVALID` THE SYSTEM SHALL keep the rendered text free of the raw
  MTProto code, so the existing `TestMtprotoErrResultCatalog` invariant in
  `internal/mcp/errorcatalog_test.go` continues to hold.
- WHILE the page describes a family whose text never reaches a tool response
  (send-code `FLOOD_WAIT`, exhausted login budget, `invalid_redirect_uri`) THE
  SYSTEM SHALL say so explicitly and name the log line or endpoint where the
  evidence is found.
- IF a reader follows the page for `AUTH_KEY_UNREGISTERED` THEN THE SYSTEM
  SHALL state that there is no server-side remedy and that the client must
  reconnect at `tg.mctl.ai/telegram/connect`.

## Out of scope

- Rendering `docs/troubleshooting.md` on the public site at
  `/docs/troubleshooting`. The Local Bridge pages reach the site only because
  the markdown is duplicated into `internal/web/` (`go:embed` cannot reach
  outside its package) and kept honest by
  `TestLocalBridgeMarkdownMatchesDocs`. Adding a ninth copied file is a
  separate change; this proposal links to the file on GitHub.
- Changing any tool's behaviour, schema, or retry policy. Only the two peer
  catalog entries and the new/edited catalog text change in Go.
- Fixing `invalid_redirect_uri` for `cursor://` clients. The decision to refuse
  custom schemes is tracked in #668; this page documents the current rule.
- Adding new metrics, alert rules or dashboards.
- Translating the page or adding a per-client (Claude / ChatGPT / Cursor)
  variant.

## Open questions

- The issue says the login budget is 30 minutes; the code default is
  `OAUTH_CODE_TTL = 10 * time.Minute` (`internal/config/config.go`), which
  bounds the background login goroutine in `internal/oauth/enable_access.go`.
  Production may set a longer value. Resolution taken: the page names the
  `OAUTH_CODE_TTL` env var and the 90-second per-step handler wait
  (`enableSendCodeWait`) rather than hardcoding "30 minutes", and states the
  default.
- `CHAT_ID_INVALID` appears in the issue's table but in no Go file in the
  clone; `CHANNEL_INVALID` appears only in
  `internal/telegram/messages.go` and `internal/telegram/media_download.go`,
  not in the catalog. Resolution taken: add both to `mtprotoErrCatalog` with
  peer-family wording, and document them together with `PEER_ID_INVALID`.
- `floodWaitSeconds` in `internal/mcp/errorcatalog.go` handles `FLOOD_WAIT_N`
  and `SLOWMODE_WAIT_N`, while `telegram.FloodWaitSeconds`
  (`internal/telegram/floodwait.go`) also handles `FLOOD_PREMIUM_WAIT_N`. A
  premium flood wait therefore falls through to the generic handler. Not fixed
  here; recorded in the page and flagged for a follow-up issue.
- Whether the hosted docs page (`internal/web/docs.html`) should also link the
  troubleshooting page. Resolution taken: add the link there too if it is a
  one-line change, otherwise leave it to the site-rendering follow-up.
