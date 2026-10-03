# Design: issue-669-docs-troubleshooting-page-for-the-error

## Current state

### Where error text is produced today

There is no single source of user-facing error text. Four distinct producers
exist, and the eight families in the issue are split across them:

1. **The MTProto catalog**, `internal/mcp/errorcatalog.go`.
   `mtprotoErrCatalog` maps 12 MTProto codes to a `{message, action}` pair;
   `mtprotoTransientCatalog` holds one entry (`PEER_FLOOD`) that renders as a
   JSON `RISK_GATED` envelope with `retry_after_seconds`. `floodWaitSeconds`
   parses `FLOOD_WAIT_N` / `SLOWMODE_WAIT_N` and renders a JSON envelope
   `{error, message, retry_after_seconds, action}`. `mtprotoErrResult` is the
   entry point; it returns `nil` for unknown codes, so `RPC_CALL_FAIL` falls
   through to the caller's generic handler.
   The peer entry reads: `"The peer ID is not valid for this account. Use
   @username, user:<id>, chat:<id>, or channel:<id>."` with action `"Check the
   peer argument and retry."`. It names the accepted *forms* but never says
   where to obtain a usable id, which is the substance of the issue's closing
   remark. `CHANNEL_INVALID` and `CHAT_ID_INVALID` are not in the map at all.

2. **Session sentinels**, `sessionErrText` in `internal/mcp/tools.go` (~line
   2012), reached through `borrowErrResult`. `AUTH_KEY_UNREGISTERED` is one of
   the `revokedSessionCodes` in `internal/telegram/clientpool.go`, which
   `sessionErrFor` maps to `db.ErrSessionRevoked`, which `sessionErrText`
   renders as "Your Telegram session is no longer valid — it was signed out
   from another device, or the account is unavailable. Reconnect the connector
   to sign in again." Note `clientpool.go` classifies the same codes a second
   time at startup (`Borrow`, ~line 215) because `client.Run` can fail before
   the ready callback fires.

3. **Hand-written fallbacks in the telegram package.**
   `internal/telegram/messages.go:587` and `:616`, and
   `internal/telegram/media_download.go:69`, already emit the correct advice —
   "call list_dialogs first and pass an id exactly as it appears there (e.g.
   `channel:<id>`)". `messages.go` even evicts the peer cache and retries once
   on `PEER_ID_INVALID` / `CHANNEL_INVALID` before giving up. These strings are
   wrapped with `fmt.Errorf` and surface through the generic `toolErr` path, so
   an agent sees a *different* peer message depending on which internal path
   failed. That divergence is the most plausible explanation for the issue's
   observation that "the hint is either not reaching the agent or not specific
   enough".

4. **OAuth and onboarding, log-only.** `internal/oauth/enable_access.go` runs
   the login on a background goroutine bounded by `cfg.CodeTTL`
   (`OAUTH_CODE_TTL`, default `10m` in `internal/config/config.go:312`) while
   the HTTP handler abandons its wait after `enableSendCodeWait = 90s`. The
   real cause — send-code `FLOOD_WAIT`, a DC dial failure, or the deadline —
   is only ever written to the `"enable: telegram login failed"` slog line
   (~line 163). `invalid_redirect_uri` is written by
   `internal/oauth/server.go:2630`/`:2643`; the scheme rule itself lives in
   `validateRedirectURIShape` (~line 2787): no backslash, no userinfo, `https`
   only except `http` on the three RFC 8252 loopback hosts accepted by
   `isLoopbackHost` (`localhost`, `127.0.0.1`, `::1`). A `cursor://` redirect
   is refused there, exactly as #668 records.

`JWT expired` is a literal in two places — `internal/auth/localjwt/issuer.go:167`
and `internal/auth/sharedhmac/verifier.go:238` — and is classified into the
`jwt_expired` reason label by `classifyAuthError` in
`internal/auth/middleware.go:130`, which already feeds the `JwtFailures`
runbook section.

`get_media`'s confirmation family is in `internal/mcp/confirm.go`
(`ConfirmationTTL = 10 * time.Minute`, `ErrConfirmationNotFound =
"confirmation not found, expired, or already used"`) and
`internal/mcp/media_tools.go`, which returns four distinguishable strings:
not-found/expired/used, issued-for-a-different-pair, belongs-to-another-
identity, and download-already-in-progress. The doc must quote the
`media_tools.go` strings, which differ from the sentinel by one word
(`confirmation_id` vs `confirmation`).

### Where docs live and how they are kept honest

`docs/` is a plain markdown directory with a Go test package attached:
`docs/doc.go` declares `package docs` and `docs/runbook_test.go` reads
`runbook.md` plus `../internal/metrics/metrics.go` and fails when the runbook
names a metric the registry never registers, or drops one of seven required
`id="..."` anchors. That is the established pattern for doc/source drift in
this repo, and the sync test in this proposal follows it.

`docs/runbook.md` opens with a table of contents of anchor links.
`docs/public/llms.txt` is a 20-line llms.txt-format index with a "Key Resources
& Submissions" list; it is a static artifact, not referenced from any Go file.
`README.md` links docs inline per topic.

The public site serves `/docs` from an embedded `internal/web/docs.html`
(`cmd/server/main.go:398`) and `/docs/local-bridge*` from markdown that is
**duplicated** into `internal/web/` because `go:embed` cannot reach outside its
package; `TestLocalBridgeMarkdownMatchesDocs` in
`internal/web/localbridge_test.go` enforces that the copies match `docs/`.

## Proposed solution

### 1. `docs/troubleshooting.md`

One new markdown file, nine sections. Eight family sections share a fixed
four-subsection shape (Symptom / Cause / What the client or agent should do /
What the operator can do); the ninth is the OAuth client and redirect rules
reference the issue asks for.

Each quoted catalog string is preceded by a machine-readable marker:

```
<!-- catalog: PEER_ID_INVALID -->
```

followed by a fenced block containing the exact rendered text. The marker is
what makes the sync test two-directional: the test can enumerate markers in the
page and enumerate keys in the maps, and fail on either side of the difference.
Markdown renderers drop HTML comments, so the page reads clean.

Where the text does not come from the catalog, the section says which producer
it comes from and names the file, so the next reader can find it:
`sessionErrText` for the revoked-session family, `media_tools.go` for the
confirmation family, the `"enable: telegram login failed"` slog line for the
onboarding families, and `validateRedirectURIShape` for redirects. For the
three log-only families the page states plainly that the client sees a generic
failure and the evidence is server-side, so no one hunts for a tool response
that was never emitted.

Two specifics the issue asks for by name:

- **Peer family.** Tell the agent to call `list_dialogs` and pass the `id`
  field byte-for-byte, and to never construct `channel:<id>` from a message
  link or a forwarded-message header, because a bare numeric id carries no
  access hash — the reason spelled out in the comment at
  `internal/telegram/media_download.go:60` and `messages.go:356`.
- **`get_media`.** Call `prepare_get_media` and `get_media` back-to-back;
  state the TTL as the value of `mcp.ConfirmationTTL` (10 minutes) and that the
  confirmation is single-shot and lost on pod restart by design
  (`internal/mcp/confirm.go`).

### 2. Catalog text change for the peer family

In `internal/mcp/errorcatalog.go`:

- Rewrite the `PEER_ID_INVALID` entry so the action points at `list_dialogs`
  and at passing the id exactly as returned, converging with the wording
  `internal/telegram/messages.go:587` already uses.
- Add `CHANNEL_INVALID` and `CHAT_ID_INVALID` entries with the same peer-family
  wording.

Hard constraint discovered in the clone: `TestMtprotoErrResultCatalog`
(`internal/mcp/errorcatalog_test.go:46`) iterates every key in the map and
asserts the rendered text does **not** contain the raw MTProto code. New
entries must therefore describe the condition without naming the code.

### 3. Drift tests

Three test additions, each placed where it can read real symbols rather than
parse Go source:

- `internal/mcp/troubleshooting_doc_test.go`, **package `mcp`** — reads
  `../../docs/troubleshooting.md`. Because it is in-package it reads
  `mtprotoErrCatalog`, `mtprotoTransientCatalog`, `ConfirmationTTL` and calls
  `sessionErrText(db.ErrSessionRevoked)` directly. Asserts: every `<!-- catalog:
  CODE -->` marker names a real key; every key's `message` and non-empty
  `action` appear verbatim in the page; every key is either documented or in an
  explicit `undocumentedCatalogCodes` allowlist; the confirmation TTL is
  rendered from the constant; the four `media_tools.go` confirmation strings
  appear.
- `internal/oauth/troubleshooting_doc_test.go`, **package `oauth`** — calls
  `validateRedirectURIShape("cursor://anonymous/callback")` and asserts the
  returned error text appears in `../../docs/troubleshooting.md`. This is what
  keeps section 9 honest if the scheme policy is ever loosened under #668.
- `docs/troubleshooting_test.go`, **package `docs`** — sibling of
  `runbook_test.go`. Asserts the page exists, carries the nine required
  headings, and that `../README.md`, `runbook.md` and `public/llms.txt` each
  reference `troubleshooting`, and that `runbook.md`'s table of contents
  includes the entry.

### 4. Links

- `README.md`: one bullet in the docs area near the existing `docs/runbook.md`
  and `docs/slo.md` references.
- `docs/runbook.md`: a table-of-contents entry plus a pointer near the top,
  worded as "client-facing error families" so the alert-driven runbook and the
  symptom-driven page stay distinguishable.
- `docs/public/llms.txt`: one bullet under "Key Resources & Submissions"
  pointing at the GitHub blob URL, matching how the two submission packages are
  already linked there.

Commit style: `docs:` for the page and links, `fix:` for the catalog entries,
`test:` for the drift tests; or a single `docs:` commit if kept together.
Merge with `gh pr merge <N> --merge --delete-branch` per `CLAUDE.md`.

## Alternatives

- **Generate the page from the catalog at build time.** A `go:generate` step
  emitting markdown from `mtprotoErrCatalog` would make drift structurally
  impossible. Dropped: five of the eight families are not in the catalog at
  all (onboarding, OAuth, JWT, confirmation, `RPC_CALL_FAIL`), so the generator
  would cover the minority and the hand-written majority would still need a
  test. Marker plus test gets the same guarantee with none of the machinery.
- **Add the sections to `docs/runbook.md` instead of a new file.** Dropped: the
  runbook is 2312 lines organised one section per *alert*, with an anchor
  contract enforced by `TestRunbookAnchorsPresent`. The audience differs — a
  client or an LLM agent reading `llms.txt` should not have to page through
  alert playbooks — and the issue asks for a separately linkable page.
- **Fix the peer problem in code only, no doc.** Converging every peer error on
  one message would help the 70 % family, but leaves the other seven with no
  written home, and the OAuth/onboarding families cannot be fixed by tool text
  because they never produce tool text. Both are done here; the doc is the
  deliverable, the catalog edit is the smaller half.
- **Render the page on the site immediately.** Dropped to out of scope: it
  requires duplicating the markdown into `internal/web/` and extending
  `localBridgeSlug`-style routing, which is a larger change than the issue asks
  for and is better proposed on its own.

## Platform impact

- **Migrations:** none. No schema, no config, no env var.
- **Backward compatibility:** the two rewritten/added catalog entries change
  user-visible error strings for the peer family. No known consumer parses
  them — the structured envelopes (`flood_wait`, `RISK_GATED`) are untouched,
  and `mtprotoErrResult` keeps returning a plain `NewToolResultError` for
  catalog entries. Any client string-matching on "The peer ID is not valid for
  this account" would break; that risk is accepted because the whole point is
  that the current wording is not working.
- **Resource impact:** none at runtime. Three new test files add negligible CI
  time (all are file reads plus map iteration).
- **Risks and mitigations:**
  - *The doc drifts anyway.* Mitigated by the two-directional marker test and
    the catalog allowlist, which fails the build when a new catalog entry is
    added without a decision about documenting it.
  - *A relative path in a test breaks when files move.* Mitigated by following
    `docs/runbook_test.go`, which already uses `../internal/...` and is proven
    in CI.
  - *The new catalog text leaks the MTProto code and trips
    `TestMtprotoErrResultCatalog`.* Mitigated by making that constraint an
    explicit acceptance criterion and a task DoD.
  - *`FLOOD_PREMIUM_WAIT_N` remains unhandled by the MCP catalog even though
    `telegram.FloodWaitSeconds` knows it.* Not fixed here; the page notes it and
    a follow-up issue is filed, so the gap is recorded rather than silently
    documented away.
