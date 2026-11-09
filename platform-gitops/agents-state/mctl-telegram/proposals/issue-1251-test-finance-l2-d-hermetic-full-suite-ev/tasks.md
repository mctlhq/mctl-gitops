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

## AMEND acceptance tasks (normative; update the corresponding tasks above)

These are required before implementation acceptance and supersede older DoDs
where contradictory. They do **not** authorize executing them at intake time.

- [ ] A1. Freeze a reviewed #1244 T1–T10 / M1–M4 **subcase crosswalk** with
  exact canonical `package:id` and a `fixture_id` requirement per entry.
  Include all missing emitters in the manifest as mandatory and mark them
  MISSING; do not infer completion from current `l2Record` call sites.
- [ ] A2. Add `OFFLINE.default_paths` tests to **policy, control and
  telegram** (listener and agentapi already emit one). Confirm exactly one
  PASS per package, while `OFFLINE.whole_process` stays
  CANNOT-OBSERVE unless a separate real sandbox is verified.
- [ ] A3. Implement a runner **BLOCKED sentinel + EXIT finalizer**, preserve
  the exit codes of every test/vet/comparison/aggregator command and reject
  empty/unusable streams. A real subprocess failure must make the runner
  exit non-zero; a complete, intentionally observed gap may exit zero with
  a visible BLOCKED security gate. Test early preflight failure, compile
  failure, vet failure, assertion failure and a failing command in a pipe.
- [ ] A4. Split dependency resolution into an explicit preflight.
  Execute all tests, vet and aggregation with
  `GOPROXY=off GOSUMDB=off GOFLAGS=-mod=readonly`,
  with credentials removed in the parent environment before spawn.
  Verify missing dependencies produce BLOCKED, not a hidden network fetch.
- [ ] A5. Add stable synthetic `fixture_id` metadata to mandatory
  canonical results (use explicit `none` only where legitimately
  inapplicable). Verify two tagged runs match full
  `(package,id,outcome,fixture_id,rev)` tuples and the manifest.
  A mismatched fixture/rev must yield INVALID and BLOCKED.
- [ ] A6. Split the existing T10 redaction evidence between durable audit
  and real slog emission. A slog PASS requires `slog_bytes>0` from a
  synthetic marker sent through the production redacting handler;
  otherwise emit CANNOT-OBSERVE, without rewriting slice-C historical
  evidence or hiding the known plaintext-intent FAIL/GAP.
- [ ] A7. Make manual workflow summary and artifact steps
  `if: always()`, with a fallback BLOCKED artifact when an early
  step fails; no secrets, product permissions or deployment.
  If normal `build.yml` still skips tagged tests, explicitly record
  the **unresolved continuous-CI gap** and open a separately governed
  follow-up only after owner acceptance.
- [ ] A8. Add negative aggregator/runner fixtures for missing mandatory
  emitters, unexpected row, duplicate, unknown token, M1–M4 non-PASS,
  five-package offline control failure, empty/no JSON, executable failure,
  wrong revision, unstable fixture and zero-byte slog.
- [ ] A9. Final evidence report must distinguish COMPLETE and
  COMPLETE_WITH_GAPS_BLOCKED from any transport/build/CI error; show
  source revision, exact commands, manifest crosswalk, all missing
  emitters and gaps, run exit codes, fixture fingerprint, actual
  offline coverage, `FINANCE_SECURITY_GATE=BLOCKED` and
  `RESEARCH_ONLY_DEFER`.
- [ ] A10. Preserve only docs-only changes in this AMEND PR. Require a
  fresh Claude/Agy review on its final HEAD and a protected merge,
  then re-compute canonical content digest before any separate owner
  approval through Temporal DevLoop #1251. **No implementer or
  standalone approval in this AMEND.**
