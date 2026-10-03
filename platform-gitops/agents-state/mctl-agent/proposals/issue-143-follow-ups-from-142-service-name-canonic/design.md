# Design: issue-143-follow-ups-from-142-service-name-canonic

## Current state

### Canonicalisation at ingestion

`internal/monitor/alerthandler.go`'s `processAlert` derives
`tenant := namespace` (the `namespace` alert label) and
`service := extractService(pod)` (line ~201-202). It then may override
`service` from a `deployment`/`statefulset`/`daemonset` label, from a workflow
name for `ticket.TypeWorkflowFailed`, or from the ArgoCD Application `name`
label for `ticket.TypeArgoCDDegraded` — and, in that last branch only,
overrides `tenant` from `dest_namespace` (lines 257-283). Each override sets
`workloadLabeled = true`.

Line 322-326 then canonicalises:

```go
svcLabels := a.Labels
if workloadLabeled {
    svcLabels = nil
}
service = svcname.Resolve(namespace, service, svcLabels)
```

Two facts matter here. First, the first argument is `namespace`, not `tenant`
— they diverge exactly when `dest_namespace` won. `internal/pipeline`'s
`candidatePaths` passes `t.Tenant` for the same parameter
(`internal/pipeline/pipeline.go:914`), so ingestion and the pipeline safety
net can strip different prefixes for the same ticket. Second,
`extractService` (`alerthandler.go:556-566`) splits on `-` and strips the last
two segments unconditionally. For a Deployment pod
`labs-mctl-telegram-base-service-6d4b5c7f8-abc12` that yields
`labs-mctl-telegram-base-service` — exactly the chart-fullname signature
`svcname` recognises. For a base-service StatefulSet pod
`labs-foo-base-service-0` it yields `labs-foo-base`, which matches no entry in
`svcname.ChartFullnameSuffixes`, so `Candidates` falls straight through to
candidate 4 (`derived` unchanged) and only an identity label can recover the
app name.

`svcname.IdentityLabels` (`internal/svcname/svcname.go:45-50`) lists
`backstage.io/kubernetes-id`, `label_backstage_io_kubernetes_id`,
`app.kubernetes.io/instance`, `label_app_kubernetes_io_instance` — raw
spellings first. `Candidates` takes the FIRST non-empty hit and `break`s
(lines 118-128), so order is decisive. Prometheus/VictoriaMetrics label names
must match `[a-zA-Z_][a-zA-Z0-9_]*`, so the raw dotted/slashed spellings can
never be keys in an AlertManager payload's `labels` map; only the `label_*`
spellings, produced by a `kube_pod_labels` join, can be. The raw spellings are
therefore ordered ahead of the only spellings that can actually arrive.

The `IgnoreService` filter runs after canonicalisation
(`alerthandler.go:432`), matching on the canonical `service`.
`TestAlertHandlerIgnoreServiceFilterMatchesCanonicalName`
(`internal/monitor/alerthandler_test.go:1393`) is the regression for that, but
it sets `regexp.MustCompile(`^openclawpr\d+`)` — unanchored. Its pod is
`openclawpr4-base-service-6d4b5c7f8-abc12` in namespace `openclawpr4`; the raw
derived name `openclawpr4-base-service` and the canonical name `openclawpr4`
both match that pattern, so the test passes whether or not `svcname.Resolve`
runs.

### Path construction and validation

`fixer.DetectFilePath` (`internal/fixer/patcher.go:74-79`) returns `""` for a
`PlatformServices` entry and otherwise
`fmt.Sprintf("platform-gitops/services/%s/%s/values.yaml", tenant, service)`
with no guard on either argument. `fixer.CandidatePaths` (lines 84-96) drops
`""` results and dedupes.

`gitopspath.Allowlist.Validate` (`internal/gitopspath/gitopspath.go:71-97`)
rejects empty, `..`-containing, and absolute candidates, then checks
`path.Clean(candidate)` against the allowlisted prefixes. It returns nil for
`platform-gitops/services//x/values.yaml`, because the cleaned form
(`platform-gitops/services/x/values.yaml`) is under
`platform-gitops/services/`. `fixer.GitHubFixer.GetFileContent`
(`internal/fixer/github.go:248-252`) validates and then passes the ORIGINAL,
uncleaned `path` to `Repositories.GetContents`. So validation and the API call
can disagree about which string is being used. `Validate` is the only place
that cleans; nothing writes the cleaned form back.

### Pipeline fix dispatch

`pipeline.handleHighConfidenceFix` (`internal/pipeline/pipeline.go:656-886`)
escalates platform services before any GitHub call (line 680), builds the
candidate list via `candidatePaths(fixResult.FilePath, t.Tenant, t.Service)`
(line 701), and probes each candidate with `ValidatePath` then
`GetFileContent`, skipping 404s and stopping on any other error (lines
709-740).

Three message defects live in that block:

1. When every candidate fails, the operator gets
   `Could not read any candidate GitOps path (tried %d, last error: %v)` with
   `len(paths)` and `lastErr` (lines 745-751). If `paths` is empty — reachable
   when `fixResult.FilePath == ""` and `svcname.Candidates` returns nil for an
   empty `t.Service` — the loop never ran, so it prints
   `tried 0, last error: <nil>`.
2. The `default` arm's `NewContent` guard
   (`fixResult.FilePath == "" || filePath == fixResult.FilePath`, line 777)
   correctly refuses whole-file content authored against a different path, but
   falls through to
   `fmt.Errorf("no applicable fix strategy for type: %s", diag.FixType)` (line
   792). `diag.FixType` is empty on exactly this path (the case
   `TestHandleHighConfidenceFixRejectsMismatchedNewContentPath`,
   `internal/pipeline/pipeline_test.go:552`, constructs), so the operator sees
   a message with a dangling empty type and no mention of the real cause.
3. `case "fix_appproject_whitelist": fixer.GenerateAppProjectWhitelistFix(content)`
   (lines 769-770) is dead. Its only producer, `WorkflowFixerSkill.Fix`
   (`internal/skill/builtin/workflow_fixer.go:115-130`), now returns
   `Applied: false`, so the pipeline escalates at line 656 before the switch.
   If any other skill ever emitted that `FixType` with `Applied: true`, the
   generator — which string-replaces an `external-secrets.io` AppProject
   anchor (`internal/fixer/patcher.go:440-460`) — would run against whatever
   tenant `values.yaml` the candidate probe resolved.

### Tests

`internal/pipeline/pipeline_test.go` declares `contentGETs` (lines 388, 739,
831), `putCalls`/`pullCalls` (line 556) and `putBody` (line 640) as plain
locals written inside `http.HandlerFunc` bodies and read from the test
goroutine after `handleHighConfidenceFix` returns. `httptest.Server` serves
each request on its own goroutine, so those are data races under
`go test -race`. Neither `Makefile`'s `test` target (`go test ./...`) nor any
workflow in `.github/workflows/` passes `-race` today, so nothing currently
reports them.

No test pins `WorkflowFixerSkill.Fix`'s `Applied: false` result for
`fix_appproject_whitelist` — `internal/skill/builtin/builtin_test.go` covers
`Match`/`Diagnose` shapes and `AutoMergeSafe`, not this `Fix` arm.

## Proposed solution

Eight small, independent changes, each landing with its own test. No new
package, no interface change, no config surface.

### 1. `fixer.DetectFilePath` refuses empty inputs

```go
func DetectFilePath(tenant, service string) string {
    if tenant == "" || service == "" {
        return ""
    }
    if PlatformServices[service] {
        return ""
    }
    return fmt.Sprintf("platform-gitops/services/%s/%s/values.yaml", tenant, service)
}
```

`""` is already the established "nothing to probe" signal: `CandidatePaths`
drops it, and `handleHighConfidenceFix` already escalates rather than treating
`""` as a path. The builtin skills that call `DetectFilePath`
(`oomkilled.go:70`, `cpu_throttle.go:85`, `probe_fix.go:88`, `rollback.go:73`,
`scale_up.go:88`, `llm_diagnosis.go:263`) therefore need no change: an empty
`FilePath` flows into the pipeline's `candidatePaths`, which drops it.

### 2. `gitopspath.Validate` rejects non-canonical paths

Add, after the existing traversal/absolute checks and the `path.Clean` call:

```go
if cleaned != candidate {
    return fmt.Errorf("gitops path %q is not in canonical form (resolves to %q)", candidate, cleaned)
}
```

This closes the validate-one-string/send-another gap at its root, which is
the structural half of finding 1: even if some future caller rebuilds a path
by hand, the string that is validated is byte-identical to the string
`GetContents`/`CreatePR` receive. Every production path is either
`DetectFilePath`'s `Sprintf` output or a fixed workflow-template constant, and
every case in `internal/gitopspath/gitopspath_test.go` is already canonical
(or already rejected for another reason), so no legitimate path changes
verdict.

### 3. Escalate an empty candidate list distinctly

Split the `filePath == ""` branch on `len(paths) == 0`:

- `len(paths) == 0`: escalate with "no candidate GitOps path could be derived
  for %s/%s" and no `tried`/`last error` clause. Nothing was probed, so
  reporting a probe failure is simply wrong.
- otherwise: today's message, unchanged.

### 4. Name the path mismatch instead of the empty `FixType`

In the `default` arm, replace the single `else` with an explicit mismatch
case:

```go
} else if fixResult.NewContent != "" && fixResult.FilePath != "" && filePath != fixResult.FilePath {
    patchErr = fmt.Errorf(
        "skill authored whole-file content for %q but the resolved gitops file is %q; refusing to write it there",
        fixResult.FilePath, filePath)
} else {
    patchErr = fmt.Errorf("no applicable fix strategy for type: %s", diag.FixType)
}
```

Behaviour is identical (the fix still fails, no PR), only the operator-facing
error changes. The existing guard condition on the reuse branch stays exactly
as written, so the "skill left `FilePath` empty" case documented at
`pipeline.go:784-788` keeps reusing `NewContent`.

### 5. Delete the `fix_appproject_whitelist` arm and its generator

Replace the dispatch arm with an explicit refusal:

```go
case "fix_appproject_whitelist":
    // AppProject manifests live under platform-gitops/bootstrap/templates/
    // projects/, outside the write allowlist (internal/gitopspath). Its only
    // producer (builtin.WorkflowFixerSkill) returns Applied:false and is
    // escalated before this switch; refuse it explicitly so a future skill
    // emitting this FixType cannot run an AppProject transform against a
    // tenant values.yaml.
    patchErr = fmt.Errorf("fix type %q targets an ArgoCD AppProject manifest, which is not patched automatically", diag.FixType)
```

and delete `fixer.GenerateAppProjectWhitelistFix` outright (it has no other
caller — confirmed by grep across `internal/`). Refusing explicitly rather
than falling into `default` is deliberate: `default` would try
`GenerateFromDiagnosis` if a future diagnosis happened to carry
`CurrentValue`/`SuggestedValue`, which is the very hazard the issue names.

### 6. `svcname.Resolve` receives the resolved tenant

Change `alerthandler.go:326` to `service = svcname.Resolve(tenant, service, svcLabels)`.
The call already sits after the `dest_namespace` override and before the
`tenant == ""` -> `"platform"` fallback, so `tenant` there is the resolved
namespace the GitOps path is actually built from — the same value
`pipeline.candidatePaths` passes. For every non-ArgoCD alert `tenant ==
namespace`, so this is a no-op; for the ArgoCD branch it makes the two
canonicalisation sites agree.

### 7. StatefulSet ordinal reduction

Add to `internal/svcname`:

```go
// TrimPodSuffix reduces a pod name to the workload name a canonical app name
// can be derived from. A base-service StatefulSet pod is
// "{release}-base-service-{ordinal}": one trailing segment, not the two a
// Deployment's "-{rs}-{id}" carries.
func TrimPodSuffix(pod string) string
```

It strips ONE segment when that segment is all digits and the remainder ends
in a `ChartFullnameSuffixes` entry; otherwise it keeps today's strip-two
behaviour (and today's "two segments or fewer -> return unchanged" rule).
`monitor.extractService` becomes a thin call into it, so the chart-signature
knowledge stays in `svcname` — the same reason `svcname` exists at all. The
all-digits + signature double gate is what keeps a plain StatefulSet pod like
`labs-something-0` from being touched, mirroring the gating rationale already
documented at `svcname.go:90-98`.

### 8. `IdentityLabels` reorder

Reorder to `label_backstage_io_kubernetes_id`,
`label_app_kubernetes_io_instance`, `backstage.io/kubernetes-id`,
`app.kubernetes.io/instance`, with a comment recording WHY: Prometheus label
names cannot contain `.` or `/`, so only the `label_*` spellings can reach
`Candidates` from an alert payload; the raw spellings stay as a trailing
fallback for any non-alert caller. `instanceLabels` already covers both
spellings of the instance label, so the release-name strip is unaffected.

### 9. Test hardening

- Anchor the `IgnoreService` pattern in
  `TestAlertHandlerIgnoreServiceFilterMatchesCanonicalName` to
  `^openclawpr\d+$` and add a comment stating the check: with the anchor, the
  raw derived name `openclawpr4-base-service` no longer matches, so the test
  fails if `svcname.Resolve` is bypassed.
- Replace the plain `contentGETs`/`putCalls`/`pullCalls` counters in
  `internal/pipeline/pipeline_test.go` with `atomic.Int64` (read via
  `.Load()`), and guard `putBody` with a `sync.Mutex`.
- Add `TestWorkflowFixerSkillFixDeclinesAppProjectWhitelist` in
  `internal/skill/builtin` pinning `Applied == false` and the summary naming
  `platform-gitops/bootstrap/templates/projects/project-apps.yaml`.
- Add a `test-race` target to the `Makefile` (`go test -race ./...`) so the
  race fixes are verifiable locally. Wiring it into CI is out of scope.

## Alternatives

1. **Normalise the path inside `gitopspath.Validate` and return the cleaned
   string for callers to use.** Rejected: it changes `Validate`'s signature
   and makes every caller responsible for using the returned value instead of
   its own variable — exactly the class of mistake that produced this finding.
   Rejecting a non-canonical path keeps one string throughout.
2. **Keep `GenerateAppProjectWhitelistFix` and only guard the dispatch arm.**
   Rejected: an unreachable transform that string-replaces an AppProject
   anchor is a latent hazard with no test and no caller. The issue explicitly
   offers "delete the arm and the generator, or refuse that `FixType`
   explicitly"; this proposal does both (refuse in the pipeline, delete the
   generator), which is strictly safer than either alone.
3. **Fix the StatefulSet case in `monitor.extractService` directly with an
   inline regexp.** Rejected: it would put chart-fullname knowledge back in
   `internal/monitor`, which is what `internal/svcname` was extracted to
   avoid, and it could not be unit tested with plain strings the way
   `svcname_test.go` tests are.
4. **Recover StatefulSet pods by widening `ChartFullnameSuffixes` with
   `-base` .** Rejected outright: `-base` is not a chart fullname signature,
   and any app legitimately named `{tenant}-{app}-base` would be silently
   renamed.
5. **Leave the test counters alone since CI does not run `-race`.**
   Rejected: the races are real, the fix is mechanical, and the `Makefile`
   target makes them checkable the moment someone does run `-race`.

## Platform impact

- **Migrations:** none. No schema change, no ticket-store change, no config
  key added or removed.
- **Backward compatibility:** changes 1-5 and 8-9 are behaviour-preserving on
  every currently reachable path — they alter refusal *messages* and close
  unreachable branches. Change 6 is a no-op except for
  `ticket.TypeArgoCDDegraded` alerts carrying `dest_namespace`, and there
  `workloadLabeled == true` so `svcLabels` is nil and only the namespace-prefix
  strip differs; it now matches what the pipeline already does.
- **Ticket-key impact:** change 7 is the only one that can rename a service
  and so change a `(tenant, service, type)` dedup key — for base-service
  StatefulSet pods only. That has the same one-off cost as the #105 and #142
  rollouts already documented in `alerthandler.go:236-250` and `310-321`: an
  alert firing at deploy time keeps its old ticket and gets one new ticket and
  one notification under the corrected name; the old one is closed by
  `reconcileWithAlertManager`. No key-migration fallback is added, for the
  reasons those comments give.
- **Resource impact:** none. `svcname` remains allocation-light and
  network-free; the candidate-probe cost is unchanged (still one
  `GetFileContent` on the happy path, pinned by
  `TestHandleHighConfidenceFixHappyPathReadsExactlyOnce`).
- **Risks and mitigations:**
  - *`Validate` rejecting a legitimate path.* Mitigated by a table test
    asserting every existing accepted case still passes plus the new
    non-canonical rejections, and by the fact that production paths come from
    `DetectFilePath` or fixed constants.
  - *`DetectFilePath("", svc)` returning `""` where a caller assumed a
    string.* Mitigated by the `""` contract already being in force for
    platform services and by an explicit test; `CandidatePaths` and
    `handleHighConfidenceFix` both already handle it.
  - *`TrimPodSuffix` misreading a Deployment pod whose 5-char ID is all
    digits.* Mitigated by the chart-signature gate: such a name would be
    `{tenant}-{app}-base-service-12345`, whose reduction to
    `{tenant}-{app}-base-service` is still the right answer.
  - *`IdentityLabels` reorder changing an existing ticket's name.* Only
    possible for a payload carrying BOTH a raw and a `label_*` spelling with
    different values — impossible from Prometheus, since the raw key is not a
    legal label name.
- **Release:** one `chore: release x.y.z` PR per `CLAUDE.md` (branch + PR,
  never on `main`), then tag the merge commit with the bare semver (no `v`
  prefix).
