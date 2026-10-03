# Tasks: x-crypto-ssh-transitive-audit

- [ ] 1. Run `go list -m all` and `go mod graph` against mctl-agent's current
      `go.mod`/`go.sum` and filter for `golang.org/x/crypto` — DoD: full list of
      requiring modules and resolved `x/crypto` version(s) captured verbatim in the
      tracking PR/issue.
- [ ] 2. Run `govulncheck ./...` to get a reachability-based signal (not just
      presence-in-graph) for the six disclosed CVEs (CVE-2026-46597, CVE-2026-39835,
      CVE-2026-39827, CVE-2026-39828, CVE-2026-39829, CVE-2026-39832) (depends on 1) —
      DoD: `govulncheck` output captured and attached to the tracking PR/issue.
- [ ] 3. Classify the finding as one of: (a) not present in build graph, (b) present but
      `x/crypto/ssh` specifically absent (other `x/crypto` subpackages don't count),
      (c) present and unreachable, (d) present and reachable (depends on 1, 2) — DoD:
      one of the four labels is recorded with supporting evidence (graph excerpt +
      govulncheck output).
- [ ] 4. IF classified (d) present and reachable: identify and apply the minimal fix —
      either bump the upstream module that pulls in `x/crypto/ssh` to a release that
      itself resolves to a patched `x/crypto`, or add a direct
      `require golang.org/x/crypto <patched-version>` to force resolution (depends on
      3) — DoD: `go.sum` reflects a patched `x/crypto` version; `go build ./...` and
      full test suite pass.
- [ ] 5. IF classified (a), (b), or (c): document "not exposed" with evidence in a
      short note (PR description is sufficient; no code change) (depends on 3) — DoD:
      finding is written down and linked from this proposal's tracking issue/PR.
- [ ] 6. Add a checklist note (in the PR description or team runbook, not in
      `context/`, which is read-only) stating that any future bump of `go-chi/chi`,
      `google/go-github`, or `anthropic-sdk-go` should re-run this audit (depends on 3)
      — DoD: note exists and is discoverable by whoever performs the next dependency
      bump.

## Tests
- [ ] T1. `go build ./...` succeeds after any dependency graph change made under task 4.
- [ ] T2. Full existing test suite passes after any dependency graph change made under
      task 4 (no behavioral regression from a forced `x/crypto` version resolution).
- [ ] T3. `govulncheck ./...` reports no findings for CVE-2026-46597, CVE-2026-39835,
      CVE-2026-39827, CVE-2026-39828, CVE-2026-39829, CVE-2026-39832 after remediation
      (if remediation was needed) or confirms "not exposed" (if it wasn't).

## Rollback
If task 4 (dependency bump / direct `x/crypto` pin) is applied and causes unexpected
build or runtime issues, revert the `go.mod`/`go.sum` change in a single commit and
redeploy the previous ArgoCD-synced revision. If no code change was made (findings (a),
(b), or (c)), there is nothing to roll back — the audit is documentation-only.
