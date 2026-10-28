# Control-plane failure-path checklist

Issue: mctlhq/mctl-gitops#2210. Source of truth:
`platform-gitops/governance/control-plane-failure-paths.yaml`, guarded by
`tests/test_control_plane_failure_paths.py`. This table mirrors it row for row.

Status: `monitored`, `partial`, `unmonitored`, or `unverified` (not observed
against the live cluster; never treated as monitored). Nothing here was
verified live when written.

| id | class | failure | detection | status | tracked by |
|---|---|---|---|---|---|
| cp-node-loss | cp-node | The single control-plane node or its k3s server process is lost. | KubeAPIDown | unverified | residual: F11 |
| alerting-path-loss | alerting-path | Whole cluster (and the in-cluster alerting stack) is lost. | none | unmonitored | follow-up-needed: off-cluster dead-man's switch fed by Watchdog |
| etcd-disk-full-quota | etcd | etcd database grows to its quota or the node disk fills. | NodeDiskSpaceHigh, NodeDiskSpaceCritical | partial | follow-up-needed: etcd metrics (etcd-expose-metrics) plus etcd rules |
| etcd-slow-fsync-leader-loss | etcd | etcd fsync latency or leader churn degrades the apiserver. | none | unmonitored | follow-up-needed: etcd metrics (etcd-expose-metrics) plus etcd rules |
| etcd-snapshot-stale | etcd | Scheduled etcd snapshot upload to R2 stops. | none | unmonitored | follow-up-needed: etcd snapshot freshness alert |
| etcd-restore-untested | etcd | Restore procedure has never been drilled and may not work. | none | unmonitored | residual: F11 |
| apiserver-overload-5xx | apiserver | Apiserver overloaded, erroring or terminating requests. | KubeAPIErrorBudgetBurn, KubeAPITerminatedRequests | unverified | follow-up-needed: confirm routing of apiserver chart-default alerts |
| apiserver-cert-expiry | apiserver | Client or serving certificates expire. | KubeClientCertificateExpiration | partial | follow-up-needed: cover k3s serving certificate rotation |
| apiserver-args-drift | apiserver | A config.yaml.d drop-in silently replaces kube-apiserver args (audit, OIDC). | none | unmonitored | follow-up-needed: detect apiserver arg drift |
| oidc-issuer-unreachable | apiserver | auth.mctl.ai (in-cluster ZITADEL) unreachable. | none | partial | residual: F11 |
| cp-resource-starvation | cp-node | Untainted control-plane node starved by ordinary workloads. | NodeHighCPU, NodeHighMemory, NodeMemoryHeadroomLow | partial | residual: F11 |
| controller-manager-scheduler-stuck | apiserver | Controller-manager or scheduler stops working inside the k3s process. | none | unmonitored | follow-up-needed: signal for controller-manager and scheduler health |
| webhook-backend-down | admission | A failurePolicy Fail webhook backend (external-secrets, cert-manager, CloudNativePG) is down. | KubePodNotReady | unverified | follow-up-needed: live webhook inventory and admission error-rate alerts |
| vap-misfire | admission | A ValidatingAdmissionPolicy CEL error or too-broad match denies writes cluster-wide. | none | unmonitored | follow-up-needed: admission error-rate alerts on kept counters |

`tracked_by: follow-up-needed: ...` means the GitHub issue is not yet opened;
replace it with the issue URL when it is.

## First diagnostic per class

- etcd: `k3s etcd-snapshot ls` on the control-plane node; DB size under
  `/var/lib/rancher/k3s/server/db/etcd`. Recovery: `docs/runbooks/restore.md` section 3.
- apiserver: `journalctl -u k3s | grep 'Running kube-apiserver'` to check the
  effective args (audit, OIDC), see `docs/runbooks/control-plane.md`. OIDC login
  depends on in-cluster ZITADEL; break-glass is `tofu output --raw kubeconfig`.
- admission: `kubectl get validatingwebhookconfigurations,mutatingwebhookconfigurations`
  and check `failurePolicy`, `namespaceSelector`, `timeoutSeconds`. The 15
  ValidatingAdmissionPolicies live in
  `platform-gitops/bootstrap/templates/system/admission-policies.yaml`.
- cp-node: node-exporter alerts in `vm-rules/mctl-alerts.yaml`; the node is
  untainted, so workloads share it with etcd.
- alerting-path: Watchdog is routed to `null` in `monitoring.yaml`; there is no
  off-cluster heartbeat, and blackbox probes run in-cluster.

## Snapshot cadence drift

`infrastructure/k3s-preview/kube.tf` is authoritative: `etcd-snapshot-schedule-cron`
`0 */12 * * *`, `etcd-snapshot-retention` 28. `docs/runbooks/restore.md` section 3
says every 6h, retention 56. That is drift, to be corrected in a follow-up.

## Open questions

Live webhook inventory, whether `KubeAPIDown` is delivered during a real
apiserver outage, and any off-cluster uptime check were not observed.
