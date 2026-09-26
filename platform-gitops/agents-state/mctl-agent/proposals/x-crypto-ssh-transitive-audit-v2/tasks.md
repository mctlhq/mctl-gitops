# Tasks: x-crypto-ssh-transitive-audit-v2

- [ ] 1. Check the status and evidence of the original `x-crypto-ssh-transitive-audit`
      proposal (has it run, is `go.sum` unchanged since) — DoD: decision recorded on
      whether to reuse its `go mod graph` / `go list -m all` output or re-run it.
- [ ] 2. Reuse or re-run `go list -m all` / `go mod graph`, filtered for
      `golang.org/x/crypto` (depends on 1) — DoD: current module-graph evidence for
      `x/crypto` (present/absent, requiring module, resolved version) is available and
      attached to the tracking PR/issue.
- [ ] 3. Run `govulncheck ./...` and check its output specifically for CVE-2026-39830,
      alongside re-confirming no regression on the original six CVEs (CVE-2026-46597,
      CVE-2026-39835, CVE-2026-39827, CVE-2026-39828, CVE-2026-39829, CVE-2026-39832)
      (depends on 2) — DoD: `govulncheck` output captured and attached, explicitly
      covering all seven CVEs.
- [ ] 4. Classify the finding as one of: (a) not present in build graph, (b) present but
      `x/crypto/ssh` specifically absent, (c) present and unreachable, (d) present and
      reachable — for CVE-2026-39830 specifically (depends on 2, 3) — DoD: one of the
      four labels recorded with supporting evidence.
- [ ] 5. IF classified (d): identify and apply the minimal fix covering all seven
      tracked CVEs at once (bump the pulling module, or force-resolve `x/crypto` via a
      direct `require` line) (depends on 4) — DoD: `go.sum` reflects a version that
      `govulncheck` confirms resolves all seven CVEs; `go build ./...` and the full
      test suite pass.
- [ ] 6. IF classified (a), (b), or (c): update the original audit's "not exposed"
      documentation to reflect the expanded seven-CVE check, cross-referenced from this
      proposal (depends on 4) — DoD: original audit's tracking PR/issue is updated (or
      explicitly cross-linked) with the new finding; no code change.
- [ ] 7. Re-affirm the standing checklist note that any future bump of `go-chi/chi`,
      `google/go-github`, or `anthropic-sdk-go` re-triggers this audit against the
      then-current CVE list (depends on 6) — DoD: note exists and is discoverable by
      whoever performs the next dependency bump.

## Tests
- [ ] T1. `go build ./...` succeeds after any dependency graph change made under task 5.
- [ ] T2. Full existing test suite passes after any dependency graph change made under
      task 5 (no behavioral regression from a forced `x/crypto` version resolution).
- [ ] T3. `govulncheck ./...` reports no findings for CVE-2026-39830 or any of the
      original six CVEs after remediation (if remediation was needed), or confirms
      "not exposed" for all seven (if it wasn't).

## Rollback
If task 5 (dependency bump / direct `x/crypto` pin) is applied and causes unexpected
build or runtime issues, revert the `go.mod`/`go.sum` change in a single commit and
redeploy the previous ArgoCD-synced revision. If no code change was made (findings (a),
(b), or (c)), there is nothing to roll back — this audit, like the original, is
documentation-only in that case.
