# Tasks: issue-2210-spike-which-control-plane-failure-paths

- [ ] 1. Gather live facts on the CP node and cluster, read-only:
  `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`
  with `failurePolicy`, `namespaceSelector` and `timeoutSeconds`;
  `k3s etcd-snapshot ls`; the `journalctl ... Running kube-apiserver` arg
  check from `docs/runbooks/control-plane.md`; and the etcd DB size
  (`/var/lib/rancher/k3s/server/db/etcd`). — DoD: each fact is recorded with
  its date in the PR description. Any fact that cannot be gathered is listed
  as such.
- [ ] 2. Add `platform-gitops/governance/control-plane-failure-paths.yaml`
  with the seed rows from design.md, corrected by the facts from task 1
  (depends on 1). — DoD: every row has `id`, `class`, `failure`,
  `blast_radius`, `detection`, `status`, `evidence`, `recovery`. A row not
  observed live is `unverified`, not `monitored`.
- [ ] 3. Add `tests/test_control_plane_failure_paths.py` (depends on 2). It
  checks the schema and allowed values, requires `tracked_by` on every row
  that is not `monitored`, and checks that each `vm-rules` alert exists in
  `platform-gitops/infra-components/observability/vm-rules/`. Each
  chart-default alert must be on an allowlist pinned to
  `victoria-metrics-k8s-stack` `0.72.5`, and an alert routed to
  `receiver: "null"` in `monitoring.yaml` cannot back a `monitored` row. —
  DoD: `python3 tests/test_control_plane_failure_paths.py` passes on the new
  YAML and fails on the negative cases in T2–T5.
- [ ] 4. Add a step to `.github/workflows/validate-manifests.yml` next to
  `test_policy_checkpoint_coverage.py` (depends on 3). — DoD: the step runs
  on the PR and is green.
- [ ] 5. Write `docs/runbooks/control-plane-failure-paths.md` (depends on 2).
  It covers each class, the table, the first diagnostic command and recovery
  pointer per row, and the break-glass kubeconfig note. It states that
  `kube.tf` is authoritative for snapshot cadence and flags the drift in
  `docs/runbooks/restore.md` §3. — DoD: the doc agrees with the YAML row for
  row.
- [ ] 6. Link the new runbook from `docs/runbooks/control-plane.md` and add a
  pointer in `CLAUDE.md` under Secrets Management/runbook pointers
  (depends on 5). — DoD: both links resolve.
- [ ] 7. Open follow-up issues in `mctlhq/mctl-gitops` for the `unmonitored`
  and `partial` rows. These cover: an off-cluster dead-man's switch fed by
  Watchdog, an etcd snapshot freshness alert, etcd metrics plus rules,
  admission error-rate alerts, the etcd restore drill, and the `restore.md`
  cadence drift. Then fill in `tracked_by` (depends on 2). — DoD: no row
  that needs `tracked_by` lacks it. Accepted residuals cite F11.

## Tests

- [ ] T1. The positive run on the committed YAML passes.
- [ ] T2. A row whose status is outside the allowed set fails.
- [ ] T3. An `unmonitored` row without `tracked_by` fails.
- [ ] T4. A `vm-rules` alert name that does not exist (for example
  `EtcdSnapshotStale` before the follow-up lands) fails.
- [ ] T5. A `monitored` row backed only by `KubeSchedulerDown` (routed to
  `"null"`) fails.
- [ ] T6. Changing the chart `targetRevision` in `monitoring.yaml` without
  updating the pinned allowlist version fails.

## Rollback

Docs, governance YAML and a CI test only; nothing touches the cluster. To
roll back, revert the PR. If the CI step alone blocks unrelated PRs, remove
the step from `validate-manifests.yml` in a follow-up PR and keep the
documents.
