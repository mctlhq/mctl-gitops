# Tasks: issue-92-operational-runbook-for-beta-top-n-incid

- [ ] 1. Create `docs/runbook.md` with all seven playbook sections — DoD: the
  file is committed; each of the seven sections (`MctlTelegramPoolNearCapacity`,
  `MctlTelegramFloodWaitSpike`, `MctlTelegramOAuthPendingStuck`,
  `MctlTelegramAuthFailuresSpike`, `MctlTelegramClientErrorsSpike`,
  `MctlTelegramCanaryFailing`, `SLOBurnRate`) exists with its stable HTML
  anchor (`<a id="...">`), and all six mandatory subsections (Symptom, Likely
  causes, Diagnostic queries, Mitigation, Escalation, Postmortem trigger) are
  present and non-empty; every Prometheus metric name matches a name registered
  in `internal/metrics/metrics.go`.

- [ ] 2. Update `deploy/alerts/mctl-telegram.rules.yaml` with `runbook_url`
  annotations (depends on #86 landing first) — DoD: every `alert:` block in the
  file whose name matches one of the seven runbook sections carries an
  `annotations.runbook_url` value of the form
  `https://github.com/mctlhq/mctl-telegram/blob/main/docs/runbook.md#<anchor>`,
  where `<anchor>` matches the id table in `design.md`; CI passes on the updated
  YAML.

## Tests

- [ ] T1. Anchor presence check: a CI script (or a Go test in `docs/`) reads
  `docs/runbook.md` and asserts that all seven anchor ids from the design table
  are present. Fails the build if any anchor is missing or renamed. This
  prevents link rot when the runbook is edited.

- [ ] T2. Metric-name consistency check: the same script (or a separate grep)
  asserts that every Prometheus metric name that appears in `docs/runbook.md`
  also appears in `internal/metrics/metrics.go`. Prevents stale metric names
  surviving a rename.

- [ ] T3. Manual review of diagnostic query correctness: a reviewer who has
  operated mctl-telegram in a staging environment validates that each
  Prometheus query returns meaningful data, and that each `kubectl logs` or
  `psql` command produces the expected output format. This is a human gate, not
  automated; record the outcome in the PR description.

- [ ] T4. `runbook_url` link validation (applies after task 2): a CI linkcheck
  step (e.g. `markdown-link-check` or `lychee`) verifies that each
  `runbook_url` value in `deploy/alerts/mctl-telegram.rules.yaml` resolves to a
  real anchor in `docs/runbook.md` at the HEAD of the default branch. Runs as
  part of the same PR that adds the annotations.

## Rollback

Both deliverables are documentation only (Markdown and YAML annotations). No
infrastructure state is mutated.

- To roll back task 1: revert the `docs/runbook.md` commit or open a follow-up
  PR that removes or replaces the file. Alert rules still work without
  `runbook_url`; the absence of the file degrades operator experience but does
  not break any system.
- To roll back task 2: remove the `runbook_url` annotation lines from
  `deploy/alerts/mctl-telegram.rules.yaml`. PrometheusRules continue to fire
  correctly; the link from the page to the runbook is simply gone.

No database migration, no binary change, no config change — rollback is a
single git revert.
