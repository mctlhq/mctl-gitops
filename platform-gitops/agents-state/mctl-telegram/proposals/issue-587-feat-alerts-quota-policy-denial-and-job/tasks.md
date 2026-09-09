# Tasks: issue-587-feat-alerts-quota-policy-denial-and-job

- [ ] 1. Confirm the label values every new expression depends on, before
      writing any YAML: `status` values in `internal/db/agent_jobs.go`
      (`pending|processing|completed|failed|dead_letter|ignored` — note the
      issue's `succeeded` does not exist), `class` values in
      `ClaudeInvoker.countResultError`, `result` values in
      `recordCost`, and the `reason`/`surface` sets in
      `internal/agent/policy/policy.go` and `internal/metrics/metrics.go`.
      — DoD: a short note in the PR description listing each label value used
      by the new rules and the file/line it was read from; no rule selects a
      value that is not on that list.

- [ ] 2. Add `MctlAgentClaudeUsageLimit` to the `mctl-telegram-agent` group of
      `deploy/alerts/mctl-telegram.rules.yaml`
      (`sum(increase(mctl_agent_claude_result_errors_total{class="usage_limit"}[15m])) > 0`,
      `for: 0m`, `severity: warning`, `service: mctl-telegram`), with a comment
      justifying the presence-test form from the dedicated credential domain
      (`AGENT_CREDENTIAL_DOMAIN_ID` required in `cmd/agent-worker/main.go`;
      C1 report's isolated OAuth token) and the sequential `Worker.Loop`, and
      explaining `> 0` rather than `>= 1` per the file header's `increase()`
      extrapolation note. (depends on 1) — DoD: `promtool check rules` passes
      on the extracted `.spec`; comment names a file, not a guess.

- [ ] 3. Add `MctlAgentPolicyDenialRateHigh` (share by `reason` over
      `sum(rate(mctl_agent_jobs_total{status="processing"}[30m]))`, `> 0.20`,
      `and sum by (reason)(increase(mctl_agent_policy_denials_total[30m])) >= 5`,
      `for: 0m`, `severity: warning`). Comment must state (a) that it
      aggregates by `reason` and why `surface` was not chosen, (b) that no
      allowed-evaluation counter exists so the claim count is a proxy
      denominator, (c) that no production baseline exists and 0.20 is the
      conservative side, (d) why the floor exists, (e) that the ratio can
      exceed 1 because `internal/agentapi/actions.go` counts each evaluation
      including redeliveries. (depends on 1) — DoD: `promtool check rules`
      passes; every claim in the comment is traceable to a file in the repo.

- [ ] 4. Add `MctlAgentJobCostHigh`
      (`sum(increase(mctl_agent_job_cost_usd_total[1h])) / sum(increase(mctl_agent_jobs_total{status="completed"}[1h])) > 0.50`
      with an absolute-spend floor of `> 0.50` in the window, `for: 0m`,
      `severity: warning`). Comment must justify the denominator choice
      (dollars per delivered outcome; claims rejected because retries flatten
      the ratio), state that the numerator includes `result="error"` because
      `recordCost` runs before the `is_error` check
      (`internal/agentworker/claudeinvoker.go:197` vs `:199`), state the `+Inf`
      behaviour when completions are zero and that it is intended, state
      plainly that the dollar figure is unmeasured in this repository and must
      be re-derived from real data, and describe `AGENT_MAX_BUDGET_USD` as a
      per-invocation CLI cap that aggregates nothing — never as a substitute.
      (depends on 1) — DoD: `promtool check rules` passes; no invented cost
      figure is presented as observed.

- [ ] 5. Add a short comment at the top of the `mctl-telegram-agent` group
      recording that these three rules are mirror-only, that the deployed copy
      is the operator's separate change to
      `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-ops.yaml`
      in `mctl-gitops`, and that merging this repository's file deploys
      nothing. (depends on 2, 3, 4) — DoD: the file header's "adding an alert
      here deploys nothing" rule is visibly honoured; no wording anywhere in
      the diff implies the cluster changes.

- [ ] 6. Add three runbook sections to `docs/runbook.md` after the
      `#communication-agent-operations` section, each opened by an explicit
      `<a id="..."></a>` (`mctlagentclaudeusagelimit`,
      `mctlagentpolicydenialratehigh`, `mctlagentjobcosthigh`) and following
      the established `### Symptom / Likely causes / Diagnostic queries /
      Mitigation / Escalation / Postmortem trigger` shape. Include the
      `mctl_agent_credential_domain` join query in the usage-limit section's
      diagnostics, the `by (reason, surface)` breakdown query in the
      denial-rate section, and the absolute-spend query in the cost section.
      (depends on 2, 3, 4) — DoD: each section names the alert, its
      expression, and the deployed-copy caveat; anchors match the
      `runbook_url` values exactly.

- [ ] 7. Add the three Table-of-contents entries and three lines to the
      existing `### Agent alert response` list beside `MctlAgentDeadLetter`
      and `MctlAgentActionsExecutingStuck`. (depends on 6) — DoD: TOC links
      resolve to the new anchors; the response list gives one concrete first
      action per alert.

- [ ] 8. Write six promtool cases in
      `deploy/alerts/mctl-telegram.rules_test.yaml` — one firing and one
      must-stay-silent per alert — with a comment on each pair saying what a
      mutation of the rule it would catch, matching the file's existing
      standard. Silent cases: `class="other"` only; a normal denial share at
      real volume plus a single denial in a near-idle window; ordinary
      spend/completion. (depends on 2, 3, 4) — DoD:
      `yq '.spec' deploy/alerts/mctl-telegram.rules.yaml > /tmp/rules.yaml &&
      promtool test rules deploy/alerts/mctl-telegram.rules_test.yaml` passes
      locally, and the two pre-existing `MctlBridgeDaemonsFlapping` cases still
      pass unchanged.

- [ ] 9. Copy each expected `exp_annotations.description` from the actual
      failing-diff output of a local `promtool test rules` run rather than
      writing it by hand, keeping the trailing `\n` left by the `>` folded
      scalar. (depends on 8) — DoD: no expected-string mismatch remains; the
      trailing-newline comment from the existing case is echoed for the new
      ones.

- [ ] 10. Mutation-check the new rules manually: temporarily drop the
      `class="usage_limit"` selector, lower each threshold to 0, and remove
      the denial floor, confirming a case fails for each mutation; revert.
      (depends on 8) — DoD: a line in the PR description listing the four
      mutations and which case caught each.

- [ ] 11. Run the full gate: `go test ./deploy/alerts/... ./docs/...`,
      `promtool check rules /tmp/rules.yaml`, `promtool test rules ...`,
      `go fmt`/`go vet`/`golangci-lint` on the (unchanged) Go tree.
      (depends on 6, 8) — DoD: all green; conventional commit
      `feat(alerts): quota, policy-denial and job-cost alerts for the
      communication agent`; merge with `gh pr merge <N> --merge
      --delete-branch` per CLAUDE.md.

- [ ] 12. State in the PR description that this repository's rules file is a
      non-deployed mirror, that the gitops change is the operator's separate
      task, and list the two provisional thresholds (0.20 share, $0.50/job)
      that need re-deriving once real data exists. (depends on 11) — DoD: the
      description contains no claim that the rules take effect in the cluster.

## Tests

- [ ] T1. `MctlAgentClaudeUsageLimit` fires: `mctl_agent_claude_result_errors_total{class="usage_limit"}`
      increments over a 15m window, evaluated past the window boundary.
- [ ] T2. `MctlAgentClaudeUsageLimit` stays silent while only
      `{class="other"}` increments — the case that kills a rule whose label
      selector was dropped or misspelled.
- [ ] T3. `MctlAgentPolicyDenialRateHigh` fires for one `reason` at a share
      above 0.20 with at least 5 denials in the window; expected labels include
      that `reason` and nothing account-, conversation- or peer-derived.
- [ ] T4. `MctlAgentPolicyDenialRateHigh` stays silent at a normal low share
      with real claim volume, and stays silent for a single denial in a
      near-idle window (the floor clause).
- [ ] T5. `MctlAgentJobCostHigh` fires when 1h spend over completed jobs
      exceeds $0.50 and total spend clears the floor.
- [ ] T6. `MctlAgentJobCostHigh` stays silent at ordinary spend per completed
      job over the same volume.
- [ ] T7. `go test ./deploy/alerts/...` — `TestRunbookURLsResolve` proves all
      three new `runbook_url` anchors exist in `docs/runbook.md`.
- [ ] T8. `go test ./docs/...` — `TestRunbookMetricNamesRegistered` proves
      every `mctl_*` name added to the runbook is registered in
      `internal/metrics/metrics.go`, and `TestRunbookAnchorsPresent` still
      passes unchanged.
- [ ] T9. `promtool check rules` on the `yq '.spec'` extraction — proves the
      PrometheusRule CRD still renders to a valid bare rules file.

## Rollback

Nothing here is deployed, so rollback is a source-only operation and cannot
affect the cluster: the live rules are the `mctl-gitops`
`vm-rules/mctl-telegram-ops.yaml` copy, which this work does not touch.

- Whole change: `git revert` the merge commit. CI restores to the previous
  green state — `runbook_links_test.go` passes because the reverted
  `runbook_url` values disappear with the rules that carried them, and the
  promtool file returns to its two `MctlBridgeDaemonsFlapping` cases.
- One bad rule only: delete that rule block and its two promtool cases, and
  delete its runbook section together with its TOC entry. Removing a section
  while leaving the rule (or the reverse) breaks `TestRunbookURLsResolve` —
  they must move as a pair.
- Threshold turned out wrong once data exists: edit the number and the comment
  above it, and update the corresponding firing/silent promtool case in the
  same commit so the pair keeps proving both directions.
- If the operator has already applied the matching `mctl-gitops` change when a
  rule is reverted here, the two files diverge until they update it too; note
  the divergence in the revert PR the way the existing header notes
  `MctlTelegramLoginSendCodeStalls`.
