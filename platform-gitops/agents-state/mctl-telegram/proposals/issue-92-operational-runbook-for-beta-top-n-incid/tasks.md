# Tasks: issue-92-operational-runbook-for-beta-top-n-incid

- [ ] 1. Create `docs/runbook.md` with playbook sections — DoD: the file is
  committed; sections exist (with stable `<a id="...">` anchors, see design
  table) for the #86 alerts (`MctlTelegramPoolNearCapacity`,
  `MctlTelegramFloodWaitSpike`, `MctlTelegramOAuthPendingStuck`), the #59 VMRule
  alerts (`JWTExpiredSpike`/`JWTInvalidSpike`, `TelegramClientErrors`,
  `RateLimitSpike`), and `SLOBurnRate`. The canary entry is a SHORT pointer that
  links to the existing `docs/runbooks/canary.md` (do NOT duplicate canary
  content). All six mandatory subsections (Symptom, Likely causes, Diagnostic
  queries, Mitigation, Escalation, Postmortem trigger) are present and non-empty
  for the authored sections; every Prometheus metric name matches a name
  registered in `internal/metrics/metrics.go`.

- [ ] 2. Confirm `runbook_url` annotations on the three #86 alerts in
  `deploy/alerts/mctl-telegram.rules.yaml` (depends on #86 having merged) — DoD:
  each of `MctlTelegramPoolNearCapacity`, `MctlTelegramFloodWaitSpike`,
  `MctlTelegramOAuthPendingStuck` carries an `annotations.runbook_url` of the form
  `https://github.com/mctlhq/mctl-telegram/blob/main/docs/runbook.md#<anchor>`,
  where `<anchor>` matches the id table in `design.md`. Do NOT modify
  `canary.rules.yaml`. The #59 VMRule alerts live in `mctl-gitops` — adding their
  `runbook_url` is a separate manual gitops edit (out of scope for this PR). CI
  passes on the updated YAML.

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
