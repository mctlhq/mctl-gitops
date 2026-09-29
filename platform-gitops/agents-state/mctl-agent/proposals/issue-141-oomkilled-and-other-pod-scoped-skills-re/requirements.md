# Resolve the canonical app name for pod-scoped tickets so GitOps patches target the right values.yaml

## Context

Every AlertManager-sourced pod-scoped ticket derives its `Service` field from the
pod name via `extractService(pod)` in `internal/monitor/alerthandler.go`, which
strips only the ReplicaSet hash and the pod suffix. For any app deployed through
the platform's `base-service` Helm chart the pod is named
`{tenant}-{app}-base-service-<rs>-<id>`, so the ticket's `Service` becomes the
chart fullname (`labs-mctl-telegram-base-service`) rather than the registered app
name (`mctl-telegram`). `detectFilePath` in `internal/skill/builtin/oomkilled.go`
(and its exported twin `fixer.DetectFilePath` in `internal/fixer/patcher.go`)
then builds `platform-gitops/services/{tenant}/{service}/values.yaml` from that
value and gets a 404. Incident `77c234ee` (2026-09-28, labs mctl-telegram
OOMKilled) is the observed case: the agent escalated with
`Could not read platform-gitops/services/labs/labs-mctl-telegram-base-service/values.yaml`
while the real file is `platform-gitops/services/labs/mctl-telegram/values.yaml`.

The blast radius is wider than the file path. The same wrong name is passed to
`GetServiceStatus`, `GetServiceConfig` and `GetServiceLogs` in
`internal/pipeline/evidence.go`, so the `argocd_status`, `config` and `logs`
evidence entries are silently missing for every base-service app — which is also
why `llm_diagnosis` has little to work with on these tickets. It is the same
mismatch `pruneOrphans` in `internal/monitor/poller.go` already documents at
length as its reason for excluding `SourceAlertManager` tickets from orphan
pruning. Five builtin skills consume the raw value when they set
`FixResult.FilePath`: `oomkilled`, `cpu_throttle`, `probe_fix`, `rollback` and
`scale_up`. Finally, because the chart fullname never equals `mctl-api` or
`mctl-agent`, the `PlatformServices` branch of `DetectFilePath` is unreachable
for AlertManager-sourced tickets about the platform's own services.

## User stories

- AS the mctl-agent pipeline I WANT the ticket's service to be the canonical
  registered app name SO THAT `detectFilePath` produces a GitOps path that
  actually exists and a fix PR can be opened.
- AS the mctl-agent pipeline I WANT evidence collection to query mctl-api with
  the canonical app name SO THAT `argocd_status`, `config` and `logs` evidence is
  present for base-service apps instead of silently empty.
- AS an on-call operator I WANT a failed path resolution to escalate with every
  candidate that was attempted SO THAT I can tell an agent-side naming bug from a
  genuinely missing values file without reading the agent's source.
- AS a maintainer I WANT one shared, unit-testable name-resolution helper SO THAT
  the fix cannot drift between `fixer.DetectFilePath` and
  `builtin.detectFilePath`.

## Acceptance criteria (EARS)

- WHEN an AlertManager alert carries `namespace=labs` and
  `pod=labs-mctl-telegram-base-service-744f465c75-dzkhf` THE SYSTEM SHALL create
  the ticket with `Service="mctl-telegram"` and `Tenant="labs"`.
- WHEN an alert's labels include a Backstage/Kubernetes identity label
  (`label_backstage_io_kubernetes_id`, or `label_app_kubernetes_io_instance` /
  `app_kubernetes_io_instance` with the `{namespace}-` prefix removed) THE SYSTEM
  SHALL prefer that value over any name derived from the pod name.
- WHEN no identity label is present THE SYSTEM SHALL fall back to
  `extractService(pod)` with a trailing `-base-service` removed and, only if that
  suffix was present, a leading `{namespace}-` removed.
- IF the pod name does not end in the `-base-service` chart-fullname signature
  THEN THE SYSTEM SHALL leave `extractService`'s result unchanged, including for
  `two-parts`, `myapp-6d4b5c7f8-abc12` and `a-b-c-d-e`.
- IF a service inventory from `mctlclient.ListServices()` is available THEN THE
  SYSTEM SHALL return the first candidate that is a registered `(team, app)` pair
  for the ticket's tenant, and SHALL fall back to the first derived candidate when
  no candidate is registered.
- WHILE the mctl-api inventory is unavailable or stale THE SYSTEM SHALL still
  produce a resolved name from the deterministic string rules alone and SHALL NOT
  fail ticket creation.
- WHEN a workload label (`deployment`, `statefulset`, `daemonset`), an Argo
  Workflow `name`, or the `TypeArgoCDDegraded` Application `name` already
  determines the service THE SYSTEM SHALL apply the same canonicalisation to that
  value and SHALL NOT reintroduce the pod-derived name.
- WHEN `t.Service` resolves to `mctl-api` or `mctl-agent` THE SYSTEM SHALL return
  `platform-gitops/apps/templates/{service}.yaml` from the shared path helper.
- WHEN a skill produces a `FixResult.FilePath` THE SYSTEM SHALL verify the path
  exists in `mctl-gitops` before generating a patch.
- IF the resolved path does not exist THEN THE SYSTEM SHALL try the remaining
  ordered candidate paths and SHALL use the first one that reads successfully.
- IF no candidate path can be read THEN THE SYSTEM SHALL escalate the ticket with
  a message naming every candidate path attempted and the underlying error, and
  SHALL NOT open a pull request.
- WHILE candidate probing runs THE SYSTEM SHALL validate every candidate through
  `gitopspath.Allowlist.Validate` (via `p.github.ValidatePath`) before reading it.
- WHEN the change ships THE SYSTEM SHALL leave pre-existing tickets keyed on the
  old pod-derived name untouched, relying on `reconcileWithAlertManager` to close
  them once their alerts clear.

## Out of scope

- Adding a Kubernetes API client (`client-go`) to mctl-agent. The repo has no
  `k8s.io` dependency today (`go.mod`), all platform reads go through
  `internal/mctlclient`, and an OOMKilled pod is frequently already replaced by
  the time the ticket is processed, so a live pod-label read is neither available
  nor reliable. The label path is supported only when AlertManager already carries
  the label.
- Authoring or changing the VMRule in `mctl-gitops` that would join
  `kube_pod_labels` onto pod-scoped alerts to supply those labels. This proposal
  consumes the labels opportunistically if they appear; it does not require them.
- Changing the +50% memory bump heuristic in `fixer.GenerateMemoryBump`. The issue
  explicitly notes that 256Mi -> 384Mi would not have been the right remediation
  for incident `77c234ee`; the manual fix is mctlhq/mctl-gitops#1450. Improving
  the sizing heuristic is separate work.
- Migrating or re-keying existing open tickets created under the old service name.
- Re-enabling `pruneOrphans` for `SourceAlertManager` tickets. Canonical names
  make the inventory comparison meaningful again, but re-enabling it needs its own
  risk assessment and is deliberately left for a follow-up.

## Open questions

- Which label AlertManager actually delivers, if any. `kube_pod_labels` exposes
  Kubernetes labels as `label_<sanitised>` series, so a join would surface
  `label_backstage_io_kubernetes_id` and `label_app_kubernetes_io_instance`, but
  no rule in `mctl-gitops` is known to perform that join today. Resolution: accept
  all four spellings (`backstage.io/kubernetes-id`,
  `label_backstage_io_kubernetes_id`, `app.kubernetes.io/instance`,
  `label_app_kubernetes_io_instance`) and treat the label path as opportunistic;
  the deterministic string fallback is what production will exercise.
- Whether any base-service release name legitimately differs from
  `{tenant}-{app}`. Proceeding on the convention documented in `poller.go`
  (`{release}-base-service` where `release` is `{tenant}-{app}`); the inventory
  check is what catches a violation, and an unverified candidate simply keeps
  today's behaviour rather than making it worse.
- Whether `worker-service` chart deployments use an analogous `-worker-service`
  fullname suffix. Not observable from this repo. Resolution: make the stripped
  suffix list a package-level variable seeded with `-base-service` so adding
  `-worker-service` later is a one-line change, and note it in the code comment.
- Whether the ticket `Service` rename should be gated behind an env flag.
  Proceeding without a flag, following the precedent of the workload-label
  rewrite already in `processAlert`, whose rollout note covers the identical
  one-extra-ticket consequence.
