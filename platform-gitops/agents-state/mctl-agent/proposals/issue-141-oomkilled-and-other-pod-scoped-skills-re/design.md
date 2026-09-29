# Design: issue-141-oomkilled-and-other-pod-scoped-skills-re

## Current state

### Where the service name is born

`internal/monitor/alerthandler.go` `processAlert` builds the ticket identity:

```go
tenant := namespace
service := extractService(pod)
```

`extractService` (same file, bottom) strips the last two dash segments only:

```go
func extractService(pod string) string {
	if pod == "" { return "" }
	parts := strings.Split(pod, "-")
	if len(parts) <= 2 { return pod }
	return strings.Join(parts[:len(parts)-2], "-")
}
```

`processAlert` then overrides `service` in three narrow cases, each already
gated and commented: a workload label (`deployment` / `statefulset` /
`daemonset`), `TypeWorkflowFailed` with a `name` label, and `TypeArgoCDDegraded`
with the Application `name`. None of those apply to `ContainerOOMKilled` or
`KubePodCrashLooping`, which are pod-scoped, so for those the pod-derived value
survives into `ticket.Ticket.Service`.

For a `base-service` chart release the pod is `{tenant}-{app}-base-service-<rs>-<id>`,
so `extractService` yields `{tenant}-{app}-base-service` —
`labs-mctl-telegram-base-service`, not `mctl-telegram`. The repo already knows
this: `pruneOrphans` in `internal/monitor/poller.go` documents it as the reason
`SourceAlertManager` tickets are excluded from orphan pruning, naming the exact
example ("`labs-mctl-telegram-base-service` vs. the registry's `mctl-telegram`").
The existing tests in `internal/monitor/alerthandler_test.go` assert the current
behaviour explicitly (`"admins-mctl-api-base-service-6d4b5c7f8-abc12"` ->
`"admins-mctl-api-base-service"`), which is why the bug was never flagged.

### Where the wrong name does damage

1. **GitOps path.** Two duplicate implementations of the same function exist:
   - `fixer.DetectFilePath(tenant, service)` in `internal/fixer/patcher.go:55`,
     used by `internal/pipeline/pipeline.go:670` as the fallback when a skill
     returns an empty `FilePath`.
   - `builtin.detectFilePath(tenant, service)` in
     `internal/skill/builtin/oomkilled.go:88`, used by `oomkilled.go:69`,
     `cpu_throttle.go:84`, `probe_fix.go:87`, `rollback.go:72`, `scale_up.go:87`
     and `llm_diagnosis.go:258`.

   Both branch on a `PlatformServices` map (`mctl-api`, `mctl-agent`) and
   otherwise return `platform-gitops/services/{tenant}/{service}/values.yaml`.
   Because the chart fullname never equals `mctl-api` or `mctl-agent`, the
   platform-services branch is in practice **unreachable** for any
   AlertManager-sourced ticket: `admins-mctl-api-base-service` falls through to
   the tenant path too.

2. **Evidence collection.** `internal/pipeline/evidence.go` `collectEvidence`
   passes `t.Tenant, t.Service` to `GetServiceStatus`, `GetServiceConfig` and
   `GetServiceLogs` on the `mctlclient.Client`. Each is a REST GET keyed on
   `/{team}/{app}` (`internal/mctlclient/client.go`), so all three 404 for a
   base-service app and the errors are swallowed (`if ... err == nil`). The
   `argocd_status`, `config` and `logs` evidence entries are simply absent. This
   is a second, quieter symptom of the same root cause, and it degrades
   `llm_diagnosis` on exactly the tickets that need it most.

3. **Ticket identity.** `Service` is part of the `(tenant, service, type)` dedup
   and resolve key used by `FindDuplicate`, `ResolveByTenantService` and
   `FindRecentlyResolved`, and it is what the operator reads in Telegram and in
   mctl-api's incident list.

### Where the failure surfaces

`internal/pipeline/pipeline.go` already validates and then reads the path:

```go
filePath := fixResult.FilePath
if filePath == "" { filePath = fixer.DetectFilePath(t.Tenant, t.Service) }
if err := p.github.ValidatePath(filePath); err != nil { ... }
content, err := p.github.GetFileContent(ctx, filePath, "main")
if err != nil {
	...
	p.escalate(ctx, t, fmt.Sprintf(
		"[escalated] Could not read %s from the GitOps repo (%v), so no patch could be "+
			"generated. This is an agent-side failure, not necessarily a service failure.",
		filePath, err), diag)
	return
}
```

So a missing file already escalates rather than corrupting the repo, and it
already blames the agent rather than the service — the escalation text from
incident `77c234ee` is this exact branch. What is missing is any attempt at a
second candidate, and any record of what else could have been tried.

`p.github.ValidatePath` delegates to `internal/gitopspath` `Allowlist.Validate`,
which confines every read and write to `platform-gitops/services/`,
`platform-gitops/apps/templates/` and
`platform-gitops/argo-workflows/workflow-templates/`.

### What is not available

`go.mod` has **no `k8s.io` / `client-go` dependency**. Every platform read in
mctl-agent goes through `internal/mctlclient` (REST to mctl-api) or
`internal/fixer` (GitHub). `internal/capability/capability.go` exposes exactly
the capabilities in `internal/skill/skill.go` (`CapReadLogs`, `CapReadConfig`,
`CapReadStatus`, `CapReadResources`, `CapReadAudit`, `CapModifyGitOps`,
`CapCreatePR`, `CapMergePR`, `CapSendNotify`, `CapCallLLM`, `CapExecWorkflow`) —
none of which is "read a Pod object". The issue's preferred fix, "read the pod's
`backstage.io/kubernetes-id` label", therefore cannot be implemented as a live
API read without adding client-go plus cluster RBAC; and for an OOMKill the pod
is often already replaced by the time the ticket is processed. This shapes the
design below: the label path is supported **only** where AlertManager already
delivers the label, and the deterministic path is the one production relies on.

One source of canonical truth *is* already in-process:
`mctlclient.Client.ListServices()` returns `[]Service{Team, App}` — the
registry's own `(team, app)` pairs — and `Poller.pollDegraded` already calls it
on every tick.

`Skill.Fix(ctx, t, diag)` receives no `EvidenceSet` (only `Match` and `Diagnose`
do), so a skill cannot read the raw alert labels at `Fix` time even though
`processAlert` stores the whole alert JSON as `"alert"` evidence. Any label-based
resolution must therefore happen at ingestion, not inside `Fix`.

## Proposed solution

Three changes, in dependency order.

### 1. New package `internal/svcname` — pure, dependency-free name resolution

Modelled directly on `internal/gitopspath`: string-only, no dependency on
`mctlclient` or `fixer`, so it is unit-testable with plain strings. It exposes
the candidate list rather than a single answer, because the caller that can
verify a candidate differs from the caller that derives it.

```go
// ChartFullnameSuffixes are the Helm chart fullname suffixes appended to a
// release name. Seeded with the base-service chart only; add "-worker-service"
// here if that chart turns out to use the same pattern.
var ChartFullnameSuffixes = []string{"-base-service"}

// IdentityLabels are the alert label keys, in preference order, that name the
// canonical app directly.
var IdentityLabels = []string{
	"backstage.io/kubernetes-id", "label_backstage_io_kubernetes_id",
	"app.kubernetes.io/instance", "label_app_kubernetes_io_instance",
}

// Candidates returns the ordered candidate app names for a pod-derived service
// name, most authoritative first, deduplicated, never empty when derived != "".
func Candidates(namespace, derived string, labels map[string]string) []string
```

Ordering:

1. An `IdentityLabels` hit. For the `app.kubernetes.io/instance` spellings the
   value is the release name, so a leading `{namespace}-` is stripped
   (`labs-mctl-telegram` -> `mctl-telegram`); for `backstage.io/kubernetes-id`
   the value is used as-is.
2. `derived` with a `ChartFullnameSuffixes` entry removed **and** a leading
   `{namespace}-` removed. `labs-mctl-telegram-base-service` -> `mctl-telegram`.
3. `derived` with only the suffix removed. Covers an app whose registered name
   legitimately begins with the tenant name.
4. `derived` unchanged — always last, so today's behaviour is the floor.

The `{namespace}-` strip is **gated on the chart-fullname suffix having been
present**. That gate is the whole safety argument: without it, a plain
StatefulSet pod named `labs-something-0` in namespace `labs` would be silently
renamed. With it, only pods carrying the chart's own fullname signature are
touched, and `extractService`'s existing cases (`myapp-6d4b5c7f8-abc12`,
`two-parts`, `a-b-c-d-e`, `""`) all fall straight through to candidate 4.

A thin `Resolve(namespace, derived string, labels map[string]string, known func(tenant, app string) bool) string`
returns the first candidate `known` accepts, or `Candidates(...)[0]` when
`known` is nil or accepts none. "Accepts none" deliberately returns the *derived*
best guess rather than the raw value, so the fix still works when mctl-api is
down.

### 2. Canonicalise at ingestion, in `processAlert`

`AlertHandler` gains one optional, nil-safe field, matching the existing
`IgnoreService` / `OnResolve` / `BatchBudget` pattern on that struct:

```go
// KnownService, when non-nil, reports whether (tenant, app) is a registered
// service. Used to pick among candidate app names. Nil disables verification
// and falls back to the deterministic derivation.
KnownService func(tenant, app string) bool
```

`cmd/agent/main.go` wires it to a small cache over
`mctlclient.Client.ListServices()` — refreshed on the poller's existing tick and
on a miss, with a short negative-result cooldown so a burst of alerts for an
unregistered name cannot hammer mctl-api. The cache lives next to the `Poller`,
which already owns a `mctlclient.Client`; `AlertHandler` sees only the closure,
so its unit tests stay store-only.

In `processAlert`, canonicalisation is applied **after** the existing workload /
workflow / ArgoCD overrides and **before** the tenant/service empty-string
fallbacks:

```go
service = svcname.Resolve(namespace, service, a.Labels, h.KnownService)
```

Placing it after the overrides means a `deployment` label like
`admins-mctl-agents-worker-base-service` is canonicalised too, which is correct
and is the same class of bug. Placing it before the empty fallbacks keeps
`service == ""` reachable for the label-less infra alerts that
`isInfraAlert` depends on — `Resolve` returns `""` for an empty input.

This single change fixes the GitOps path, `collectEvidence`'s three failing
mctl-api calls, the ticket identity shown to operators, and the mismatch
`pruneOrphans` documents — all from one place, rather than patching five skills'
`FilePath` call sites independently.

**Rollout.** `Service` is part of the `(tenant, service, type)` dedup key, so an
alert already firing when this ships gets one new ticket (and one notification)
under the corrected name; the old one is closed by `reconcileWithAlertManager`
once its alerts clear. This is the identical trade the workload-label rewrite
already made, and its rollout note in `alerthandler.go` explains why **no
key-migration fallback is added**: a fallback that resolves the old key on a
replayed batch can close an incident that is still firing. That reasoning applies
here unchanged, so this design deliberately does not add one.

### 3. Deduplicate the path helper and probe candidates before patching

- Delete `builtin.detectFilePath` and route all six builtin call sites
  (`oomkilled`, `cpu_throttle`, `probe_fix`, `rollback`, `scale_up`,
  `llm_diagnosis`) through `fixer.DetectFilePath`, which the pipeline already
  uses. One implementation, one `PlatformServices` map, one test table. With
  step 2 in place the `PlatformServices` branch becomes reachable for
  AlertManager tickets about `mctl-api` / `mctl-agent` for the first time.

- Add `fixer.CandidatePaths(tenant string, services []string) []string`, and in
  `internal/pipeline/pipeline.go` replace the single `GetFileContent` with a
  bounded loop over the candidate paths for `t.Tenant` and
  `svcname.Candidates(...)`, keeping the existing `ValidatePath` gate inside the
  loop so no candidate escapes the allowlist. The first path that reads wins and
  becomes `filePath` for the rest of the function (patch generation and
  `CreatePR` both already take `filePath` as a parameter, so nothing else
  changes). The candidate list is capped and every probe is a single GitHub
  contents GET, so the cost on the happy path is unchanged — the first candidate
  hits.

- When every candidate fails, escalate with all of them:

  ```
  [escalated] Could not read any candidate GitOps path for labs/mctl-telegram.
  Tried: platform-gitops/services/labs/mctl-telegram/values.yaml;
  platform-gitops/services/labs/labs-mctl-telegram-base-service/values.yaml
  (last error: 404 Not Found). This is an agent-side failure, not necessarily a
  service failure.
  ```

  This keeps the existing "agent-side failure" framing that makes the escalation
  actionable, and answers the question incident `77c234ee` left an operator with.

Step 3 is what makes the change safe under an imperfect step 2: even if a name is
resolved wrongly, the old path is still in the candidate list, so the worst case
is today's behaviour plus a better escalation message.

## Alternatives

**A. Fix only `detectFilePath`, leave `t.Service` alone.** Smallest diff, no
dedup-key churn, no rollout note. Dropped: it leaves `collectEvidence`'s three
mctl-api calls still 404ing, leaves the operator-visible service name wrong in
Telegram and mctl-api incidents, leaves `pruneOrphans`' documented mismatch in
place, and would have to be repeated in both `DetectFilePath` implementations
plus anywhere else the name is consumed. It treats the symptom at the last
consumer instead of the one place the name is constructed.

**B. Add `client-go` and read the pod's labels live.** This is the issue's stated
preferred fix and is the most authoritative source. Dropped: mctl-agent has no
`k8s.io` dependency at all and no capability for pod reads; adding one means new
RBAC, a new failure mode in the alert hot path, and a large dependency tree for
one string. Worse, it is unreliable for the actual trigger — an OOMKilled pod is
frequently gone by the time the ticket is processed, which is precisely the case
the issue's own fallback (step 2) exists for. The label path is therefore kept as
an opportunistic read of labels AlertManager already carries, and the
deterministic derivation is promoted from "fallback" to the primary mechanism.

**C. Resolve the name lazily inside each skill's `Fix`.** Dropped on the
interface: `Skill.Fix(ctx, t, diag)` has no `EvidenceSet` parameter, so a skill
cannot see the alert labels; only `Match` and `Diagnose` can. Resolving in
`Diagnose` and smuggling the result through `DiagnosisResult` would add a field
to a shared struct for one skill family's benefit and would still leave YAML and
remote skills (`internal/skill/yaml/`, `internal/skill/remote/`) unfixed, since
they build their own `FilePath`.

**D. Probe candidate paths in the pipeline only, with no ingestion change.**
Fixes the PR path with no dedup churn at all. Dropped as insufficient on its own
for the same reasons as A — evidence and operator-visible identity stay wrong —
but it is not discarded: it is adopted as step 3, where it serves as the safety
net under step 2 rather than as the whole fix.

## Platform impact

**Migrations.** None. No schema change: `ticket.Ticket` gains no field, and the
resolved name is written into the existing `Service` column.

**Backward compatibility.**
- Tickets open at rollout keep their old `Service` and are closed by
  `reconcileWithAlertManager`, as described above. Expect a small one-off burst
  of duplicate notifications, bounded by the number of base-service alerts firing
  at deploy time.
- Three existing test tables assert the current wrong names and must be updated
  deliberately, not incidentally: `alerthandler_test.go` cases around lines
  1026, 1133, 1180, 1278-1304, 1328, 1385 (`admins-mctl-api-base-service`,
  `admins-mctl-agents-worker-base-service`), and `builtin_test.go:469`
  (`labs-mctl-telegram-base-service`). Each change is a behaviour change the
  reviewer should confirm one by one.
- The `IgnoreService` regex (used for demo/PR-preview services such as
  `openclawpr4`) now matches against the canonical name. `alerthandler_test.go`
  has a case with `pod: "openclawpr4-base-service-..."`; under the new rule the
  derived name is `openclawpr4` in namespace `openclawpr4`, so a
  `{namespace}-` strip does not apply and a regex matching `openclawpr4` still
  matches. Worth a regression test rather than an assumption.
- `pruneOrphans` stays excluded from `SourceAlertManager` tickets. Its comment
  should be amended to say the mismatch is now fixed at ingestion but that the
  exclusion is retained pending separate review — not silently re-enabled.

**Resource impact.** One extra in-memory map of registered `(team, app)` pairs,
refreshed from a `ListServices()` call the poller already makes. On the happy
path the pipeline performs the same single `GetFileContent`; candidate probing
costs at most a handful of extra contents GETs, and only on the path that
currently fails outright.

**Risks and mitigations.**
- *Over-eager `{namespace}-` stripping renames a service that was correct.*
  Mitigated by gating the strip on the `-base-service` suffix, by ordering the
  raw value last in the candidate list, and by the registry check. Residual risk
  is covered by step 3: the old path is still probed.
- *mctl-api unavailable during an alert burst, so no candidate can be verified.*
  `Resolve` degrades to the deterministic derivation; ticket creation never
  blocks on the API. The negative-result cooldown bounds retry load.
- *A tenant and app share a prefix ambiguously* (tenant `labs`, app
  `labs-dashboard`). Candidate 3 (suffix stripped, prefix kept) is in the list
  ahead of the raw value precisely for this, and the registry check disambiguates
  when it is reachable.
- *Duplicate notifications at rollout.* Bounded, one-off, and identical in kind
  to the accepted precedent already documented in `alerthandler.go`. Deploy
  during a quiet window.
