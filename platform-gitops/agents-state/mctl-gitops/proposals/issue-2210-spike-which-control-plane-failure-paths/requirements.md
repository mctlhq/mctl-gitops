# Control-plane failure-path checklist (etcd, API server, admission)

## Context

Issue #2210 is a scout-generated spike. It asks which Kubernetes control-plane
failure paths (etcd, kube-apiserver, admission webhooks) could take down
mctl's cluster, and whether each one is monitored. The outcome it asks for is
a failure-path checklist.

The answer matters because mctl runs everything on one k3s cluster
(`mctl-preprod`) with a single control-plane node (`control_plane_nodepools`
count 1 in `infrastructure/k3s-preview/kube.tf`; accepted residual F11 in
`docs/runbooks/control-plane.md`). ArgoCD, Vault, ZITADEL, Argo Workflows,
mctl-api and every tenant depend on that one apiserver and its embedded etcd.
Reading the repo already turns up several monitoring gaps:
- etcd is neither scraped nor alerted (`kubeEtcd.enabled: false` and
  `defaultRules.groups.etcd.create: false` in
  `platform-gitops/bootstrap/templates/observability/monitoring.yaml`).
- The `Watchdog` heartbeat is routed to the `"null"` receiver, so nothing
  notices when the whole alerting path is lost.
- etcd snapshots uploaded to R2 have no freshness alert
  (`vm-rules/backup-alerts.yaml` covers Vault, VictoriaMetrics, Forgejo and
  shared-pg only).

This proposal delivers the checklist as a committed runbook and records each
gap as a follow-up. It does not fix the gaps.

## User stories

- AS a platform operator I WANT one checklist of the control-plane failure
  paths that can take the cluster down, with the current detection signal for
  each, SO THAT I know which outages would page me and which would stay silent.
- AS a platform operator I WANT every unmonitored path linked to a follow-up
  issue SO THAT closing the gaps is tracked work, not tribal knowledge.
- AS an on-call responder I WANT the first diagnostic step and recovery
  pointer for each path SO THAT I can act without rediscovering how k3s
  embeds etcd, the apiserver and admission.

## Acceptance criteria (EARS)

- WHEN the checklist is merged THE SYSTEM SHALL contain
  `docs/runbooks/control-plane-failure-paths.md` with one row per failure
  path in at least these classes: etcd, kube-apiserver, admission (webhooks
  and ValidatingAdmissionPolicies), control-plane node/host, and the alerting
  path itself.
- WHEN a row is written THE SYSTEM SHALL record for it: the failure mode,
  blast radius on mctl, current detection (alert name and route, or "none"),
  evidence (a repo path, or "verified live on <date>"), status
  (`monitored` / `partial` / `unmonitored` / `unverified`), and a recovery
  pointer.
- IF a row's detection could not be confirmed against the live cluster THEN
  THE SYSTEM SHALL mark it `unverified` and not `monitored`.
- IF a row's status is `unmonitored` or `partial` THEN THE SYSTEM SHALL link a
  follow-up GitHub issue in `mctlhq/mctl-gitops`, or name an existing accepted
  residual (for example F11) that covers it.
- WHEN `docs/runbooks/control-plane.md` is read THE SYSTEM SHALL link to the
  new checklist.
- WHEN the checklist and `docs/runbooks/restore.md` disagree on etcd snapshot
  schedule or retention THE SYSTEM SHALL state the value from
  `infrastructure/k3s-preview/kube.tf` (`etcd-snapshot-schedule-cron`,
  `etcd-snapshot-retention`) as authoritative and flag the drift.
- WHILE the checklist exists THE SYSTEM SHALL be guarded by a test that fails
  if a row lacks a status or if a status is outside the allowed set.

## Out of scope

- Implementing new alerts, enabling etcd metrics, wiring a dead-man's-switch,
  or changing alert routes. Each of these is a follow-up issue.
- Adding a second control-plane node (deferred under F11, ROADMAP Horizon 2).
- Running the etcd restore drill.
- The `infrastructure/k3s-prod/` cluster, which is still a TODO README.
- Any change to cluster configuration in `infrastructure/k3s-preview/`.

## Open questions

- Live webhook inventory: the repo shows webhooks from external-secrets,
  cert-manager and CloudNativePG charts, plus 15 in-process
  ValidatingAdmissionPolicies, but this run had no kubectl access.
  The implementer must list `validatingwebhookconfigurations` and
  `mutatingwebhookconfigurations` live, with their `failurePolicy`,
  `namespaceSelector` and `timeoutSeconds`. Any row they cannot verify stays
  `unverified`.
- Does `KubeAPIDown` actually reach Telegram when the apiserver is down?
  vmagent service discovery and some vmalert behaviour depend on the
  apiserver. The repo shows the route (#1771 critical route in
  `monitoring.yaml`); a fault-injection check has not been done. Default:
  mark `unverified` until tested.
- Is there an external (off-cluster) uptime check, such as Cloudflare health
  checks or a third-party pinger, that this repo does not show? Default:
  treat as absent-but-unverified and ask in the follow-up issue.
- Snapshot cadence drift: `kube.tf` says 12h/28 copies, `restore.md` §3 says
  6h/56. Which one is live? Confirm on the CP node with `k3s etcd-snapshot ls`.
