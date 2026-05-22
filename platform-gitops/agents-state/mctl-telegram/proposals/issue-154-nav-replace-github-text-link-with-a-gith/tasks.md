# Tasks: issue-154-nav-replace-github-text-link-with-a-gith

- [ ] 1. Replace GitHub text link with inline SVG icon in `ui_topbar`
  **File:** `internal/ui/chrome.go`, inside the `defs` string, `{{define "ui_topbar"}}` block.
  **Change:** Replace the single line:
  ```html
  <a href="https://github.com/mctlhq/mctl-telegram" target="_blank" rel="noopener">github ↗</a>
  ```
  with:
  ```html
  <a href="https://github.com/mctlhq/mctl-telegram" target="_blank" rel="noopener" aria-label="GitHub" title="GitHub" class="gh-link"><svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.65 7.65 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg></a>
  ```
  **DoD:** `go build ./internal/ui/...` succeeds; the string `github ↗` no
  longer appears in the compiled template output; the string `aria-label="GitHub"`
  does appear.

- [ ] 2. Update `chrome_test.go` to assert the new accessible label (depends on 1)
  **File:** `internal/ui/chrome_test.go`, function `TestFullChrome`.
  **Change:** Add `aria-label="GitHub"` to the list of expected strings checked
  with `strings.Contains`. Optionally remove or replace any assertion that
  previously checked for `github ↗` if one is added before this task runs (none
  exists today).
  **DoD:** `go test ./internal/ui/...` passes; the test fails if `aria-label="GitHub"`
  is absent from the rendered output.

## Tests

- [ ] T1. Unit — `go test ./internal/ui/...` passes with no changes to existing
  assertions. The new assertion added in task 2 confirms `aria-label="GitHub"`
  is present in the full-page render.
- [ ] T2. Unit — `go test ./internal/ui/...` confirms the lite-page
  (`TestLiteChromeHasNoExternalDeps`) is unaffected: the `ui_topbar_lite` /
  `topbarLiteHTML` constant does not contain the GitHub link and is not changed.
- [ ] T3. Visual (manual) — load any full page (e.g., `/`) in a browser,
  resize to a mobile width (360 px or 375 px), confirm the top navigation
  renders on one line without the brand or controls wrapping to a second line.
- [ ] T4. Accessibility (manual) — tab to the GitHub icon link; confirm the
  browser tooltip reads "GitHub" and a screen reader (or browser accessibility
  inspector) announces "GitHub, link".
- [ ] T5. Theme (manual) — toggle between light and dark themes; confirm the
  GitHub icon color changes with the rest of the nav link text, matching
  `var(--text-dim)` at rest.
- [ ] T6. Lint — `go vet ./...` and `golangci-lint run` produce no new warnings.

## Rollback

1. Revert `internal/ui/chrome.go` to restore the original line:
   `<a href="https://github.com/mctlhq/mctl-telegram" target="_blank" rel="noopener">github ↗</a>`
2. Revert the `chrome_test.go` assertion added in task 2.
3. Run `go test ./internal/ui/...` to confirm the original suite passes.

No database migration, no configuration change, no static asset file, and no
deployment pipeline step is involved; a single `git revert` of the feature
commit is sufficient to restore the previous state.
