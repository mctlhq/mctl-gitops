# Follow-ups from #142: harden service-name canonicalisation, candidate probing and their escalation messages

## Context

PR #142 (refs #141) introduced `internal/svcname` so a pod-scoped ticket's
`Service` is canonicalised at ingestion from the base-service Helm chart's
fullname (`labs-mctl-telegram-base-service`) to the registered app name
(`mctl-telegram`), and taught `internal/pipeline` to probe
`svcname.Candidates` as a safety net when a ticket's `Service` predates that
canonicalisation. The PR merged with zero P1/P2 findings. Issue #143 collects
the P3 findings from the final review round so they are not lost in resolved
review threads.

None of these findings can produce a wrong GitOps write today, so this is a
hardening and observability proposal, not a bug fix. Its value is in three
places: closing input-validation gaps that only *happen* to be unreachable
(`fixer.DetectFilePath` with an empty `tenant`/`service`, and the dead
`fix_appproject_whitelist` dispatch arm), replacing escalation messages that
mislead the on-call operator (`no applicable fix strategy for type: ` with an
empty `FixType`; `tried 0, last error: <nil>`), and making the new tests
actually prove what they claim (an unanchored regex that passes with or
without canonicalisation; test counters written from `httptest` handler
goroutines). It also fixes two real name-resolution gaps: `svcname.Resolve`
is handed `namespace` where it should get the resolved `tenant`, and
base-service StatefulSet pods (`{release}-base-service-0`) reduce to
`...-base` in `extractService` and so skip deterministic canonicalisation
entirely.

## User stories

- AS the platform on-call operator I WANT an escalation message that names the
  real reason a fix was not applied SO THAT I do not have to read agent source
  to find out why `no applicable fix strategy for type: ` has an empty type.
- AS the platform on-call operator I WANT the "could not read any candidate
  GitOps path" escalation to be distinguishable from "there was nothing to
  read" SO THAT I do not chase a GitHub outage that never happened.
- AS a platform engineer I WANT `fixer.DetectFilePath` to refuse empty inputs
  SO THAT no malformed path (`platform-gitops/services//x/values.yaml`) can
  ever reach the GitHub API, even though `gitopspath.Validate` accepts its
  cleaned form.
- AS a platform engineer I WANT the `fix_appproject_whitelist` dispatch arm
  gone SO THAT no future skill emitting that `FixType` can run an AppProject
  transform against a tenant `values.yaml`.
- AS a platform engineer I WANT the canonicalisation regression tests to fail
  when canonicalisation is bypassed SO THAT they are regressions and not
  decoration.
- AS an SRE running a base-service StatefulSet I WANT its pods canonicalised
  deterministically SO THAT the ticket carries the registered app name without
  depending on an identity label being present.

## Acceptance criteria (EARS)

Path construction and validation

- WHEN `fixer.DetectFilePath` is called with an empty `tenant` or an empty
  `service` THE SYSTEM SHALL return `""`.
- WHILE `fixer.DetectFilePath` returns `""` THE SYSTEM SHALL cause
  `fixer.CandidatePaths` to drop that entry, exactly as it already drops the
  platform-service `""`.
- WHEN `gitopspath.Allowlist.Validate` is given a candidate whose
  `path.Clean` form differs from the candidate as written (an empty path
  segment such as `platform-gitops/services//x/values.yaml`, a `./` segment,
  or a trailing `/`) THE SYSTEM SHALL reject it with a descriptive error,
  because the uncleaned string is what `GetFileContent`/`CreatePR` send to the
  GitHub API.
- WHILE a path is already in cleaned form THE SYSTEM SHALL continue to accept
  or reject it exactly as it does today (no change for
  `platform-gitops/services/acme/api/values.yaml` or for any case in
  `internal/gitopspath/gitopspath_test.go`).

Pipeline escalation messages

- IF `fixResult.NewContent` is non-empty, `fixResult.FilePath` is non-empty,
  and the resolved candidate `filePath` differs from `fixResult.FilePath`,
  THEN THE SYSTEM SHALL fail patch generation with an error that names both
  paths and states that the skill's whole-file content was authored against a
  different file, instead of `no applicable fix strategy for type: %s` with an
  empty `FixType`.
- IF the candidate path list is empty THEN THE SYSTEM SHALL escalate with a
  message stating that no candidate GitOps path could be derived for
  `tenant/service`, and SHALL NOT render `tried 0, last error: <nil>`.
- WHILE at least one candidate path was probed and all probes failed THE
  SYSTEM SHALL keep today's message shape, including the candidate list and
  the last error.

Dead fix-type dispatch

- WHEN `diag.FixType` is `fix_appproject_whitelist` THE SYSTEM SHALL refuse it
  explicitly with an error naming AppProject manifests as operator-only, and
  SHALL NOT call any AppProject content transform.
- WHILE `fix_appproject_whitelist` is refused THE SYSTEM SHALL NOT retain
  `fixer.GenerateAppProjectWhitelistFix` as reachable production code.
- WHEN `WorkflowFixerSkill.Fix` is called with
  `FixType == "fix_appproject_whitelist"` THE SYSTEM SHALL return
  `Applied: false` with the escalation summary naming
  `platform-gitops/bootstrap/templates/projects/project-apps.yaml`, and a
  unit test SHALL pin that.

Name resolution

- WHEN `internal/monitor.processAlert` calls `svcname.Resolve` THE SYSTEM
  SHALL pass the resolved `tenant`, not the raw `namespace` label, so the
  namespace-prefix strip agrees with `internal/pipeline.candidatePaths`
  (which already passes `t.Tenant`) when `dest_namespace` won.
- WHEN a pod name carries a `svcname.ChartFullnameSuffixes` signature followed
  by a StatefulSet ordinal (`{tenant}-{app}-base-service-0`) THE SYSTEM SHALL
  reduce it to the chart fullname (`{tenant}-{app}-base-service`) so
  deterministic canonicalisation applies, without needing an identity label.
- WHILE a pod name does not carry that signature THE SYSTEM SHALL reduce it
  exactly as `extractService` does today (strip the last two segments, or
  return the name unchanged for two segments or fewer).
- WHEN `svcname.Candidates` looks up `IdentityLabels` THE SYSTEM SHALL prefer
  the `label_*` spellings, which are the only spellings a Prometheus/
  VictoriaMetrics alert label can actually carry (Prometheus label names match
  `[a-zA-Z_][a-zA-Z0-9_]*`, so `backstage.io/kubernetes-id` cannot appear as
  an alert label key), and SHALL keep the raw dotted/slashed spellings as a
  trailing fallback for non-alert callers.

Tests

- WHILE `TestAlertHandlerIgnoreServiceFilterMatchesCanonicalName` runs THE
  SYSTEM SHALL use an anchored pattern (`^openclawpr\d+$`) so the test fails
  if `svcname.Resolve` is bypassed.
- WHILE any test in `internal/pipeline` observes counters or bodies written
  from an `httptest` handler THE SYSTEM SHALL guard them with a mutex or
  `sync/atomic` so `go test -race` reports no race.

## Out of scope

- Opening the GitOps write allowlist to
  `platform-gitops/bootstrap/templates/` (platform services or AppProjects).
  Escalation stays the behaviour for both.
- Any key-migration fallback for tickets created under a pre-canonicalisation
  dedup key. `internal/monitor/alerthandler.go` documents at length why AM
  reconcile is the only correct closer; that reasoning is unchanged.
- Adding `-worker-service` (or any other chart) to
  `svcname.ChartFullnameSuffixes`.
- Any registry or network lookup in `internal/svcname`. It stays
  deterministic and string-only.
- Correcting the amended spec in mctlhq/mctl-gitops#1461. The spec correction
  in the issue is recorded here for the record only; `mctl-agent` runs on the
  base-service chart (`admins-mctl-agent-base-service`) with values inlined in
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml`, so
  `fixer.PlatformServices` keeping `mctl-agent` is still correct behaviour and
  no code changes because of it.

## Open questions

- Should `gitopspath.Allowlist.Validate` reject a non-canonical-but-safe path
  (`//`, `./`, trailing `/`) outright, or only log and pass the cleaned form
  on? Proceeding with outright rejection: every production path is built by
  `fixer.DetectFilePath` or is a fixed workflow-template constant, so no
  legitimate caller produces a non-canonical path, and rejecting keeps
  "validated string" and "string sent to GitHub" identical.
- The `label_*` reordering assumes every real producer is a
  `kube_pod_labels` join. If some non-alert caller (a future mctl-api
  evidence path) supplies raw dotted keys, they still resolve via the
  trailing fallback, so the reorder is safe either way; proceeding with the
  reorder.
- The StatefulSet ordinal rule is gated on a chart-fullname signature plus an
  all-digits final segment. A Deployment pod whose 5-character random suffix
  is all digits *and* whose name ends in `-base-service` would be misread as
  an ordinal; proceeding anyway, because such a name would then be
  `{tenant}-{app}-base-service-12345`, whose only plausible reading is still
  a base-service pod of `{app}`.
- `go test -race` is not run by the `Makefile` or any workflow in
  `.github/workflows/` today, so the test-race findings are forward-looking.
  Proceeding with the fixes plus an optional `make test-race` target; wiring
  it into CI is left out of scope.
