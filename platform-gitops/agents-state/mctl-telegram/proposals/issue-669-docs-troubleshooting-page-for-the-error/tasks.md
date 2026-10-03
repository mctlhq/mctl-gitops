# Tasks: issue-669-docs-troubleshooting-page-for-the-error

- [ ] 1. Inventory the exact strings each of the eight families produces today,
      from `internal/mcp/errorcatalog.go` (`mtprotoErrCatalog`,
      `mtprotoTransientCatalog`, `floodWaitSeconds`), `sessionErrText` in
      `internal/mcp/tools.go`, `internal/mcp/media_tools.go`,
      `internal/mcp/confirm.go`, `internal/telegram/messages.go:587`/`:616`,
      `internal/telegram/media_download.go:69`,
      `internal/oauth/enable_access.go` (the `"enable: telegram login failed"`
      slog line, `enableSendCodeWait`, `cfg.CodeTTL`),
      `internal/oauth/server.go` (`validateRedirectURIShape`, `isLoopbackHost`)
      and `internal/auth/middleware.go` (`classifyAuthError`) —
      DoD: a scratch table mapping family to producing file, exact string, and
      whether the text ever reaches a tool response or is log-only.

- [ ] 2. Update the peer family in `internal/mcp/errorcatalog.go` (depends on 1)
      — rewrite `PEER_ID_INVALID` so the action names `list_dialogs` and "pass
      the id exactly as returned", and add `CHANNEL_INVALID` and
      `CHAT_ID_INVALID` entries with the same wording, converged with
      `internal/telegram/messages.go:587`.
      DoD: `go test ./internal/mcp/...` passes, including
      `TestMtprotoErrResultCatalog`, which asserts the rendered text contains
      no raw MTProto code; `go vet ./...` and `golangci-lint` clean.

- [ ] 3. Write `docs/troubleshooting.md` (depends on 1, 2) — nine sections:
      the eight families, each with Symptom / Cause / What the client or agent
      should do / What the operator can do, plus "Supported OAuth clients and
      redirect rules". Quote catalog strings verbatim, each preceded by an
      `<!-- catalog: CODE -->` marker. State the `get_media` confirmation TTL
      as 10 minutes (`mcp.ConfirmationTTL`) and that it is single-shot. For
      `AUTH_KEY_UNREGISTERED` state there is no server-side remedy and the
      client must reconnect at `tg.mctl.ai/telegram/connect`. For send-code
      `FLOOD_WAIT` state: wait out Telegram's interval, do not retry from
      another browser, and why the canary uses a separate account
      (`docs/runbooks/canary.md`). For the onboarding budget, name
      `OAUTH_CODE_TTL` (default 10m) and `enableSendCodeWait` (90s) rather than
      a hardcoded 30 minutes. Note the unhandled `FLOOD_PREMIUM_WAIT_N` gap.
      DoD: file exists, no emoji, English only, every quoted string copied from
      the task-1 table rather than retyped.

- [ ] 4. Add `internal/mcp/troubleshooting_doc_test.go` (package `mcp`,
      depends on 3) — reads `../../docs/troubleshooting.md`; asserts every
      `<!-- catalog: CODE -->` marker names a real key in
      `mtprotoErrCatalog` or `mtprotoTransientCatalog`; asserts each key's
      `message` and non-empty `action` appear verbatim; asserts every key is
      documented or listed in an `undocumentedCatalogCodes` allowlist; asserts
      the page renders `ConfirmationTTL` and the text of
      `sessionErrText(db.ErrSessionRevoked)`; asserts the four
      `media_tools.go` confirmation strings appear.
      DoD: the test fails if a catalog message is edited without editing the
      page, and fails if a marker names a code that was removed — verify both
      by temporarily mutating the map, then revert.

- [ ] 5. Add `internal/oauth/troubleshooting_doc_test.go` (package `oauth`,
      depends on 3) — calls `validateRedirectURIShape("cursor://anonymous/callback")`
      and asserts the returned error text appears in
      `../../docs/troubleshooting.md`.
      DoD: the test fails if the scheme-policy message in
      `internal/oauth/server.go` changes without the page changing.

- [ ] 6. Add `docs/troubleshooting_test.go` (package `docs`, depends on 3, 7) —
      sibling of `runbook_test.go`; asserts `troubleshooting.md` exists and
      carries the nine required headings, and that `../README.md`,
      `runbook.md` and `public/llms.txt` each reference `troubleshooting`, and
      that the runbook table of contents lists the entry.
      DoD: `go test ./docs/...` passes; removing any one of the three links
      fails it.

- [ ] 7. Link the page from `README.md`, `docs/runbook.md` (table of contents
      plus an intro pointer distinguishing "client-facing error families" from
      the alert playbooks) and `docs/public/llms.txt` (a bullet under "Key
      Resources & Submissions" using the GitHub blob URL, matching the existing
      submission-package entries). Optionally add the link to
      `internal/web/docs.html` if it is a one-line change.
      DoD: all three files reference the page; `go test ./...` passes,
      including `internal/web` tests if `docs.html` was touched.

- [ ] 8. File a follow-up issue for `FLOOD_PREMIUM_WAIT_N` — `floodWaitSeconds`
      in `internal/mcp/errorcatalog.go` handles `FLOOD_WAIT_`/`SLOWMODE_WAIT_`
      only, while `telegram.FloodWaitSeconds`
      (`internal/telegram/floodwait.go`) also handles `FLOOD_PREMIUM_WAIT_`, so
      a premium flood wait falls through to the generic handler with no
      `retry_after_seconds`.
      DoD: issue open, linked from #669 and referenced in the page.

- [ ] 9. Open the PR (depends on 2-8) — conventional commits (`docs:`, `fix:`,
      `test:`), body linking #669 and #668.
      DoD: CI green; merged with `gh pr merge <N> --merge --delete-branch` per
      `.claude/CLAUDE.md` (merge commits, never squash or rebase).

## Tests

- [ ] T1. `TestTroubleshootingDocCatalogSync` (package `mcp`) — catalog markers
      and strings are two-directionally in sync with `mtprotoErrCatalog` and
      `mtprotoTransientCatalog`, with an explicit undocumented-code allowlist.
- [ ] T2. `TestTroubleshootingDocSessionAndConfirmStrings` (package `mcp`) —
      the page renders `ConfirmationTTL`, `sessionErrText(db.ErrSessionRevoked)`
      and the `media_tools.go` confirmation messages verbatim.
- [ ] T3. `TestTroubleshootingDocRedirectPolicy` (package `oauth`) — the page
      quotes what `validateRedirectURIShape` returns for a `cursor://` URI.
- [ ] T4. `TestTroubleshootingSectionsPresent` (package `docs`) — the nine
      required headings exist, each family section carrying the four fixed
      subsections.
- [ ] T5. `TestTroubleshootingLinkedFromReadmeRunbookAndLlmsTxt` (package
      `docs`) — `../README.md`, `runbook.md` (body and table of contents) and
      `public/llms.txt` all reference the page.
- [ ] T6. Regression: existing `internal/mcp/errorcatalog_test.go` still
      passes with the three peer entries, in particular the invariant that
      rendered text never contains the raw MTProto code.

## Rollback

The change is documentation plus three test files plus three catalog map
entries; there is no state, no migration and no config. Reverting the merge
commit (`git revert -m 1 <merge-sha>`) restores the previous catalog strings
and removes the page and its tests in one step, with no redeploy needed for the
doc itself. If only the catalog wording proves wrong — for example a connector
turns out to string-match the old `PEER_ID_INVALID` text — revert task 2's hunk
alone and keep the page, then relax the T1 assertion for that one code via the
`undocumentedCatalogCodes` allowlist until the wording is settled. If a drift
test proves flaky in CI (relative-path resolution under a different working
directory), skip that single test with a `t.Skip` and a linked issue rather
than deleting the page.
