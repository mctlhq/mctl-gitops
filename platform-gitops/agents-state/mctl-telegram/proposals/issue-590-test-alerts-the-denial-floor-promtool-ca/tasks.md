# Tasks: issue-590-test-alerts-the-denial-floor-promtool-ca

- [ ] 1. Set up a local promtool harness matching CI. Download promtool
      `2.52.0` (the `PROM_VERSION` pinned in `.github/workflows/build.yml`,
      lines 175-179) and extract the rules the way CI does:
      `yq '.spec' deploy/alerts/mctl-telegram.rules.yaml > /tmp/rules.yaml`
      (the test file's `rule_files:` entry is that absolute path).
      — DoD: `promtool check rules /tmp/rules.yaml` reports
      `SUCCESS: 19 rules found` and
      `promtool test rules deploy/alerts/mctl-telegram.rules_test.yaml`
      reports SUCCESS on an unmodified checkout.

- [ ] 2. Record the pre-change mutation baseline (depends on 1). Relax the
      floor in a scratch copy of `/tmp/rules.yaml`:
      `sum by (reason) (increase(mctl_agent_policy_denials_total[30m])) > 4`
      becomes `> -1`. Run the suite against it and keep the output.
      — DoD: the exact promtool output is captured for the PR body. Expect
      FAILED on promtool 2.52.0 (the existing case does catch the mutation on
      the pinned version) and SUCCESS on promtool 3.x (where left-open range
      selectors make the case vacuous — the behaviour #590 reports). Do not
      restate the issue's unconditional claim without this measurement.

- [ ] 3. Replace the two input series of the denial-floor case in
      `deploy/alerts/mctl-telegram.rules_test.yaml` (lines 128-137, the block
      commented "T4b") with the mctl-gitops#1110 inputs, byte-identical:
      `mctl_agent_jobs_total{status="processing"}` becomes
      `'0 0 1 1 2 2 3 3 4 4 5 5 6 6 6 6 6 6 6 6 6 6 6 6 6 6 6 6 6 6 6'` and
      `mctl_agent_policy_denials_total{reason="unknown"}` becomes
      `'0 0 0 0 0 1 1 1 1 1 2 2 2 2 2 3 3 3 3 3 3 3 3 3 3 3 3 3 3 3 3'`.
      Leave `interval: 1m`, `eval_time: 30m`, `alertname:` and `exp_alerts: []`
      untouched. (depends on 1)
      — DoD: exactly 62 sample values change; `git diff` touches no other case,
      no rule file, and no workflow.

- [ ] 4. Rewrite the case comment (depends on 3). It must state: which clause
      suppresses the alert (the `> 4` absolute floor, not the share); the
      concrete numbers the input produces — six claims against three denials,
      share `0.50`, extrapolated denial count `3.0` on Prometheus 2.x and about
      `3.10` on Prometheus 3.x, both under the `> 4` floor; why the series must
      rise inside the window, namely that a series which steps once at `t=1m`
      and then holds flat reads as a constant under a left-open range selector
      (Prometheus 3.0 changed range selectors from closed to left-open), making
      both rates `0`, the share `NaN`, and the case silent for arithmetic
      reasons regardless of the floor; and that the inputs mirror the
      mctl-gitops case `denials below the absolute floor stay silent despite a
      high share` from mctlhq/mctl-gitops#1110.
      — DoD: no sentence in the comment asserts a property that T1-T8's
      surrounding style would let a reader verify only by trusting it; the
      claim "kills a dropped floor clause" is now backed by task 5's evidence.

- [ ] 5. Re-run the mutation against the replaced case (depends on 3, 4).
      — DoD: with the floor intact the whole suite is SUCCESS; with the floor
      relaxed to `> -1` the suite FAILS on the denial-floor case with
      `exp:[]` against a fired
      `MctlAgentPolicyDenialRateHigh{reason="unknown", severity="warning",
      service="mctl-telegram"}`. Both outputs pasted into the PR body.
      Confirmed during investigation on promtool 2.52.0 and 3.5.0 — the
      replacement kills the mutation on both.

- [ ] 6. (Optional, low risk) Fix the stale first paragraph of the test file
      header (lines 6-9), which still says "these two cases" although the file
      now holds ten. Rephrase to state the pairing principle generally
      (a silence assertion and a firing assertion are only meaningful together)
      without changing its meaning. (depends on 3)
      — DoD: header no longer counts cases; no case bodies touched.

- [ ] 7. (Optional) Add a `promql_expr_test` at `eval_time: 30m` pinning the
      floor sub-expression's value for the new input, so the arithmetic is
      asserted directly and not only through the alert's silence. Use the value
      promtool actually prints on the pinned version — do not hand-derive it.
      (depends on 3)
      — DoD: the added expression test passes on the pinned promtool and its
      expected value is the one observed, not assumed. Drop this task if the
      value differs between promtool 2.x and 3.x in a way that would make the
      file version-locked; the alert-level case in task 3 is the primary
      guarantee and must not be weakened by a version-fragile companion.

- [ ] 8. Open the PR (depends on 5). Conventional-commit subject, e.g.
      `test(alerts): make the denial-floor case pin the floor`. Body must
      state, per the issue's definition of done, that the `> 4` to `> -1`
      mutation was run and what it produced — including the honest,
      version-split result from tasks 2 and 5. Merge with
      `gh pr merge <N> --merge --delete-branch` per `.claude/CLAUDE.md`; never
      squash or rebase. No emoji.
      — DoD: PR links issue #590 and mctlhq/mctl-gitops#1110, and states that
      no alert expression changed.

- [ ] 9. (Follow-up, separate issue — do NOT fold into this PR) Propose bumping
      `PROM_VERSION` in `.github/workflows/build.yml` from `2.52.0` to a
      Prometheus 3.x release, so CI evaluates the suite under the same
      left-open range semantics as the deployed rules. Measured during
      investigation: the full existing suite is green under promtool 3.5.0 with
      the rule intact, so the bump is low-risk — but every case deserves a
      per-case mutation re-check under the new semantics, which is a PR of its
      own.
      — DoD: an issue exists in `mctlhq/mctl-telegram` describing the bump and
      the per-case re-check it requires.

## Tests

- [ ] T1. `promtool test rules deploy/alerts/mctl-telegram.rules_test.yaml`
      against `/tmp/rules.yaml` extracted from the unmodified rule file —
      SUCCESS, all cases.
- [ ] T2. Mutation: floor `> 4` relaxed to `> -1` — the denial-floor case
      FAILS, reporting `exp:[]` against a fired
      `MctlAgentPolicyDenialRateHigh{reason="unknown"}`. This is the assertion
      the issue's definition of done requires; run it on the pinned CI version
      and, if available, on a Prometheus 3.x promtool too.
- [ ] T3. Mutation control: share threshold `> 0.20` raised to `> 0.90` — the
      firing case T3 (`0+2x40` claims against `0+1x40` denials, a 50% share)
      must FAIL, confirming the replaced case's neighbours still constrain the
      share clause and that the two cases pin different clauses.
- [ ] T4. `promtool check rules /tmp/rules.yaml` — SUCCESS, 19 rules, unchanged
      from before the edit (the rule file is not touched).
- [ ] T5. `go test ./deploy/alerts/... ./docs/...` — passes.
      `TestRunbookURLsResolve` (`deploy/alerts/runbook_links_test.go`) and
      `TestRunbookAnchorsPresent` / `TestRunbookMetricNamesRegistered`
      (`docs/runbook_test.go`) read the rule file and `docs/runbook.md`, neither
      of which this change modifies, so this is a regression guard rather than
      new coverage.
- [ ] T6. Diff review: the change is confined to
      `deploy/alerts/mctl-telegram.rules_test.yaml`, and within it to one
      case's `values:` lines plus its comment (plus the header sentence if
      task 6 is taken).

## Rollback

Single-file, test-only, non-deployed. `git revert` the merge commit, or restore
`deploy/alerts/mctl-telegram.rules_test.yaml` from the previous revision:
nothing in the cluster, no ArgoCD application, and no running service observes
this file. The only visible effect of a rollback is that CI returns to the
previous case, which is mutation-blind on Prometheus 3.x and mutation-catching
on the pinned 2.52.0. If the replaced case turns out to be flaky on a future
promtool version, prefer fixing the series forward (adjust the rise so it stays
strictly inside the window on that version) over reverting — reverting restores
a case whose coverage depends on a pinned toolchain, which is the defect this
proposal exists to remove.
