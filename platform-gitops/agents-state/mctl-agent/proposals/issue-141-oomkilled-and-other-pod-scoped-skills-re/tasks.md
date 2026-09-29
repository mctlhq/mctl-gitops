# Tasks: issue-141-oomkilled-and-other-pod-scoped-skills-re

- [ ] 1. Add `internal/svcname/svcname.go`: a string-only, dependency-free package
      exposing `ChartFullnameSuffixes` (seeded `{"-base-service"}`),
      `IdentityLabels` (`backstage.io/kubernetes-id`,
      `label_backstage_io_kubernetes_id`, `app.kubernetes.io/instance`,
      `label_app_kubernetes_io_instance`),
      `Candidates(namespace, derived string, labels map[string]string) []string`
      and `Resolve(namespace, derived string, labels map[string]string, known func(tenant, app string) bool) string`.
      Candidate order: identity label (with `{namespace}-` stripped for the
      `instance` spellings) > suffix-stripped + prefix-stripped >
      suffix-stripped only > `derived` unchanged. The `{namespace}-` strip is
      gated on a `ChartFullnameSuffixes` entry having actually been present.
      Deduplicate, drop empties, return `nil` for `derived == ""`. Mirror the
      package doc style of `internal/gitopspath/gitopspath.go`.
      — DoD: package compiles, `go vet` clean, no import outside stdlib, and T1
      passes.

- [ ] 2. Wire canonicalisation into `internal/monitor/alerthandler.go` (depends on 1).
      Add an optional nil-safe `KnownService func(tenant, app string) bool` field
      to `AlertHandler`, documented in the same style as `IgnoreService` /
      `OnResolve`. In `processAlert`, insert
      `service = svcname.Resolve(namespace, service, a.Labels, h.KnownService)`
      after the `deployment`/`statefulset`/`daemonset`, `TypeWorkflowFailed` and
      `TypeArgoCDDegraded` overrides and before the `tenant == ""` /
      `service == ""` fallbacks. Add a comment recording the rollout consequence
      and stating, with a pointer to the #105 precedent already in this file, why
      no key-migration fallback is added.
      — DoD: a `ContainerOOMKilled` alert with `namespace=labs`,
      `pod=labs-mctl-telegram-base-service-744f465c75-dzkhf` creates a ticket with
      `Service == "mctl-telegram"`; label-less infra alerts still reach
      `service == ""` so `isInfraAlert`'s manual-only gate is unaffected.

- [ ] 3. Add a cached service-inventory lookup over
      `mctlclient.Client.ListServices()` and wire it to `AlertHandler.KnownService`
      in `cmd/agent/main.go` (depends on 2). Place it beside the `Poller`, which
      already calls `ListServices()` each tick (`internal/monitor/poller.go:154`)
      and already builds a `tenant+"/"+service` set. Refresh on the poller tick
      and on a miss, with a short negative-result cooldown so an alert burst for
      an unregistered name cannot hammer mctl-api. Must be goroutine-safe and must
      never block or fail ticket creation.
      — DoD: with mctl-api reachable, a candidate registered as `(labs, mctl-telegram)`
      wins over an unregistered one; with mctl-api returning errors, resolution
      still returns the deterministic derivation and no alert is dropped.

- [ ] 4. Delete `detectFilePath` from `internal/skill/builtin/oomkilled.go` and
      route `oomkilled.go:69`, `cpu_throttle.go:84`, `probe_fix.go:87`,
      `rollback.go:72`, `scale_up.go:87` and `llm_diagnosis.go:258` through the
      exported `fixer.DetectFilePath` (`internal/fixer/patcher.go:55`), which
      `internal/pipeline/pipeline.go:670` already uses. Move
      `TestDetectFilePath` (`internal/skill/builtin/builtin_test.go:281`) to the
      `fixer` package tests, keeping its three existing cases.
      — DoD: one implementation and one `PlatformServices` map remain in the repo;
      `grep -rn "detectFilePath" internal/` returns nothing; all six skills
      compile against the exported helper.

- [ ] 5. Add `fixer.CandidatePaths(tenant string, services []string) []string`
      (depends on 4) that maps each candidate service name through
      `DetectFilePath` and deduplicates, preserving order.
      — DoD: `CandidatePaths("labs", []string{"mctl-telegram", "labs-mctl-telegram-base-service"})`
      returns the two `platform-gitops/services/labs/...` paths in that order;
      `CandidatePaths("admins", []string{"mctl-api"})` returns the single
      `platform-gitops/apps/templates/mctl-api.yaml`.

- [ ] 6. Probe candidate paths before patching in `internal/pipeline/pipeline.go`
      (depends on 1, 5). Replace the single `p.github.GetFileContent(ctx, filePath, "main")`
      at line 691 with a bounded loop over `fixResult.FilePath` followed by the
      remaining `fixer.CandidatePaths(t.Tenant, svcname.Candidates(...))` entries.
      Keep `p.github.ValidatePath` inside the loop so no candidate escapes the
      `gitopspath` allowlist; skip (do not fail on) a candidate that fails
      validation. The first path that reads becomes `filePath` for patch
      generation and `CreatePR`. Log at info when a non-first candidate wins, so
      a silent rename is visible in the agent's logs.
      — DoD: the happy path still performs exactly one `GetFileContent`; a ticket
      whose `Service` is stale resolves to the correct file via a later candidate
      and opens a PR against it.

- [ ] 7. Rewrite the read-failure escalation (depends on 6) to name every
      candidate attempted plus the last underlying error, keeping the existing
      "This is an agent-side failure, not necessarily a service failure." framing
      and the existing `p.escalate` + `SendDiagnosis` pair. Wrap the go-github
      error in `fixer.GetFileContent` (`internal/fixer/github.go:248`) with the
      path so the raw `404 Not Found []` stops reaching operators bare.
      — DoD: when no candidate reads, the ticket's `Analysis` lists every
      candidate path, and the Telegram message does too; the ticket still lands in
      `StatusEscalated` (unchanged from today).

- [ ] 8. Update the stale prose (depends on 2). Amend the `pruneOrphans` comment
      in `internal/monitor/poller.go:497-529` to record that the
      `extractService`/base-service mismatch it describes is now resolved at
      ingestion, while stating that the `SourcePolling` restriction is
      deliberately retained pending separate review. Note the canonicalisation
      step in `CLAUDE.md` under the skills/architecture section.
      — DoD: no comment in the repo still claims the ticket `Service` cannot match
      the registry, and `pruneOrphans` behaviour is unchanged.

## Tests

- [ ] T1. `internal/svcname/svcname_test.go` — table test over `Candidates`:
      `("labs", "labs-mctl-telegram-base-service", nil)` leads with
      `"mctl-telegram"` and still contains the raw value last;
      `("admins", "admins-mctl-api-base-service", nil)` leads with `"mctl-api"`;
      `("labs", "labs-mctl-telegram-base-service", {"backstage.io/kubernetes-id": "mctl-telegram"})`
      leads with the label value; the `label_app_kubernetes_io_instance:
      "labs-mctl-telegram"` spelling resolves the same way;
      `("default", "myapp", nil)`, `("default", "two-parts", nil)` and
      `("labs", "labs-something", nil)` are unchanged (no `-base-service`
      signature, so no prefix strip); `("labs", "", nil)` returns empty.
      Plus a `Resolve` test where `known` accepts only the second candidate, and
      one where `known` is nil.

- [ ] T2. `internal/monitor/alerthandler_test.go` — end-to-end through
      `processAlert`: `ContainerOOMKilled`, `namespace=labs`,
      `pod=labs-mctl-telegram-base-service-744f465c75-dzkhf` yields a ticket with
      `Tenant="labs"`, `Service="mctl-telegram"`. A second case with a
      non-base-service pod (`myapp-6d4b5c7f8-abc12` in `default`) yields
      `Service="myapp"` unchanged. A third with `KnownService` returning false for
      everything still yields `"mctl-telegram"` (deterministic fallback).

- [ ] T3. `internal/monitor/alerthandler_test.go` — update the existing assertions
      that encode the old behaviour, one per case with intent stated in the test
      name: lines ~1026/1028, ~1127-1141, ~1180, ~1193, ~1278-1304, ~1328, ~1385
      (`admins-mctl-api-base-service`, `admins-mctl-agents-worker-base-service`).
      Keep `TestExtractService` (line ~84) exactly as-is — `extractService` itself
      is not changing.

- [ ] T4. `internal/monitor/alerthandler_test.go` — regression for the
      `IgnoreService` filter: a firing alert with
      `pod="openclawpr4-base-service-6d4b5c7f8-abc12"` in namespace `openclawpr4`
      is still dropped by a regex matching `openclawpr4` after canonicalisation.

- [ ] T5. `internal/fixer/patcher_test.go` — `DetectFilePath` table (moved from
      `builtin_test.go`) plus `CandidatePaths` order/dedup cases, including the
      `PlatformServices` branch now reachable for `mctl-api` and `mctl-agent`.

- [ ] T6. `internal/pipeline/pipeline_test.go` — with a fake GitHub that 404s the
      first candidate and serves the second, the pipeline opens a PR against the
      second path; with a fake that 404s every candidate, the ticket lands in
      `StatusEscalated` and its `Analysis` contains every candidate path. Assert
      the happy path issues exactly one `GetFileContent`.

- [ ] T7. `internal/pipeline/pipeline_test.go` — a candidate that fails
      `ValidatePath` is skipped rather than aborting the loop, and no read is
      attempted for it.

- [ ] T8. Full `go build ./... && go vet ./... && go test ./...` green; `go fmt`
      clean, per `CLAUDE.md` conventions.

## Rollback

The change is code-only: no schema migration, no new `Ticket` column, no GitOps
manifest change beyond the image tag. Roll back by reverting the release commit
and redeploying the previous image tag through the normal
`chore: release x.y.z` + tag flow described in `CLAUDE.md` (branch + PR, never
directly on `main`); the gitops bump in `.github/workflows/build.yml` handles the
manifest.

Partial de-risking without a full revert:

- Set `AlertHandler.KnownService` to `nil` (drop the wiring from
  `cmd/agent/main.go`) to disable registry verification while keeping the
  deterministic derivation — useful if mctl-api's inventory turns out to be
  unreliable.
- Empty `svcname.ChartFullnameSuffixes` to make `Candidates` return only the raw
  value, restoring today's naming exactly while leaving the candidate-probing
  safety net in task 6 active.

Post-rollback, tickets created under canonical names remain in the store with
those names. They are closed normally by `reconcileWithAlertManager`, which keys
on AlertManager fingerprints rather than on the service name, so no manual
cleanup is required. Expect one more small burst of duplicate notifications as
names swing back, the mirror image of the rollout burst.
