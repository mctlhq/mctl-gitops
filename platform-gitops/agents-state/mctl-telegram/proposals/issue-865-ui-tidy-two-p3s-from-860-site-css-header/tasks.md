# Tasks: issue-865-ui-tidy-two-p3s-from-860-site-css-header

- [ ] 1. Guard the newline index in `TestSiteCSSMirrorMatchesPinnedVersion`
  (`internal/ui/chrome_test.go`): if `strings.Index` returns -1 (or
  `strings.Cut` reports not found), call `t.Fatalf` with a clear message
  before slicing. — DoD: the test never slices with -1, and its existing
  assertions are unchanged.
- [ ] 2. Re-wrap line 29 of the package doc comment in `internal/ui/chrome.go`
  (the `"lite"` tier bullet) to at most 80 columns. Keep the wording and the
  4-space continuation indent. — DoD: no line in the package doc comment is
  longer than 80 columns except the unbreakable CSP literal on line 27, and
  `go doc ./internal/ui` shows the same text.
- [ ] 3. Run `gofmt -l internal/ui`, `go vet ./internal/ui/...` and
  `go test ./internal/ui/...` (depends on 1, 2). — DoD: all three are clean.
- [ ] 4. Commit as `test(ui): guard site.css header parse; chore: wrap chrome.go doc comment`
  or as two conventional commits, referencing #865. — DoD: a PR is opened.

## Tests
- [ ] T1. `go test ./internal/ui/ -run TestSiteCSSMirrorMatchesPinnedVersion`
  passes with the current asset.
- [ ] T2. Manual check, not committed: temporarily set `siteCSS` to a string
  with no newline, for example in a scratch copy of the test, and confirm the
  test reports a `t.Fatalf` failure instead of a panic.
- [ ] T3. `awk 'NR<=31 && length>80' internal/ui/chrome.go` prints only the CSP
  literal line, if anything.

## Rollback
Revert the merge commit. Both changes are test-only or comment-only and have
no deploy impact.
