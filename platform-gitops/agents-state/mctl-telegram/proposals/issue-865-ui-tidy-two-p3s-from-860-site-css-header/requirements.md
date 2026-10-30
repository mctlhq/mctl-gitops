# Tidy two P3s from #860: site.css header guard and chrome.go doc-comment wrap

## Context
PR #860 left two low-priority review findings that issue #865 asks to close.
First, `TestSiteCSSMirrorMatchesPinnedVersion` in `internal/ui/chrome_test.go`
slices `siteCSS[:strings.Index(siteCSS, "\n")]`. If the embedded
`internal/ui/assets/site.css` ever has no newline, `strings.Index` returns -1
and the slice `siteCSS[:-1]` panics. The test run then crashes instead of
failing with a readable message.

Second, line 29 of the package doc comment in `internal/ui/chrome.go` is about
115 columns wide. Every other line of that comment wraps at about 80 columns.

Both are test-only or comment-only changes. Runtime behaviour does not change.

## User stories
- AS a contributor refreshing the site.css mirror I WANT a malformed mirror
  header to produce a clear test failure SO THAT I can see what is wrong
  without reading a panic stack trace.
- AS a reader of `internal/ui` I WANT the package doc comment wrapped
  consistently SO THAT it reads cleanly in editors and `go doc`.

## Acceptance criteria (EARS)
- IF the embedded `siteCSS` contains no newline THEN
  `TestSiteCSSMirrorMatchesPinnedVersion` SHALL fail via `t.Fatalf` with a
  message saying the site.css header line is missing its newline, and SHALL
  NOT panic.
- WHEN `siteCSS` starts with the expected header line followed by a newline,
  the test SHALL keep comparing that line against
  `"/* @mctlhq/css " + DesignVersion + " — site.css. */"`, exactly as it does
  today.
- WHILE the pinned mirror matches `DesignVersion`, `go test ./internal/ui/...`
  SHALL pass.
- WHEN the package doc comment in `internal/ui/chrome.go` is rendered, no line
  in it SHALL be longer than 80 columns, and its wording SHALL stay the same.

## Out of scope
- Changes to `site.css`, `DesignVersion`, the CSS bundling, or any runtime code.
- Re-wrapping other long lines in `chrome.go`, such as the code and HTML
  template lines after the package clause.
- The similar unguarded `strings.Index(componentsCSS[i:], "}")` slice in
  `TestCtrlListColumnCanShrink`. See Open questions.

## Open questions
- `TestCtrlListColumnCanShrink` (chrome_test.go line 207) has the same latent
  -1 slice risk when no `}` follows `ul.ctrl {`. The issue does not mention it,
  so this proposal leaves it unchanged. The implementer may guard it the same
  way if the reviewer wants that.
