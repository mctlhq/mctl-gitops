# Design: issue-100-default-auto-merge-enabled-false-honor-c

## Current state

**Auto-merge default.** `internal/config/config.go:95-98`:
```go
autoMergeEnabled := true
if v := os.Getenv("AUTO_MERGE_ENABLED"); v == "false" {
    autoMergeEnabled = false
}
```
This is an opt-out pattern: the flag starts `true` and only a literal
`"false"` turns it off. `Config.AutoMergeEnabled` flows unchanged into
`pipeline.NewPipeline` at `cmd/agent/main.go:107` as the `autoMerge`
constructor arg, and is read at `internal/pipeline/pipeline.go:601`:
```go
shouldAutoMerge := p.autoMerge && !p.dryRun
if shouldAutoMerge {
    if am, ok := s.(skill.AutoMerger); !ok || !am.AutoMergeSafe() {
        shouldAutoMerge = false
    }
}
```
So today, any deployment that sets `DRY_RUN=false` and leaves
`AUTO_MERGE_ENABLED` unset gets auto-merge for any skill whose
`AutoMergeSafe()` returns `true` — currently `OOMKilledSkill`,
`CPUThrottleSkill`, and `ProbeFixSkill`
(`internal/skill/builtin/oomkilled.go:75`,
`internal/skill/builtin/cpu_throttle.go:79`,
`internal/skill/builtin/probe_fix.go:82`). The gitops deployment referenced
in the issue does not set `AUTO_MERGE_ENABLED`, so prod is exposed to this
by omission, not by explicit choice.

**PR rate limits.** `internal/config/config.go:44-45,81-93` already parses
`MAX_PR_PER_HOUR` (default 5) and `MAX_PR_PER_DAY` (default 20) into
`Config.MaxPRPerHour` / `Config.MaxPRPerDay`. But `GitHubFixer` — the only
consumer of these limits — never receives them. `NewGitHubFixer` in
`internal/fixer/github.go:42-54` takes `(token, tokenFile, owner, repo,
store, dryRun)` with no rate-limit params, and is constructed at
`cmd/agent/main.go:70`:
```go
githubFixer := fixer.NewGitHubFixer(cfg.GitHubToken, cfg.GitHubTokenFile, cfg.GitHubOwner, cfg.GitHubRepo, store, cfg.DryRun)
```
Inside `CreatePR` (`internal/fixer/github.go:76-90`), the check is hardcoded:
```go
if hourCount >= 5 {
    return "", 0, fmt.Errorf("hourly PR limit reached (%d/5)", hourCount)
}
if dayCount >= 20 {
    return "", 0, fmt.Errorf("daily PR limit reached (%d/20)", dayCount)
}
```
`Config.MaxPRPerHour`/`MaxPRPerDay` are exercised only by
`internal/config/config_test.go` (asserting the parsed value lands on
`Config`) — nothing downstream reads them, which is exactly the "config
field that does nothing" bug the issue reports.

## Proposed solution

1. **Flip the default in `internal/config/config.go`.** Change the
   `autoMergeEnabled` initializer from `true` to `false`, and match on
   `v == "true"` instead of `v == "false"`:
   ```go
   autoMergeEnabled := false
   if v := os.Getenv("AUTO_MERGE_ENABLED"); v == "true" {
       autoMergeEnabled = true
   }
   ```
   This mirrors the existing opt-in style already used for
   `WEBHOOK_ENABLED` (`config.go:100-103`) and `AM_RECONCILE_ENABLED`'s
   sibling opt-out style — the point is not stylistic consistency for its
   own sake but that auto-merge, like webhook dispatch, is a capability
   that should require deliberate enablement rather than accidental
   inheritance of a permissive default. No other field in `Config`
   changes.

2. **Thread `MaxPRPerHour`/`MaxPRPerDay` into `GitHubFixer`.** Add two
   fields to the `GitHubFixer` struct in `internal/fixer/github.go` and two
   parameters to `NewGitHubFixer`:
   ```go
   type GitHubFixer struct {
       client       *github.Client
       owner        string
       repo         string
       store        *ticket.Store
       dryRun       bool
       maxPRPerHour int
       maxPRPerDay  int
   }

   func NewGitHubFixer(token, tokenFile, owner, repo string, store *ticket.Store, dryRun bool, maxPRPerHour, maxPRPerDay int) *GitHubFixer {
       ...
       return &GitHubFixer{
           ...
           maxPRPerHour: maxPRPerHour,
           maxPRPerDay:  maxPRPerDay,
       }
   }
   ```
   Update the two comparisons in `CreatePR` to use `f.maxPRPerHour` /
   `f.maxPRPerDay`, and interpolate the actual limit into the error
   message instead of the literal `5`/`20` so the error stays truthful if
   an operator overrides the default:
   ```go
   if hourCount >= f.maxPRPerHour {
       return "", 0, fmt.Errorf("hourly PR limit reached (%d/%d)", hourCount, f.maxPRPerHour)
   }
   if dayCount >= f.maxPRPerDay {
       return "", 0, fmt.Errorf("daily PR limit reached (%d/%d)", dayCount, f.maxPRPerDay)
   }
   ```

3. **Update the call site.** `cmd/agent/main.go:70` passes
   `cfg.MaxPRPerHour, cfg.MaxPRPerDay` as the two new trailing args. Since
   `Config` already defaults these to 5/20 when the env vars are unset
   (`internal/config/config.go:81-93`), behavior for deployments that don't
   set `MAX_PR_PER_HOUR`/`MAX_PR_PER_DAY` is unchanged — only deployments
   that *do* set them start actually being honored, which is the bug fix.

4. **Tests.**
   - `internal/config/config_test.go`: extend `TestLoadDefaults` (or add a
     dedicated test) to assert `cfg.AutoMergeEnabled == false` with the env
     var unset, and add a case asserting `AUTO_MERGE_ENABLED=true` yields
     `true` while any other value (e.g. `"false"`, `"1"`, `""`) yields
     `false`.
   - `internal/fixer/` (new or extended `github_test.go`): construct a
     `GitHubFixer` with a low limit (e.g. `maxPRPerHour=1`) against a fake
     `ticket.Store` / stubbed count, call `CreatePR` twice, and assert the
     second call returns the "hourly PR limit reached" error referencing
     the configured value, not the old hardcoded `5`. If `ticket.Store`
     isn't trivially fakeable, use its existing test helpers/sqlite test
     DB pattern already present in the package (check `internal/ticket` and
     existing fixer tests for the established DB-setup helper before
     inventing a new one).

## Alternatives

1. **Only flip the default, leave rate limits hardcoded.** Rejected: the
   issue explicitly asks for both, and the rate-limit bug is the same
   class of problem (a `Config` field that silently does nothing) — fixing
   only half leaves `MAX_PR_PER_HOUR`/`MAX_PR_PER_DAY` operators believe
   they can tune throughput when they cannot.

2. **Pass the whole `*config.Config` into `GitHubFixer` instead of two
   ints.** Rejected: `GitHubFixer` currently takes discrete primitives
   mirroring exactly what it needs (`token, tokenFile, owner, repo, store,
   dryRun`), and other fixer-adjacent code (`internal/fixer/token.go`)
   follows the same narrow-dependency style. Taking a full `Config` would
   couple the fixer to unrelated fields (Telegram, webhook, alert-resolve
   timers) it has no business reading, purely to save two constructor
   params.

3. **Read `MaxPRPerHour`/`MaxPRPerDay` from env directly inside
   `internal/fixer/github.go` instead of threading through `Config`.**
   Rejected: `internal/config` is already the single place all env parsing
   happens in this codebase (see the package doc comment style and every
   other `Config` field) — a second env-read site would duplicate parsing
   logic and defeat the purpose of `config_test.go` as the one place
   defaults are verified.

## Platform impact

- **Migrations:** none — no schema, no new persisted state.
- **Backward compatibility:** this is a behavior-changing default. Any
  environment that relies on today's implicit `AutoMergeEnabled=true` (with
  `DRY_RUN=false` and `AUTO_MERGE_ENABLED` unset) will silently switch to
  manual-review mode after this ships, until/unless the companion
  `mctl-gitops` change (out of scope here, see issue) sets
  `AUTO_MERGE_ENABLED=true` explicitly for any tenant that actually wants
  auto-merge. This is the intended effect of the issue (fail safe by
  default) and should be called out in the release notes / PR description
  for reviewers who know which tenants currently depend on auto-merge.
- **Resource impact:** none — no new I/O, no new dependencies.
- **Risks + mitigations:**
  - Risk: a tenant currently depending on silent auto-merge loses it
    without immediate notice. Mitigation: `internal/pipeline/pipeline.go:620`
    already falls back to `SendPRNeedsReview` when auto-merge doesn't fire,
    so PRs still get created and a human is still notified via Telegram —
    the only change is that a human must click through instead of it
    merging unattended. No tickets get silently dropped.
  - Risk: `NewGitHubFixer`'s signature change breaks any other caller.
    Mitigation: grep confirms `cmd/agent/main.go:70` is the only
    non-test call site; test call sites are updated in the same change.
  - Risk: rate-limit error message format change
    (`"%d/%d"` vs `"%d/5"`) could break a test or downstream string match
    on the literal `"5"`/`"20"`. Mitigation: grep the repo for those exact
    substrings before landing to confirm nothing else parses the error
    text (Telegram notification code sends `err.Error()` through
    verbatim, it does not pattern-match it — see
    `internal/pipeline/pipeline.go:578-581`).
