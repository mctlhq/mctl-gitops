# Tasks: issue-99-path-allowlist-for-gitops-writes-remote

- [ ] 1. Add `internal/gitopspath` package with `Allowlist` type and
      `Validate(path string) error` (traversal, absolute-path, and
      prefix-membership checks over posix-style `/`-separated paths) —
      DoD: package compiles standalone, no dependency on `fixer`/`github`,
      exported `NewAllowlist([]string)` and `DefaultAllowlist()`.

- [ ] 2. Add `GitOpsPathAllowlist []string` to `internal/config.Config`,
      parsed from `GITOPS_PATH_ALLOWLIST` (comma-separated, trimmed),
      defaulting to `["platform-gitops/services/",
      "platform-gitops/apps/templates/",
      "platform-gitops/argo-workflows/workflow-templates/"]` when unset —
      DoD: `config_test.go` covers default and override, following the
      existing `envOr`/comma-split pattern already used for
      `TELEGRAM_TENANT_CHAT_IDS`.

- [ ] 3. Thread the allowlist into `fixer.NewGitHubFixer` (new param) and
      enforce `allowlist.Validate(path)` at the top of both
      `GitHubFixer.GetFileContent` and `GitHubFixer.CreatePR`, returning a
      wrapped error on rejection before any GitHub API call — DoD:
      `internal/fixer/github_test.go` (new or extended) covers a traversal
      path, an absolute path, and an out-of-prefix path all returning an
      error with no HTTP call made (use `httptest`/a fake `*github.Client`
      transport already used by the package's existing tests, or add a
      minimal interface seam if none exists — check `token_test.go` /
      `previous_tag_test.go` for the established mocking pattern first).
      (depends on 1, 2)

- [ ] 4. Add a symlink check: after fetching `RepositoryContent` in both
      `GetFileContent` and `CreatePR`, reject if `GetType() == "symlink"` —
      DoD: unit test with a fake GetContents response of type `"symlink"`
      returns an error and never reaches `UpdateFile`. (depends on 3)

- [ ] 5. Validate `filePath` in
      `pipeline.Pipeline.handleHighConfidenceFix` immediately after it is
      resolved from `fixResult.FilePath` / `fixer.DetectFilePath`, routing
      a rejection through the existing "patch generation failed" handling
      (same `t.Status = ticket.StatusFixProposed`, Telegram message,
      `webhook.EventTicketFixFailed`) — DoD:
      `internal/pipeline/pipeline_test.go` / `processticket_test.go` gains
      a case where a stub skill returns `FixResult.FilePath =
      "../.github/workflows/ci.yml"` and asserts no PR is created and the
      ticket lands in `StatusFixProposed` with a logged rejection.
      (depends on 1, 2)

- [ ] 6. Add `skill.AllCapabilityIDs() []CapabilityID` to
      `internal/skill/skill.go` as the single source of truth for the
      known capability enum — DoD: existing `CapReadLogs`...`CapExecWorkflow`
      constants are all included; a table test asserts the slice length
      matches the const block (regression guard against a future constant
      being added without updating the helper).

- [ ] 7. Add `internal/skill/remote/validate.go` with
      `ValidateRegistration(reg Registration) error`: require `https://`
      scheme + non-empty host; resolve host via
      `net.DefaultResolver.LookupIPAddr` and reject if the literal or any
      resolved IP is loopback/private/link-local/CGNAT
      (`100.64.0.0/10`); reject any `reg.Capabilities` entry not in
      `skill.AllCapabilityIDs()` — DoD: table-driven test covering
      `http://...`, `https://169.254.169.254/`, `https://10.0.0.5/`,
      `https://[::1]/`, an unknown capability string, and a valid
      `https://public-host/` + known capabilities case, each with an
      httptest-backed fake resolver or `net.ParseIP` literal-host inputs
      (avoid live DNS in tests). (depends on 6)

- [ ] 8. Call `ValidateRegistration(reg)` at the top of
      `remote.Manager.Register`, returning its error unchanged so the
      existing `remoteSkillRegisterHandler` 400 path is exercised —
      DoD: `internal/api/router_test.go` gains cases for the
      `POST /api/v1/skills/register` endpoint asserting `http://` and a
      10.x endpoint return 400 with the validation error message, and a
      valid `https://` registration still returns 201. (depends on 7)

- [ ] 9. Harden `remote.New`'s `http.Client` with a custom
      `Transport.DialContext` that resolves the dial address and refuses
      to connect if the resolved IP is denied (same `isDeniedIP` helper as
      task 7, factored into a shared function to avoid policy drift) —
      DoD: a test standing up an `httptest.Server` on `127.0.0.1` and
      calling through `Skill.post` (bypassing `ValidateRegistration`, i.e.
      constructing the `Skill` directly) confirms the dial is refused,
      proving registration-time and connection-time checks share one
      source of truth. (depends on 7)

- [ ] 10. Wire `internal/capability` into the pipeline: replace direct
      `p.github.GetFileContent` / `p.github.CreatePR` /
      `p.github.LookupPreviousImageTag` (used by `rollbackImage`) /
      `p.telegram.*` calls inside `handleHighConfidenceFix` and
      `rollbackImage` with calls through a `capability.Context` built via
      `capability.NewContext(p.provider, s, t, ev)`; add a
      `LookupPreviousImageTag` passthrough to `capability.Provider`/
      `Context` gated on `CapModifyGitOps` — DoD: `p.provider` is read
      somewhere in `pipeline.go` (grep confirms), and
      `capability_test.go`-style tests confirm a skill missing
      `CapModifyGitOps`/`CapCreatePR` gets an error instead of a PR.
      (depends on 3, 4)

- [ ] 11. Audit and update every builtin skill in
      `internal/skill/builtin/*.go` (oomkilled, image_pull/imagepull,
      rollback, argocd_drift, probe_fix, cpu_throttle, quota_adjust,
      scale_up, llm_diagnosis — 9 total per `CLAUDE.md`) to declare
      `RequiredCapabilities()` including `CapModifyGitOps` + `CapCreatePR`
      (and `CapReadLogs`/`CapReadStatus`/etc. where each skill's `Diagnose`
      already reads that data), so task 10's enforcement doesn't break
      existing fix flows — DoD: `builtin_test.go` gains a test that runs
      every registered builtin skill through a `capability.Context` built
      from its own declared capabilities and confirms `CreatePR`/
      `GetFileContent` are not rejected for missing capabilities.
      (depends on 10)

- [ ] 12. Update `cmd/agent/main.go` if the `fixer.NewGitHubFixer` /
      `capability.NewProvider` constructor signatures changed (task 3) to
      pass `cfg.GitOpsPathAllowlist` — DoD: `go build ./...` passes;
      `main_test.go` (if it exercises wiring) still passes.
      (depends on 2, 3, 10)

- [ ] 13. Update `CHANGELOG.md` and note the breaking change for
      previously-registered `http://`/private-range remote skills (they
      must be re-registered) — DoD: entry added under the next unreleased
      version per `release-please-config.json` convention.
      (depends on 8, 9)

## Tests

- [ ] T1. `gitopspath` unit tests: reject `../.github/workflows/ci.yml`,
      `/etc/passwd`, `bootstrap/x.yaml`, accept
      `platform-gitops/services/acme/api/values.yaml` and the two
      `workflow_fixer.go` literal paths against the default allowlist.
- [ ] T2. `GitHubFixer.CreatePR`/`GetFileContent` reject out-of-allowlist
      paths and symlink-typed existing content before any `UpdateFile`
      call (mock/fake transport, no network).
- [ ] T3. Pipeline-level test: a fake skill returning
      `FixResult{FilePath: "../.github/workflows/ci.yml", Applied: true}`
      results in no PR, `StatusFixProposed`, and an
      `EventTicketFixFailed` webhook event.
- [ ] T4. `remote.ValidateRegistration` table test: `http://good-host/`
      rejected (scheme); `https://169.254.169.254/` rejected (link-local /
      cloud metadata); `https://10.1.2.3/` rejected (private); `https://
      [::1]/` rejected (loopback v6); `https://100.64.1.1/` rejected
      (CGNAT); unknown capability `"delete_everything"` rejected; valid
      `https://skills.example.com/` with `["read_logs","modify_gitops"]`
      accepted.
- [ ] T5. `POST /api/v1/skills/register` integration test (via
      `internal/api/router_test.go` harness) for the same accept/reject
      matrix as T4, asserting HTTP status codes.
- [ ] T6. Connection-time dialer test: registering (or directly
      constructing) a `remote.Skill` pointed at an `httptest.Server`
      listening on loopback is refused at dial time even if
      `ValidateRegistration` were bypassed.
- [ ] T7. Capability-wiring test: a stub skill with
      `RequiredCapabilities() == []` gets an error from `capCtx.CreatePR`
      / `capCtx.GetFileContent` inside the pipeline flow, and no PR is
      opened.
- [ ] T8. Regression test: every builtin skill's declared
      `RequiredCapabilities()` is sufficient for its own `Fix()` output to
      pass both the capability check (task 10/11) and the path allowlist
      check (task 1) — i.e. the full legitimate flow still produces a PR
      end to end against a fake GitHub backend.

## Rollback

- All changes are additive/config-gated: `GITOPS_PATH_ALLOWLIST` defaults
  to the paths already in production use, so a bad rollout can be
  mitigated first by widening the env var (e.g. add a missing prefix)
  without a code rollback.
- If the capability-wiring change (task 10/11) rejects a legitimate skill
  in production, the immediate mitigation is to add the missing
  `CapabilityID` to that skill's `RequiredCapabilities()` and redeploy —
  a one-line, low-risk fix — rather than reverting the whole feature.
- Full rollback path: revert the merge commit(s) for this proposal (single
  PR per repo convention — see `CLAUDE.md` release process) and redeploy
  the previous image tag via `mctl_rollback_service` / the existing
  gitops-tag rollback mechanism; no database migration exists to unwind.
- Remote skills re-registered under the new HTTPS/capability rules remain
  valid after a rollback (the `Registration` struct is unchanged), so
  rollback does not require re-registering skills a second time.
