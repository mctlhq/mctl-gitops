# Tasks: argocd-cluster-label-drift

- [ ] 1. Locate and audit the current version-label comparison code in
  `internal/skill/builtin/argocd_drift.go` (or equivalent file) — DoD: a code comment
  or PR description identifies the exact line(s) where the cluster version label is read
  and compared, and documents the current format assumption (`"Major.Minor"`).

- [ ] 2. Implement `parseClusterVersionLabel(label string) (ClusterVersion, error)` in
  the `ArgoCDDrift` skill package (depends on 1) — DoD: the function strips a leading
  `"v"`, splits on `"."`, parses Major and Minor as integers, returns a typed
  `ClusterVersion{Major, Minor int}` struct; returns a non-nil error for malformed
  input; compiles with `go build ./...` and passes `go vet ./...`.

- [ ] 3. Update the drift comparison site to use `parseClusterVersionLabel` on both the
  observed and expected labels (depends on 2) — DoD: the old raw-string or two-segment-
  split comparison is replaced with a call to `parseClusterVersionLabel`; when parsing
  fails, a structured `slog.Warn` is emitted with the raw label value, and no drift
  event is raised for that attribute.

- [ ] 4. Extend the table-driven test suite for `ArgoCDDrift` (depends on 3) — DoD:
  new test cases cover at minimum: legacy format (`"1.29"`), new format (`"v1.29.4"`),
  cross-format equal (`"1.29"` vs `"v1.29.4"` → no drift), cross-format unequal
  (`"1.29"` vs `"v1.30.1"` → drift), and malformed inputs (`""`, `"abc"`, `"v1"`,
  `"v1.abc.4"`); all existing tests continue to pass.

- [ ] 5. Run the full test suite and confirm CI green (depends on 4) — DoD:
  `go test ./internal/skill/builtin/...` exits 0 with no skipped or failing cases;
  coverage for the normaliser function is 100%.

- [ ] 6. Open a PR to `mctlhq/mctl-agent` with the changes from tasks 2–4 (depends on
  5) — DoD: PR description references this proposal slug, explains the Argo CD v3.4.1
  format change, links to the upstream release note, and includes the test output.

## Tests

- [ ] T1. Unit: `parseClusterVersionLabel("1.29")` returns `ClusterVersion{1, 29}`, nil.
- [ ] T2. Unit: `parseClusterVersionLabel("v1.29.4")` returns `ClusterVersion{1, 29}`, nil.
- [ ] T3. Unit: cross-format equal — comparing parsed `"1.29"` to parsed `"v1.29.4"`
  yields no drift event.
- [ ] T4. Unit: cross-format unequal — comparing parsed `"1.29"` to parsed `"v1.30.1"`
  yields a drift event with observed=`"v1.30.1"` and expected=`"1.29"` in the evidence
  payload.
- [ ] T5. Unit: malformed label `"abc"` causes `parseClusterVersionLabel` to return a
  non-nil error; no panic; slog.Warn is emitted.
- [ ] T6. Integration (optional, run against a real or mocked Argo CD v3.4.1 API):
  `ArgoCDDrift` skill evaluates a live cluster with a `"vMajor.Minor.Patch"` label and
  correctly reports drift or no-drift as expected.

## Rollback
The change is contained in a single skill package with no external side effects. If a
regression is detected in production:

1. Revert the PR to `mctlhq/mctl-agent` and release a patch version (e.g., v1.5.1 →
   v1.5.0 re-release from the previous tag).
2. The circuit breaker on `ArgoCDDrift` will auto-disable the skill after N consecutive
   failures, preventing erroneous drift events from flooding the ticket queue while the
   rollback is in progress.
3. Manually re-enable `ArgoCDDrift` after the rollback deploy confirms the old behaviour.
4. File a post-mortem identifying which test case was missing, add it, and retry.
