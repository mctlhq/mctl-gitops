# Tasks: issue-143-follow-ups-from-142-service-name-canonic

All tasks are independent unless a dependency is stated, so they can land as
one PR or as several. Keep `go fmt ./... && go vet ./... && go test ./...`
green after each.

- [ ] 1. Guard `fixer.DetectFilePath` (`internal/fixer/patcher.go:74`) to
      return `""` when `tenant == ""` or `service == ""`, before the
      `PlatformServices` lookup. — DoD: `DetectFilePath("", "api") == ""`,
      `DetectFilePath("labs", "") == ""`, `DetectFilePath("billing",
      "payment-api")` unchanged; no builtin skill call site
      (`oomkilled.go:70`, `cpu_throttle.go:85`, `probe_fix.go:88`,
      `rollback.go:73`, `scale_up.go:88`, `llm_diagnosis.go:263`) needs
      editing because `fixer.CandidatePaths` and
      `pipeline.candidatePaths` already drop `""`.
- [ ] 2. Reject non-canonical paths in `gitopspath.Allowlist.Validate`
      (`internal/gitopspath/gitopspath.go:82`): after `path.Clean`, return an
      error when `cleaned != candidate`. — DoD:
      `platform-gitops/services//x/values.yaml`,
      `platform-gitops/services/./x/values.yaml` and
      `platform-gitops/services/acme/api/` are rejected; every existing case
      in `gitopspath_test.go` keeps its verdict; the string `Validate`
      approves is byte-identical to the string
      `fixer.GitHubFixer.GetFileContent` passes to `GetContents`
      (`internal/fixer/github.go:248`).
- [ ] 3. Split the exhausted-candidates escalation in
      `pipeline.handleHighConfidenceFix` (`internal/pipeline/pipeline.go:742`)
      on `len(paths) == 0`, with a message stating no candidate path could be
      derived for `tenant/service` and no `tried`/`last error` clause. —
      DoD: no operator-facing message can render `tried 0, last error:
      <nil>`; the >=1-candidate message keeps today's wording, candidate list
      and last error.
- [ ] 4. Replace the fall-through in the `default` arm's `NewContent` guard
      (`internal/pipeline/pipeline.go:777-793`) with an explicit mismatch
      error naming both `fixResult.FilePath` and the resolved `filePath`. —
      DoD: the mismatch case no longer produces `no applicable fix strategy
      for type: ` with an empty `FixType`; the empty-`FilePath` reuse branch
      (`TestHandleHighConfidenceFixReusesNewContentWithEmptyFilePath`) still
      passes; still no PUT and no PR on mismatch.
- [ ] 5. Refuse `fix_appproject_whitelist` explicitly in the fix-type switch
      (`internal/pipeline/pipeline.go:769`) with an error naming AppProject
      manifests as operator-only, and delete
      `fixer.GenerateAppProjectWhitelistFix`
      (`internal/fixer/patcher.go:439-460`). — DoD: `grep -rn
      "GenerateAppProjectWhitelistFix" internal/` returns nothing; the
      `FixType` cannot reach `GenerateFromDiagnosis` via `default`;
      `go build ./...` clean.
- [ ] 6. Pass the resolved tenant to `svcname.Resolve`
      (`internal/monitor/alerthandler.go:326`): `svcname.Resolve(tenant,
      service, svcLabels)`. — DoD: the argument matches what
      `pipeline.candidatePaths` passes (`pipeline.go:914`); an
      `ArgoCDApplicationDegraded` alert with `dest_namespace` strips the
      `dest_namespace` prefix, not the `namespace` one; the call still sits
      after the `dest_namespace` override and before the `tenant == ""` ->
      `"platform"` fallback.
- [ ] 7. Add `svcname.TrimPodSuffix(pod string) string` to
      `internal/svcname/svcname.go`: strip ONE trailing segment when it is
      all digits and the remainder ends in a `ChartFullnameSuffixes` entry,
      otherwise keep today's `extractService` behaviour (strip two segments;
      return unchanged for <= 2 segments; `""` for `""`). — DoD:
      `TrimPodSuffix("labs-foo-base-service-0") == "labs-foo-base-service"`,
      `TrimPodSuffix("labs-mctl-telegram-base-service-6d4b5c7f8-abc12") ==
      "labs-mctl-telegram-base-service"`, `TrimPodSuffix("labs-something-0")
      == "labs"` is NOT asserted — it must stay at today's value
      (`"labs-something-0"` has 3 segments, so today's strip-two gives
      `"labs"`; pin whatever today's function returns and do not change it).
- [ ] 8. Rewrite `monitor.extractService`
      (`internal/monitor/alerthandler.go:556`) as a thin delegation to
      `svcname.TrimPodSuffix` (depends on 7). — DoD: every existing
      `internal/monitor` test passes untouched; no chart-fullname string
      literal remains in `internal/monitor`; a
      `labs-foo-base-service-0` pod produces ticket `Service == "foo"` after
      `svcname.Resolve`.
- [ ] 9. Reorder `svcname.IdentityLabels`
      (`internal/svcname/svcname.go:45-50`) to put
      `label_backstage_io_kubernetes_id` and
      `label_app_kubernetes_io_instance` first, raw dotted/slashed spellings
      last, with a comment recording that Prometheus label names match
      `[a-zA-Z_][a-zA-Z0-9_]*` so the raw spellings cannot arrive from an
      alert payload. — DoD: `instanceLabels` still covers both instance
      spellings; a payload with only a `label_*` key resolves identically to
      today; a payload carrying both spellings prefers the `label_*` value.

## Tests

- [ ] T1. `internal/fixer/patcher_test.go`: extend `TestDetectFilePath` with
      `{"", "payment-api", ""}` and `{"billing", "", ""}` (task 1).
- [ ] T2. `internal/gitopspath/gitopspath_test.go`: add
      `{"empty path segment rejected", "platform-gitops/services//x/values.yaml", true}`,
      `{"dot segment rejected", "platform-gitops/services/./x/values.yaml", true}`,
      `{"trailing slash rejected", "platform-gitops/services/acme/api/", true}`
      (task 2).
- [ ] T3. `internal/pipeline/pipeline_test.go`: a test driving
      `handleHighConfidenceFix` with `fixResult.FilePath == ""` and
      `t.Service == ""` so `candidatePaths` is empty, asserting the escalation
      analysis contains the "no candidate GitOps path could be derived" phrase
      and NOT `tried 0` (task 3).
- [ ] T4. `internal/pipeline/pipeline_test.go`: extend
      `TestHandleHighConfidenceFixRejectsMismatchedNewContentPath` to assert
      the persisted escalation/analysis text names both the skill-proposed and
      the resolved path, and does not contain `no applicable fix strategy`
      (task 4).
- [ ] T5. `internal/pipeline/pipeline_test.go`: a test with
      `diag.FixType == "fix_appproject_whitelist"` and `Applied: true`
      asserting patch generation fails with the AppProject refusal and that
      no PUT and no `/pulls` request reaches the mock server (task 5).
- [ ] T6. `internal/skill/builtin/builtin_test.go`:
      `TestWorkflowFixerSkillFixDeclinesAppProjectWhitelist` pinning
      `Applied == false`, `err == nil`, and a summary containing
      `platform-gitops/bootstrap/templates/projects/project-apps.yaml`
      (`internal/skill/builtin/workflow_fixer.go:115-130`).
- [ ] T7. `internal/svcname/svcname_test.go`: table cases for
      `TrimPodSuffix` covering the base-service StatefulSet ordinal, the
      Deployment RS-hash form, a <= 2-segment name, a non-signature name with
      a numeric tail, and `""` (task 7); plus a `TestCandidates` case proving
      `labs-foo-base-service` resolves to `foo` with no labels.
- [ ] T8. `internal/monitor/alerthandler_test.go`: anchor
      `TestAlertHandlerIgnoreServiceFilterMatchesCanonicalName`
      (line 1397) to `^openclawpr\d+$`, and record in a comment that the raw
      derived name `openclawpr4-base-service` does not match the anchored
      pattern — verify locally that the test FAILS when the
      `svcname.Resolve` line is commented out, then restore it.
- [ ] T9. `internal/monitor/alerthandler_test.go`: a case asserting a
      `labs-foo-base-service-0` StatefulSet pod yields ticket `Service ==
      "foo"` (tasks 7-8), and a case asserting an
      `ArgoCDApplicationDegraded` alert with `dest_namespace` different from
      `namespace` canonicalises against `dest_namespace` (task 6).
- [ ] T10. `internal/pipeline/pipeline_test.go`: convert `contentGETs`
      (lines 388, 739, 831) and `putCalls`/`pullCalls` (line 556) to
      `atomic.Int64` read with `.Load()`, and guard `putBody` (line 640) with
      a `sync.Mutex`. — DoD: `go test -race ./internal/pipeline/...` reports
      no race and the assertions are unchanged in meaning.
- [ ] T11. `Makefile`: add a `test-race` target running `go test -race ./...`
      and list it in `.PHONY`. — DoD: `make test-race` passes on the branch;
      CI wiring is deliberately not part of this proposal.

## Rollback

Every change is a code-only edit in `mctl-agent` with no schema, config or
GitOps-manifest component, so rollback is a revert plus a release:

1. Revert the merge commit(s) on a branch, open a PR, merge it (never commit
   on `main`), then cut a `chore: release x.y.z` PR and tag the merge commit
   with the bare semver — `.github/workflows/build.yml` rebuilds the image and
   bumps the manifest.
2. For an urgent rollback with no rebuild, roll the running deployment back to
   the previous image tag. `mctl-agent` runs on the base-service chart as
   `admins-mctl-agent-base-service`, with values inlined in
   `platform-gitops/bootstrap/templates/mctl-platform/mctl-agent.yaml`; edit
   the image tag there by hand through a mctl-gitops PR (the agent itself
   cannot patch that path — it is outside the write allowlist, which is why
   `fixer.PlatformServices` lists `mctl-agent`).
3. Partial rollback is safe per task. Task 7/8 is the only one that can change
   a ticket dedup key: reverting it renames base-service StatefulSet services
   back, which costs one extra ticket and notification per firing alert, and
   `reconcileWithAlertManager` (`internal/monitor/poller.go`) closes the
   stranded one once its alerts clear — the same rollout cost documented for
   #105 and #142 in `internal/monitor/alerthandler.go`.
4. Tasks 2 and 5 are the only ones that can make a previously-accepted input
   fail: a non-canonical path now escalates instead of being read, and a
   `fix_appproject_whitelist` diagnosis now fails patch generation instead of
   escalating one step earlier. Both fail closed — they refuse to write — so
   rolling back is never required to prevent a bad GitOps write, only to
   restore a permissive read.
