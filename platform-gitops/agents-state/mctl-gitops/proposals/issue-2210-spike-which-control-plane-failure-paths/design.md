# Design: issue-2210-spike-which-control-plane-failure-paths

## Current state

### Topology
- One k3s cluster, `mctl-preprod`: one control-plane node
  `control-plane-fsn1` (cx33, `count = 1`, `taints = []`) and three workers
  `worker-cx43-fsn1` (`infrastructure/k3s-preview/kube.tf`,
  `control_plane_nodepools` / `agent_nodepools`). The CP has no taint, so
  ordinary workloads can schedule beside the apiserver and etcd.
- k3s runs the apiserver, controller-manager, scheduler and embedded etcd in
  one `k3s server` process on that node. Losing the node or the process takes
  down all of them at once. This is accepted residual F11
  (`docs/runbooks/control-plane.md`).
- etcd snapshots: `etcd_s3_backup` in `kube.tf` uploads to R2
  `mctl-etcd-snapshots/k3s-preview` with `etcd-snapshot-schedule-cron =
  "0 */12 * * *"` and `etcd-snapshot-retention = "28"`.
  `docs/runbooks/restore.md` §3 says "every 6h, retention 56", which is drift.
  `control-plane.md` says the restore drill has never been run.
- apiserver args: `control_planes_custom_config.kube-apiserver-arg` in
  `kube.tf` sets the audit policy (F20) and OIDC against `https://auth.mctl.ai`.
  ZITADEL itself runs in-cluster, so OIDC kubectl access is unavailable while
  the cluster is degraded; the break-glass path is `tofu output --raw
  kubeconfig`. `control-plane.md` records a past incident in which a
  `config.yaml.d` drop-in silently replaced these args.
- `automatically_upgrade_os = false` prevents kured from draining the only CP.
  PDBs protect mctl-api and the Argo CD server and repo-server (F11
  compensating controls).

### Monitoring (`platform-gitops/bootstrap/templates/observability/monitoring.yaml`)
- Stack: `victoria-metrics-k8s-stack` 0.72.5, VMSingle, in-cluster
  Alertmanager.
- `kubeApiServer.vmScrape` is enabled. Histogram buckets are dropped (#1772),
  but `apiserver_request_sli_duration_seconds_bucket` is kept on purpose for
  `KubeAPIErrorBudgetBurn`, and
  `apiserver_client_certificate_expiration_seconds_bucket` is kept for
  `KubeClientCertificateExpiration`. The admission webhook and
  `apiserver_admission_*` `_bucket` series are dropped, but their counters are
  kept.
- `kubeEtcd.enabled: false`, `kubeControllerManager.enabled: false`,
  `kubeScheduler.enabled: false`. `defaultRules.groups.etcd.create: false`,
  and scheduler/controller-manager groups are off. Nothing in `kube.tf` sets
  k3s `etcd-expose-metrics`, so there is no etcd metrics endpoint to scrape
  anyway.
- Alertmanager routes:
  - `KubeControllerManagerDown|KubeSchedulerDown|KubeProxyDown` go to
    `"null"` as k3s false positives.
  - `InfoInhibitor|Watchdog` go to `"null"`, so there is no dead-man's switch.
  - The #1771 severity routes page every `severity = "critical"` alert,
    including `KubeAPIDown`, to Telegram (`continue: true`).
- `platform-gitops/infra-components/observability/vm-rules/`: no rule
  mentions etcd or the control plane. `backup-alerts.yaml` has freshness
  alerts for Vault, VictoriaMetrics, Forgejo and shared-pg, but none for etcd
  snapshots. `mctl-alerts.yaml` has node alerts (`NodeDiskSpaceCritical`,
  `NodeHighMemory`, `NodeCordoned`, `K3sUpgradeJobFailed`, ...) that apply to
  the CP node through node-exporter.
- Blackbox (`infra-components/observability/blackbox/vmprobes.yaml`) probes
  public HTTPS endpoints (`api.mctl.ai/healthz`, `secrets.mctl.ai`,
  `auth.mctl.ai`, ...). It runs in-cluster, so it cannot report a dead
  cluster.

### Admission
- `platform-gitops/bootstrap/templates/system/admission-policies.yaml`: 15
  `ValidatingAdmissionPolicy` objects plus bindings, all `failurePolicy:
  Fail`. They are in-process CEL with no network dependency. The risk is a
  CEL error or a too-broad match that denies pod or namespace writes
  cluster-wide, and nothing alerts on that.
- Webhook-bearing charts in bootstrap:
  - external-secrets (`core-infra/external-secrets.yaml`, `webhook:` on 9443)
  - cert-manager (k3s HelmChartConfig
    `infrastructure/k3s-preview/extra-manifests/cert-manager-helmchartconfig.yaml.tpl`)
  - CloudNativePG (`data/cloudnative-pg.yaml`)

  The Vault injector is disabled (`core-infra/vault.yaml`, `injector.enabled:
  false`). There is no Kyverno or Gatekeeper.
- No alert reads `apiserver_admission_webhook_rejection_count`,
  `apiserver_admission_webhook_request_total` or
  `apiserver_validating_admission_policy_check_total`.

### Deployed state checked:
- `mctl_list_incidents(status=resolved, limit=50)`: incidents from
  2026-10-24 to 2026-10-28. None concern the apiserver, etcd, admission or
  the control plane. The only match on "webhook" is
  `MctlApiSecurityWebhookFailures`, an application-level GitHub webhook
  alert, not Kubernetes admission. This window is too short to be evidence
  of anything.
- Live webhook configurations, the live k3s server args, `k3s etcd-snapshot
  ls`, and whether `KubeAPIDown` reaches Telegram during an outage were not
  observable from this run. The MCP tools are service-scoped and there was no
  kubectl. These are recorded as open questions and must not be read as
  absent.
- `$MCTL_GITOPS_ROOT` services and tenants: not relevant. This is
  cluster-level, not per-service config.

## Proposed solution

Deliver the spike outcome as a machine-checked inventory plus a readable
runbook. This follows the existing pattern of
`platform-gitops/governance/policy-checkpoint-coverage.yaml` together with
`tests/test_policy_checkpoint_coverage.py` and
`docs/runbooks/policy-checkpoint-coverage.md`.

1. `platform-gitops/governance/control-plane-failure-paths.yaml`: the source
   of truth. Each entry has:
   - `id`
   - `class`: `etcd | apiserver | admission | cp-node | alerting-path`
   - `failure`
   - `blast_radius`
   - `detection`: a list of `{alert, source: vm-rules|chart-default, route}`
     entries, or empty
   - `status`: `monitored | partial | unmonitored | unverified`
   - `evidence`: repo paths, or `verified_live: <date>`
   - `recovery`: a runbook anchor
   - `tracked_by`: an issue URL or `residual: F11`; required unless the
     status is `monitored`

   Seed rows from the findings above:

   | id | class | detection today | seed status |
   |---|---|---|---|
   | cp-node-loss | cp-node | KubeAPIDown (critical), but delivery depends on the in-cluster stack | unverified; residual F11 |
   | whole-cluster-loss / alerting-path-loss | alerting-path | none: Watchdog goes to null, no off-cluster heartbeat | unmonitored |
   | etcd-disk-full / db-quota | etcd | NodeDiskSpaceHigh/Critical (node-level only), no etcd DB-size signal | partial |
   | etcd-slow-fsync / leader-loss | etcd | none (`kubeEtcd` off, no `etcd-expose-metrics`) | unmonitored |
   | etcd-snapshot-stale (R2 upload stops) | etcd | none (`backup-alerts.yaml` has no etcd rule) | unmonitored |
   | etcd-restore-untested | etcd | n/a, drill never run | unmonitored; residual |
   | apiserver-overload / 5xx | apiserver | KubeAPIErrorBudgetBurn, KubeAPITerminatedRequests (chart default) | monitored (route to confirm) |
   | apiserver-cert-expiry | apiserver | KubeClientCertificateExpiration (chart default) | partial: covers client certs, not the k3s serving cert rotation |
   | apiserver-args-drift (config.yaml.d replace) | apiserver | none; manual journalctl check in control-plane.md | unmonitored |
   | oidc-issuer-unreachable | apiserver | auth.mctl.ai blackbox probe (in-cluster) | partial; break-glass kubeconfig |
   | cp-resource-starvation (untainted CP) | cp-node | NodeHighCPU / NodeHighMemory / NodeMemoryHeadroomLow | partial |
   | controller-manager / scheduler stuck | apiserver | muted to null as k3s false positive | unmonitored |
   | webhook-backend-down (ESO / cert-manager / CNPG, failurePolicy Fail) | admission | none on admission metrics; pod-level KubePodNotReady only | unverified; needs live inventory |
   | vap-misfire (CEL error or broad deny) | admission | none | unmonitored |

2. `docs/runbooks/control-plane-failure-paths.md`: the readable checklist.
   It explains each class, reproduces the table, and gives the first
   diagnostic command per row, for example `k3s etcd-snapshot ls`, the
   `journalctl ... Running kube-apiserver` check from `control-plane.md`,
   `kubectl get validatingwebhookconfigurations -o
   custom-columns=...failurePolicy...`, and the break-glass kubeconfig.
   It states that `kube.tf` is authoritative for snapshot cadence and flags
   the `restore.md` drift. Also add one link line in
   `docs/runbooks/control-plane.md` and one pointer in `CLAUDE.md` next to
   the other runbook pointers.

3. `tests/test_control_plane_failure_paths.py`, wired into
   `.github/workflows/validate-manifests.yml` like
   `test_policy_checkpoint_coverage.py`. It checks four things:
   - Every entry has the required keys, and `class` and `status` are in the
     allowed sets.
   - A non-`monitored` entry has `tracked_by`.
   - Every `detection.alert` with `source: vm-rules` exists as an
     `- alert: <name>` in `platform-gitops/infra-components/observability/vm-rules/`.
     Every `source: chart-default` alert is on an explicit allowlist in the
     test, pinned to chart 0.72.5. This keeps the inventory from claiming an
     alert that does not exist.
   - If an alert in the inventory is matched by a `receiver: "null"` route
     in `monitoring.yaml`, the entry must not be `monitored`. This catches
     the controller-manager/scheduler and Watchdog cases mechanically.

4. Before merge, the implementer opens one follow-up issue per
   `unmonitored` or `partial` row (or groups them by class) and fills in
   `tracked_by`. Likely follow-ups:
   - an off-cluster dead-man's switch fed by `Watchdog`
   - an etcd snapshot freshness alert (R2 object age, or k3s
     `ETCDSnapshotFile` CR age)
   - `etcd-expose-metrics: true` plus `kubeEtcd` scrape and etcd rules
   - admission error-rate alerts on the kept counters
   - an etcd restore drill
   - fixing the `restore.md` drift

The spike adds no runtime change. It only documents and adds a guard.

## Alternatives

1. **Markdown-only checklist.** Cheapest option, but nothing stops it from
   rotting. It could keep calling a path `monitored` after a route is muted
   or a rule is deleted. Dropped in favour of a YAML file checked by a test,
   which this repo already uses for policy-checkpoint coverage.
2. **Fix the gaps in this proposal.** For example: enable etcd metrics,
   un-mute Watchdog, add snapshot and admission alerts. Each of these touches
   live cluster config (a `kube.tf` apply on the only CP, with the documented
   risk of the apiserver refusing to start) or alert routing. Each needs its
   own review and rollback. The issue asks for a checklist, so these are
   split into follow-ups.
3. **Generate the inventory from the live cluster (kubectl/VM API) in CI.**
   This would be most accurate for the webhook inventory, but CI has no
   cluster credentials, and adding them for a spike widens access. Dropped.
   Live checks are a manual implementer step recorded as `verified_live`.

## Platform impact

- No migration and no runtime or resource change. The change adds two docs,
  one governance YAML, one test, and one workflow step.
- CI: one extra Python test, which needs only PyYAML and is already used by
  sibling tests. It runs in under a second.
- Risk: the chart-default allowlist goes stale when
  `victoria-metrics-k8s-stack` is bumped. Mitigation: the allowlist is pinned
  to the chart version string in `monitoring.yaml`, and the test fails if
  that version changes without the allowlist being re-reviewed.
- Risk: the checklist creates false confidence. Mitigation: anything not
  observed live is `unverified`, never `monitored`.

## Open questions

- Live admission webhook inventory and `failurePolicy` values: not observed
  in this run.
- Whether `KubeAPIDown` is delivered during a real apiserver outage: not
  observed.
- Whether an off-cluster uptime check exists outside this repo: not observed.
- Live etcd snapshot cadence: `kube.tf` says 12h/28, `restore.md` says 6h/56.
