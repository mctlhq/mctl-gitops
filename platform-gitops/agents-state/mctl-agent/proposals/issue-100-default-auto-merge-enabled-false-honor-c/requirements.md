# Default AUTO_MERGE_ENABLED to false; honor configured PR rate limits

## Context
`internal/config/config.go:95-98` defaults `AutoMergeEnabled` to `true` when
the `AUTO_MERGE_ENABLED` env var is unset, and the gitops deployment
(`bootstrap/templates/mctl-platform/mctl-agent.yaml:57` in `mctl-gitops`,
out of scope here) does not set that env var while `DRY_RUN` is `"false"`.
Combined with three builtin skills that already report
`AutoMergeSafe() == true` (`internal/skill/builtin/oomkilled.go:75`,
`internal/skill/builtin/cpu_throttle.go:79`, `internal/skill/builtin/probe_fix.go:82`),
this means agent-authored PRs against `mctl-gitops` main can merge today
with no human in the loop, purely because a boolean default was chosen the
wrong way round. Separately, `internal/fixer/github.go:85-89` hardcodes the
hourly (5) and daily (20) PR-creation limits as literals instead of reading
`cfg.MaxPRPerHour` / `cfg.MaxPRPerDay`, which are parsed from
`MAX_PR_PER_HOUR` / `MAX_PR_PER_DAY` in `internal/config/config.go:81-93`
but never reach `GitHubFixer` — so those env vars are silently inert.

This proposal flips the auto-merge default to safe (off) and wires the
already-parsed rate-limit config into the one place that currently ignores
it, so operators can actually tighten (or loosen) PR throughput without a
code change.

## User stories
- AS a platform operator I WANT `mctl-agent` to default to no auto-merge SO
  THAT a fresh or misconfigured deployment never merges unreviewed fixes
  into `mctl-gitops` main.
- AS a platform operator I WANT to opt in to auto-merge explicitly via
  `AUTO_MERGE_ENABLED=true` SO THAT the capability still exists once an
  allowlist / review gate is in place.
- AS a platform operator I WANT `MAX_PR_PER_HOUR` / `MAX_PR_PER_DAY` to
  actually govern how many PRs `mctl-agent` opens SO THAT I can throttle a
  noisy or misbehaving skill without redeploying a new image.

## Acceptance criteria (EARS)
- WHEN `config.Load()` runs with `AUTO_MERGE_ENABLED` unset THE SYSTEM
  SHALL set `Config.AutoMergeEnabled` to `false`.
- WHEN `config.Load()` runs with `AUTO_MERGE_ENABLED=true` THE SYSTEM SHALL
  set `Config.AutoMergeEnabled` to `true`.
- WHEN `config.Load()` runs with `AUTO_MERGE_ENABLED` set to any value other
  than exactly `"true"` (e.g. `"1"`, `"TRUE"`, `""`) THE SYSTEM SHALL leave
  `Config.AutoMergeEnabled` at `false`, preserving the existing
  strict-match style already used for `DRY_RUN=="false"` and
  `WEBHOOK_ENABLED=="true"` in the same file.
- WHEN `GitHubFixer.CreatePR` checks the hourly count THE SYSTEM SHALL
  compare it against the fixer's configured `maxPRPerHour` instead of the
  literal `5`.
- WHEN `GitHubFixer.CreatePR` checks the daily count THE SYSTEM SHALL
  compare it against the fixer's configured `maxPRPerDay` instead of the
  literal `20`.
- WHEN `NewGitHubFixer` is constructed in `cmd/agent/main.go` THE SYSTEM
  SHALL pass `cfg.MaxPRPerHour` and `cfg.MaxPRPerDay` through to it.
- IF `MAX_PR_PER_HOUR` / `MAX_PR_PER_DAY` are unset THEN THE SYSTEM SHALL
  keep behaving exactly as today (limits of 5 and 20), since
  `internal/config/config.go:81-93` already defaults them to those values.
- WHILE `Config.DryRun` is `true` THE SYSTEM SHALL continue to short-circuit
  `CreatePR` before the rate-limit check runs (unchanged from today,
  `internal/fixer/github.go:68-74`), so this change only affects real
  PR-creating runs.
- WHEN the error message for a hit rate limit is emitted THE SYSTEM SHALL
  include the configured limit value (not a stale hardcoded number), e.g.
  `"hourly PR limit reached (%d/%d)"` formatted with the actual configured
  limit.

## Out of scope
- The `mctl-gitops` values/deployment change that sets `AUTO_MERGE_ENABLED`
  explicitly for prod — companion issue in `mctl-gitops`, cross-linked from
  #100. This proposal only changes `mctl-agent` code defaults and tests.
- Building the path allowlist referenced in the issue
  ("mctlhq/mctl-agent#99-area work") that would gate what auto-merge is
  allowed to touch. That is a separate, larger proposal.
- Any change to which skills report `AutoMergeSafe() == true`
  (`oomkilled`, `cpu_throttle`, `probe_fix` keep their current values) —
  the issue only asks to change the *default enablement*, not skill-level
  safety judgments.
- Adding new env vars for rate limiting; `MAX_PR_PER_HOUR` /
  `MAX_PR_PER_DAY` already exist and are parsed — this proposal only makes
  the fixer consume the already-existing `Config` fields.

## Open questions
- None. The issue is fully specified: flip the `AutoMergeEnabled` default,
  thread `cfg.MaxPRPerHour`/`MaxPRPerDay` into the fixer, and add tests for
  both. Where the issue is silent (exact match semantics for
  `AUTO_MERGE_ENABLED=true`), this proposal follows the existing pattern
  already used by every other boolean flag in `internal/config/config.go`
  (e.g. `DRY_RUN`, `WEBHOOK_ENABLED`, `AM_RECONCILE_ENABLED`) for
  consistency rather than inventing a new parsing convention.
