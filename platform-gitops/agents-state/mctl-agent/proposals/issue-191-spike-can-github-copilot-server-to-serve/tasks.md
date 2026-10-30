# Tasks: issue-191-spike-can-github-copilot-server-to-serve

- [ ] 1. Re-run the credential inventory against HEAD: `grep -rni copilot`, read the env
  reads in `internal/config/config.go` `Load`, the outbound HTTP clients
  (`internal/fixer/github.go`, `internal/fixer/token.go`,
  `internal/skill/builtin/llm_diagnosis.go`, `internal/mctlclient`, `internal/notify`,
  `internal/scoutspike`) and `.github/workflows/*.yml`. DoD: every credential and
  destination is captured, matching or correcting the table in design.md.
- [ ] 2. Verify the GitHub changelog entry (2026-10-27): whether the feature exists,
  which Copilot APIs it covers and the App permission it requires. DoD: each claim is
  recorded as verified (with a link) or unverified.
- [ ] 3. Write `docs/spikes/copilot-s2s-auth.md` (depends on 1, 2). It contains the
  inventory table, a feature summary, the decision "no-go / not applicable for
  mctl-agent" with reasons, the residual `MCTL_API_TOKEN` fallback risk, unverified
  deployed-state items, and follow-up candidates outside this repo. DoD: the document is
  merged and the go/no-go is stated in its first paragraph.
- [ ] 4. Add `internal/fixer/copilot_guard_test.go`. It is a table-driven test that scans
  non-test `.go` files under the module root for Copilot API hostnames and fails with a
  pointer to the spike document. DoD: `go test ./internal/fixer/...` passes on HEAD;
  `go vet` and `go fmt` are clean.
- [ ] 5. Add a one-line link from the `GITHUB_TOKEN` row in `README.md` to the spike
  document (depends on 3). DoD: the link resolves.
- [ ] 6. Comment the decision on issue #191 and close it, or retarget its follow-ups
  (depends on 3). DoD: the issue references the merged document.

## Tests
- [ ] T1. Guard test passes on current HEAD (no Copilot hosts present).
- [ ] T2. Guard test negative case: a table entry feeds an in-memory source string that
  contains `api.githubcopilot.com` to the scanning helper, and the helper reports a match.
- [ ] T3. Existing `internal/fixer` token tests (`authTransport` host scoping,
  `tokenSource` rotation) still pass unchanged.

## Rollback
Revert the PR. It only adds a Markdown document, a test file and a README line, with no
runtime, config or deployment change, so reverting has no operational effect.
