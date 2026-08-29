# Tasks: issue-100-default-auto-merge-enabled-false-honor-c

- [ ] 1. Flip `AUTO_MERGE_ENABLED` default in `internal/config/config.go:95-98`
      from opt-out (`true` unless `"false"`) to opt-in (`false` unless
      `"true"`) — DoD: `Config.AutoMergeEnabled` is `false` when the env var
      is unset or set to anything other than exactly `"true"`; `go build
      ./...` passes.
- [ ] 2. Add `maxPRPerHour`/`maxPRPerDay` fields and constructor params to
      `GitHubFixer` in `internal/fixer/github.go`, and use them in place of
      the hardcoded `5`/`20` in `CreatePR`'s rate-limit check (including the
      error message interpolation) (depends on none, parallel with 1) —
      DoD: `NewGitHubFixer` takes `maxPRPerHour, maxPRPerDay int` as
      trailing params; `CreatePR` compares against `f.maxPRPerHour` /
      `f.maxPRPerDay` and the returned error strings show the actual
      configured limit.
- [ ] 3. Update the `NewGitHubFixer` call site in `cmd/agent/main.go:70` to
      pass `cfg.MaxPRPerHour, cfg.MaxPRPerDay` (depends on 2) — DoD:
      `go build ./...` passes; no other call sites left uncompiled (grep
      confirms `cmd/agent/main.go` is the only non-test caller).
- [ ] 4. Update/extend `internal/config/config_test.go` for the new
      auto-merge default and opt-in semantics (depends on 1) — DoD: see
      T1/T2 below; `go test ./internal/config/...` passes.
- [ ] 5. Add/extend a `GitHubFixer` rate-limit test in `internal/fixer/`
      (depends on 2, 3) — DoD: see T3 below; `go test ./internal/fixer/...`
      passes.
- [ ] 6. Sweep the repo for any other reference to the old hardcoded `5`/
      `20` PR-limit values or to `AutoMergeEnabled`'s old default assumption
      (README, `.claude/skills/*`, comments) and update anything stale
      (depends on 1, 2) — DoD: `grep -rn "hourly PR limit\|daily PR limit\|AUTO_MERGE_ENABLED"`
      across the repo shows no remaining references to the old literal
      defaults or the old "defaults to true" behavior.

## Tests

- [ ] T1. `internal/config`: with `AUTO_MERGE_ENABLED` unset (and cleared
      via `t.Setenv`), `config.Load().AutoMergeEnabled == false`.
- [ ] T2. `internal/config`: table-driven case over `AUTO_MERGE_ENABLED`
      values `{"true" -> true, "false" -> false, "1" -> false, "" -> false,
      "TRUE" -> false}` confirming only the exact string `"true"` enables
      it (matches the strict-match convention used elsewhere in the file).
- [ ] T3. `internal/fixer`: construct `GitHubFixer` with `maxPRPerHour=1,
      maxPRPerDay=20` (dryRun=false) against a real/fake `ticket.Store` with
      1 PR already recorded in the last hour; call `CreatePR`; assert it
      returns an error containing `"hourly PR limit reached (1/1)"` — i.e.
      the configured limit of 1, not the old hardcoded 5. Also assert a
      fixer constructed with the default `maxPRPerHour=5` and the same
      store state does NOT hit the limit, to prove the value is actually
      threaded through rather than coincidentally still comparing to a
      stray literal.
- [ ] T4. `internal/fixer`: same pattern for `maxPRPerDay`, asserting the
      daily-limit error message reflects the configured value.

## Rollback

This is a config-default and constructor-signature change with no data
migration. To roll back:
1. Revert the commit(s) implementing tasks 1-6 (straightforward `git
   revert`, no forward-compatibility concerns since no persisted state or
   wire format changed).
2. Re-tag and redeploy the previous `mctl-agent` image tag via
   `mctl_rollback_service` (or the platform's standard rollback path) if the
   bad version already shipped.
3. If a tenant needs auto-merge restored immediately without a full
   rollback (e.g. because they explicitly relied on the old implicit
   default and the companion `mctl-gitops` change hasn't landed yet), set
   `AUTO_MERGE_ENABLED=true` explicitly in that tenant's deployment env —
   the opt-in path this change introduces is the intended escape hatch and
   requires no code change.

## Operator decisions (approve, 2026-08-29)

- Accepted as proposed, one addition: when AUTO_MERGE_ENABLED is set to an
  unrecognized value ("1", "TRUE", "yes", ...), log a warning naming the
  raw value before treating it as false — a silently-ignored truthy intent
  is how fail-closed defaults turn into invisible outages.
- Land order: this PR merges BEFORE issue-99 (both touch the
  `NewGitHubFixer` signature and `cmd/agent/main.go` wiring); issue-99
  rebases on top.
