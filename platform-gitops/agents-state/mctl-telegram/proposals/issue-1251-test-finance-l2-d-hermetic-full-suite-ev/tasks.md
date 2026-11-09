# Tasks: issue-1251-test-finance-l2-d-hermetic-full-suite-ev

Precondition: #1247, #1249 and #1250/#1255 are merged or reviewed, and this proposal has a fresh
exact-content human approval that is distinct from the #1244 grant. Do not touch the existing slice
PR branches.

- [ ] 1. Build `internal/l2finance/gate/testdata/manifest.txt` with one canonical `<pkg>:<id>` and
  one kind (`case`, `control` or `offline`) per line, from every current `l2Record`/`expectGap` call
  site.
  - Cross-check every #1244 T1-T10 subcase and M1-M4 control.
  - Add an ID with no emitter for each required subcase that has no emitter.
  - DoD: every #1244 subcase maps to at least one manifest line, and the review notes list the
    unmapped ones.
- [ ] 2. Align the policy harness in `internal/agent/policy/l2finance_result_test.go`. (depends on 1)
  - Add `TestMain` with the 40-hex `L2FINANCE_SOURCE_REV` check, the env unsets and the
    resolver/transport guard.
  - Use `l2SourceRev` instead of `248db4f`.
  - Add an `OFFLINE.default_paths` self-test.
  - DoD: the package aborts without the revision, and every row carries the 40-hex rev.
- [ ] 3. Normalise the outcome tokens and duplicates. (depends on 1)
  - Emit M4 as `PASS` with `detected` in evidence.
  - Make the `T1.wire_input_peer_self` call sites emit once per run, or give them distinct IDs.
  - DoD: no `L2RESULT` outcome contains a space, and no canonical ID is duplicated in a run.
- [ ] 4. Write the aggregator `internal/l2finance/gate/gate_test.go` (`//go:build l2finance`).
  (depends on 1)
  - Parse the `go test -json` stream with the strict regex.
  - Check against the manifest.
  - Report `harness_status` separately from `FINANCE_SECURITY_GATE`.
  - Map the result to the issue outcome and write the Markdown fragment.
  - DoD: exit is non-zero only on INVALID, and stdout always ends with both status lines.
- [ ] 5. Write the runner `scripts/l2finance/run.sh`. (depends on 2, 3, 4)
  - Check for a clean tree and pin the revision.
  - Run the tagged `-race -count=1` JSON run, then vet, the untagged comparison and the optional
    lint.
  - Run the aggregator and the second-run reproducibility diff.
  - DoD: a local run prints `harness_status=COMPLETE` and `FINANCE_SECURITY_GATE=BLOCKED` on the
    current code.
- [ ] 6. Add the optional `.github/workflows/l2finance-gate.yml`. (depends on 5)
  - Trigger on `workflow_dispatch` only, with `permissions: contents: read`, no secrets and pinned
    actions.
  - Run `go mod download` before the runner.
  - Write the step summary and upload the artifact.
  - DoD: no `secrets.` string appears in the file, the workflow is not in required checks, and a
    manual run's summary starts with the gate line.
- [ ] 7. Regenerate `docs/reports/finance-assistant-l2-results.md` from the aggregator output.
  (depends on 5)
  - Include the pinned SHA, Go version, commands, both statuses, the issue outcome and the full
    table with counts.
  - List the gap IDs with planned follow-up fix titles (not implemented).
  - Include the M1-M4 evidence, the vet, untagged, lint and reproducibility results, and the offline
    limitation.
  - State that #325 `RESEARCH_ONLY_DEFER` is unchanged.
  - DoD: the report matches the aggregator output row for row.
- [ ] 8. Verify scope. (depends on 7)
  - `git diff --name-only origin/main` lists only `*_test.go` files with `//go:build l2finance`,
    `internal/l2finance/gate/testdata/*`, `scripts/l2finance/*`, the optional workflow and the
    report.
  - DoD: no production Go, config, permission or deploy file changes.
- [ ] 9. Get an independent Claude/Agy review and human acceptance of the report. (depends on 8)
  - DoD: acceptance is recorded. Follow-up security-fix issues are filed only afterwards, as separate
    approvals.

## Tests

- [ ] T1. Aggregator unit test: a synthetic stream that is missing one manifest ID gives
  `harness_status=INVALID` and `INCOMPLETE_BLOCKED`.
- [ ] T2. Aggregator unit test: a duplicate canonical ID gives INVALID.
- [ ] T3. Aggregator unit test: an outcome token with a space (`PASS (detected)`) or an unknown token
  is unclassified and gives INVALID.
- [ ] T4. Aggregator unit test: a row whose rev differs from the pinned SHA, or that is not 40-hex,
  gives INVALID.
- [ ] T5. Aggregator unit test: a `control` row (M1-M4) or an `offline` row that is not PASS gives
  INVALID, not just BLOCKED.
- [ ] T6. Aggregator unit test: a complete stream with one FAIL/GAP gives
  `COMPLETE_WITH_GAPS_BLOCKED` with exit 0, and the output contains `FINANCE_SECURITY_GATE=BLOCKED`.
- [ ] T7. Aggregator unit test: only a complete all-PASS stream gives `FINANCE_SECURITY_GATE=PASS`
  and `COMPLETE_WITH_PASS`.
- [ ] T8. Aggregator unit test: an empty stream, or a stream with a package build failure, gives
  `CANNOT_OBSERVE_BLOCKED`.
- [ ] T9. Policy package: without `L2FINANCE_SOURCE_REV` it exits 2 before any `L2RESULT`, and its
  `OFFLINE.default_paths` row is PASS.
- [ ] T10. Full runner on current HEAD: `harness_status=COMPLETE` and `FINANCE_SECURITY_GATE=BLOCKED`.
  Two runs give identical `(id, outcome)` sets. The untagged `go test -race ./...` stays green and
  unchanged.

## Rollback

Every change is test-only, tooling or docs. Revert the merge commit (`git revert -m 1 <merge>`). That
removes the aggregator, runner, workflow and harness alignment, and restores the slice-A partial
report. There is nothing to undo in deployment, data or config. If only the manual workflow
misbehaves, delete `.github/workflows/l2finance-gate.yml` on its own. The default CI is unaffected
either way.
