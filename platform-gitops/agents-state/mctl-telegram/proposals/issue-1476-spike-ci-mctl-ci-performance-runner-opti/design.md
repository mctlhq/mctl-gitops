# Design: issue-1476-spike-ci-mctl-ci-performance-runner-opti

Disposition: a research proposal. Approving it authorizes read-only evidence collection and building (not dispatching) one controlled benchmark harness on a scratch branch. Dispatching that harness needs a separate authorization, given only after a runner-minute cap and a queue-regression tolerance are agreed with mctlhq/mctl-gitops#2993. Changing `build.yml`, rulesets, required contexts or runners requires a separate, independently reviewed implementation proposal.

## Current state

### Workflows (clone HEAD `c74249b9cbd01c88a54e7f86e1431e0f4db116f2`, 2026-11-27)

- `.github/workflows/build.yml` triggers on `pull_request` to `main` only. It has no `merge_group`, no `push`, no `paths` filter and no `concurrency` block. It defines 16 jobs. All of them use hosted runners (`ubuntu-latest`, plus `macos-latest` and `windows-latest` in the `test-cross-platform` matrix).
  - `test` (lines 11-172) runs everything serially on one runner, with a `postgres` 17.2 service pinned by digest. The order is:
    1. Restore `actions/cache` with key `go-race-<os>-<hash(go.sum)>-<sha>`.
    2. `go vet ./...`, then `go vet -tags livetg ./internal/telegram/`, then `go build ./...`.
    3. `go test -race -timeout 20m ./...`. The comment at lines 80-83 notes that `internal/pa` and `internal/db` crossed the default 10m per-package timeout on #1421 and #1432.
    4. The node handshake test.
    5. The PA S1 gate (`go test -count=1 ./docs -run S1Manifest`).
    6. Vet and `-race` test of `test/glovo-poc`, then of `provider/glovo`.
    7. The Postgres no-skip guard, with an `expected=14` floor.
  - The comments at lines 195-198 and 387-389 record that renaming a required check (for example by adding a matrix) would leave the required context `test` or `docker` pending forever. Any redesign must keep those context names.
  - `cross-build` and `test-cross-platform` use `setup-go` with its default `cache: true`. The `docker*` jobs use `cache-to: type=gha,mode=max`. Both therefore write PR-scoped caches. The live cache list showed `setup-go-Windows-...` (349 MB), `setup-go-macOS-arm64-...` (417 MB) and many `buildkit-blob-*` entries on `refs/pull/1474/merge`. That contradicts the intent stated for `test` at lines 51-56 ("PR-scoped caches ... only push the repository past its cache quota").
- `.github/workflows/go-cache.yml` runs on `push` to `main` with `concurrency: go-cache, cancel-in-progress: true`. It warms the cache with `go test -race -count=1 -run '^$' ./...` for the root module only and deletes superseded `go-race-*` keys. It does not warm `test/glovo-poc` or `provider/glovo`. It restores the previous cache before saving a new one, so stale build-cache entries can accumulate across saves.
- `codeql.yml` (`Analyze (go)`), `agy-review.yml` (reusable `mctlhq/.github` workflow), `claude-review.yml`, `agent-trailer-check.yml` and `sticky-ingress-acceptance.yml` also run on PRs. `release-please.yml` runs on push to `main` and opens the release PR with an App token, so the release PR gets the full `build`.

### Components

| Component | Module | Image | Shared root packages |
|---|---|---|---|
| Telegram MCP | root | `Dockerfile` (`COPY . .`) | all |
| PA agent worker | root | `Dockerfile.agent-worker` (`COPY . .`) | all |
| Glovo MCP | root (`cmd/glovo-mcp`, `internal/glovo/...`) | `Dockerfile.glovo-mcp` (`COPY cmd/glovo-mcp`, `COPY internal`) | `internal/auth`, `internal/audit`, `internal/metrics`, `internal/edgectx`, `internal/jsonstrict` (from `go list -deps ./cmd/glovo-mcp`) |
| Fake-provider worker | nested `provider/glovo` | `Dockerfile.glovo-provider-worker` | none (separate `go.mod`) |
| Glovo PoC | nested `test/glovo-poc` (Temporal SDK) | none | none |

`internal/pa/egress_guard_test.go` asserts import boundaries that involve `internal/glovo/authn` and `internal/glovo/mctlapi`. This test couples PA to the Glovo packages, so Glovo cannot be cleanly separated from PA by path alone.

### Measured baseline (read-only, `gh api`, 2026-11-27)

The sample is the latest 100 runs of `build.yml` (`actions/workflows/build.yml/runs?per_page=100`). All 100 are `pull_request` events, created 2026-11-24T11:54:17Z to 2026-11-27T11:12:39Z. Conclusions: 84 success, 14 failure, 1 cancelled, 1 in progress at the time of listing. Two runs have `run_attempt=2`. Jobs were fetched with `filter=latest` and the analysis was run with a local script. That script, the run list and the job JSON are not committed and must be regenerated (task 1).

| Metric | n | p50 | p90 | p95 | max |
|---|---|---|---|---|---|
| Run wall (first job created to last job done) | 100 | 25.0m | 28.9m | 34.6m | 46.0m |
| `test` execution (successful) | 91 | 23.9m | 26.9m | 27.2m | 29.1m |
| `test` queue wait | 91 | 0.0m | 5.4m | 9.2m | 16.9m |
| `test` cache restore step | 91 | 1.9m | 2.6m | 2.7m | 3.2m |
| `test` `go test -race` step | 91 | 18.6m | 22.6m | 22.8m | 24.2m |
| `test` serial tail after `go test -race` | 91 | 1.7m | 1.9m | 1.9m | 2.0m |
| macOS cross-platform | 90 | 7.8m | 10.5m | 11.4m | 13.2m |
| `docker` | 85+ | 3.0m | 3.5m | 3.5m | 4.0m |
| `docker-glovo-mcp` | 85+ | 1.5m | 2.0m | 2.1m | 2.3m |
| `docker-glovo-provider-worker` | 85+ | 1.0m | 1.3m | 1.4m | 1.8m |

- Last job to finish: `test` in 97 runs, and `cross-build`, `publish-script` and `macos` in 1 run each. No Glovo job was ever last.
- Failure counts: `test` 7, macOS 4, `product-updates` 2. macOS was cancelled 6 times. Flake attribution needs reruns of the same SHA, which this sample does not include.
- The sum of job execution time is about 4603 minutes per 100 runs (mixed OS, unrounded). Of that, `test` accounts for about 23.9m per run.
- PR #1475, run 45466703355, job 138703397953 (`test`): created 19:06:36, started 19:06:47, completed 19:27:21 (20m34s), so this was the blocking required job. Its steps:
  - cache restore: 3m01s
  - vet + vet livetg + build: 30s
  - `go test -race`: 15m07s
  - PA S1: 7s
  - Glovo PoC vet+test: 38s
  - provider vet+test: 18s
  - Postgres guard: 19s
  The macOS job in this run sat queued from 19:06:36 to 19:21:37 with no runner and no steps, and was then cancelled. The reason is not observed.
- PR #1481, run 45792964722 (release-only diff): `test` ran 09:32:51-10:00:18 (27m27s), with a cache restore of 2m44s and `go test -race` of 21m52s. Both Glovo docker jobs finished by 09:34:01. Glovo did not determine the run's wall clock.
- Per-package `go test -race` times from the #1475 log (105 `ok` packages, sum 2252s): `internal/pa` 591s, `internal/db` 354s, `cmd/server` 302s, `internal/oauth` 177s, `internal/mcp` 143s, `internal/agentapi` 98s, `internal/web` 66s. `internal/pa` alone is about 65% of the 15m07s step. With `go test`'s default `-p` package parallelism, the step cannot finish faster than its slowest package plus compile time.
- Test-level parallelism: in `internal/pa` (378 `Test*` functions), `internal/db` (603), `cmd/server` (115), `internal/oauth` (379) and `internal/mcp` (451), `t.Parallel()` appears 0 times. The test files in those packages contain 14, 12, 5, 8 and 1 `time.Sleep` calls respectively.
- Caches: `go-race-Linux-...-c74249b9` is 4211 MB. Repository cache usage is 12.67 GB in 206 entries (`actions/cache/usage`), which is above the default 10 GB quota, so GitHub is evicting entries.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: image `ghcr.io/mctlhq/mctl-telegram`, tag `b773df01`. The service is deployed in tenant `labs`.
- `$MCTL_GITOPS_ROOT/services/labs/{agent-worker-preview,agent-worker-pa-preview,agent-worker-managed-preview,mctl-telegram-preview}` exist and reference this repo's images.
- `grep -rl glovo $MCTL_GITOPS_ROOT/services`: no matches. No Glovo MCP or fake-provider service appears in gitops. This is consistent with the "no push, nothing deploys this image" comments in `build.yml`.
- `GET repos/mctlhq/mctl-telegram/branches/main/protection/required_status_checks`: HTTP 403. Not observed.
- `GET repos/mctlhq/mctl-telegram/rulesets` and `rules/branches/main`: `[]`. Org rulesets and merge-queue settings are not observed. An empty list visible to this token is not proof that there are none.
- The mctl MCP tools were not called. The CI questions here do not depend on runtime service state.

## Proposed solution

The spike runs in three phases. Each phase produces evidence, not changes to `main`.

### Phase R1: full baseline (S0)

Extend the measurement above into a committed, re-runnable script in a research branch or an attachment to the issue, not in `build.yml`. The script:
- pins `build.yml` blob SHAs per run (`head_sha`);
- covers `push` and release (`release-please.yml`, `go-cache.yml`) runs, and `merge_group` runs if any exist;
- splits queue wait from execution;
- records the cache-hit outcome of each `test` run (the `Cache restored from key` line, or the restore-step duration as a proxy);
- runs a per-package and per-test (`go test -json`) profile of `internal/pa`, `internal/db`, `cmd/server` and `internal/oauth` from a trusted run;
- counts superseded runs: runs on a PR ref that a newer push made obsolete.

Queue figures are correlated with the #2993 saturation windows. Correlation is not presented as causation.

### Phase R2: controlled benchmark of the Linux critical path (S1)

Candidates are benchmarked on a scratch branch with `workflow_dispatch`, synthetic inputs and no secrets, against the current `test` job as the control. Benchmark protocol:

- Control and candidate runs are interleaved, so each comparison happens under comparable runner conditions. Every sample records its run and job IDs, with execution and queue latency kept separate.
- Ten repetitions per variant is the starting point. The sample grows while the variance makes p95 unreliable, and every percentile is reported with its uncertainty (for example a bootstrap interval). The target stays a reduction of at least 30% in `test` p95.
- Before dispatch, a runner-minute cap and a queue-regression tolerance are agreed with #2993, and the benchmark gets its own authorization. Scheduling is coordinated with #2993 and #2931.
- Capacity impact: each candidate is measured on org-wide runner minutes, queue delay, runner saturation and the failure/flake rate, not only on its own wall clock. A local speedup that pushes the shared queue past the agreed tolerance is rejected.
- Coverage equivalence: the harness compares an exact test inventory, built from `go test -json` of the control and of the candidate: package, test and subtest identity, pass/fail/skip status, build tags, the race-enabled package set, and the results of the mandatory gates (race, PostgreSQL no-skip, PA S1, both nested modules, CodeQL, govulncheck, product-updates). An equal or larger test count is not evidence. Negative fixtures (a missing test, changed build tags, a skipped Postgres case, a missing shard) must each make the comparison fail.

Ranked by expected value:

1. **Package-sharded race test behind a stable aggregate `test` gate.** Shards run `go test -race`, and each shard has its own Postgres service and cache restore:
   - shard A: `internal/pa`
   - shard B: `internal/db` + `internal/oauth`
   - shard C: `cmd/server`
   - shard D: the remaining packages, computed as `go list ./...` minus A-C, so that a new package lands in D automatically
   - shard E: node handshake + PA S1 + both nested Glovo modules

   Every shard that runs Postgres-backed tests carries its own no-skip guard in its race run. The per-shard floors come from the task 3 inventory and together cover at least today's `expected=14`.

   A final job keeps the required name `test`. It `needs` all shards, runs with `if: always()`, and fails unless every shard's result is `success`: a missing, skipped, cancelled or failed shard fails it. It also checks that the union of packages tested equals `go list ./...` (fail closed). Estimated gain, to be validated: `test` p95 from 27.2m to about 13-15m, bounded by `internal/pa` (591s on #1475) plus restore and compile. Runner minutes rise by roughly 4 restores plus Postgres start-ups per run, about 8-12 extra Linux minutes per run (estimate). This must be weighed with #2993 because it adds concurrent jobs to a saturated org.
2. **Cache hygiene.** Measured lever: the 4.2 GB restore takes 1.9m at p50.
   - Rebuild the go-race cache from empty on `main` instead of restore-then-save, to stop accumulation.
   - Optionally split `~/go/pkg/mod` from `~/.cache/go-build`.
   - Warm the two nested modules as well.
   - Stop the PR-scoped `setup-go` and buildkit saves (`cache: false` plus restore-only, or `cache-to` only on `main`), so that the go-race cache is not evicted under the 12.67 GB > 10 GB pressure.

   Estimated gain is 0.5-1.5m on `test`, plus fewer cold-cache outliers. Runner minutes go down.
3. **Intra-package parallelism (`t.Parallel()`) in `internal/pa` and `internal/db`.** This has the largest long-term ceiling but the highest flake risk: there are zero parallel tests today, there are shared fixtures and sleeps, and the race detector's memory overhead grows with parallelism. The spike only profiles it and lists the candidates.
4. **Larger hosted runner for `test` only.** This is a cost decision for #2993. The spike measures `-p`/`GOMAXPROCS` scaling on a larger runner, if #2993 authorizes one, and does not buy anything itself.

### Phase R3: scheduling, capacity and selective CI (S2, S3)

- **Stale runs.** Evaluate `concurrency: group: build-${{ github.event.pull_request.number }}, cancel-in-progress: true` for `pull_request` only. Quantify superseded runs from R1. This must not apply to `merge_group`, `push` or release workflows, and `go-cache.yml` keeps its own group. The expected benefit is fewer runner minutes and less org queue pressure, with no per-PR latency change. The risk is a required context appearing as cancelled on an older SHA, which is harmless because the head SHA's run reports.
- **Selective component CI.** The measurements show it saves runner minutes, not wall clock: the Glovo jobs total about 2.5m and run in parallel. The one serial Glovo cost on the critical path is about 56s of nested-module vet/test inside `test`, and that time is recovered by shard E in option 1 without any path filtering. A dependency-aware matrix is evaluated only as a fixture-tested design, never as path filters on required jobs. The design must handle:
  - Change-routing fixtures: Telegram-only, Glovo-only, `provider/glovo`-only, a shared dependency (`internal/auth` etc.), release-only (`CHANGELOG.md` + `.release-please-manifest.json`), an unknown path, a rename across components, and merge-group.
  - Full-build triggers: any unknown or shared path forces the full build, and the aggregate gate always reports.

  A release-only shortcut is considered only if the release PR's tree is byte-identical to a `main` commit whose full build passed. That cannot be proven today because the release PR's merge ref differs, so it is DEFER.
- **Glovo placement.** Glovo MCP shares five root packages and is referenced by the PA egress-guard test, so extraction to mctlhq/mctl-glovo is not justified by CI time. Recommend keeping it, with documented component boundaries.
- **Intel Mac mini.** macOS is not on the critical path (p95 11.4m against `test` 27.2m), and per the owner snapshot it is not required. `macos-latest` is Apple Silicon (`setup-go-macOS-arm64` cache key), so an Intel i3 gives darwin/amd64 coverage, which is not a substitute. A persistent self-hosted runner would need ephemeral VMs, a dedicated runner group restricted to trusted `push`/`workflow_dispatch` on `main`, no fork PRs, no credentials or keychain, no LAN access, and no shared cache with PR jobs. Recommend DEFER, pending #2993 and the hardware facts.

### Preliminary recommendation (to be confirmed by R1-R2 evidence and independent review)

- Linux optimization: GO for building the research benchmark, covering option 1 together with option 2; dispatching it needs the separate authorization above. Implementation stays AMEND until the benchmark shows a p95 reduction of at least 30% with its uncertainty, an exact coverage-equivalent test inventory, and a shared-queue impact within the tolerance agreed with #2993.
- Stale-run scheduling: AMEND. Quantify first, then coordinate with #2993 and #2931.
- Optional Intel runner: DEFER.
- Selective component CI: DEFER. It saves minutes only; revisit if #2993 shows minutes, not latency, are the binding constraint.

## Alternatives

- **Path filters (`on.pull_request.paths`) on `build.yml`.** Dropped. A filtered-out required check never reports and blocks the PR, or a ruleset bypass produces a false green. Both violate the fail-closed requirement.
- **Lowering coverage, for example dropping `-race` on slow packages, running the Postgres tests without `-race`, or making nested Glovo modules optional.** Dropped. This is explicitly forbidden by the issue and by the comments in `build.yml`.
- **A matrix on the existing `test` job.** Dropped. It renames the context to `test (...)` and strands the required check, a trap already documented in `build.yml`. The aggregate-gate job keeps the name.
- **Extracting Glovo into mctlhq/mctl-glovo now.** Dropped. The CI gain is about 1m serial plus about 2.5m parallel, while the shared root packages and the PA egress-guard coupling would add cross-repo churn.

## Platform impact

- This proposal changes no workflow, ruleset, required context, runner or deployment, and cancels no live CI run. The benchmark runs on a scratch branch via `workflow_dispatch` only after its separate authorization. It costs at least 10 repetitions × variants × about 25-40 Linux minutes, more if variance forces a larger sample, and must stay within the runner-minute cap agreed with #2993 and outside saturation windows.
- Risks, with mitigations:
  - Benchmark noise from shared runner load: interleave control and candidate runs, report uncertainty per percentile, and grow the sample beyond 10 repetitions when p95 is unreliable.
  - A sharded gate that silently drops packages or tests: a union-of-packages assertion, an exact test inventory comparison, and negative fixtures.
  - A local speedup that degrades the shared queue: measure org-wide runner minutes, queue delay and saturation per candidate against the tolerance agreed with #2993.
  - Benchmark caches poisoning real caches: benchmark caches use a distinct key prefix (`bench-`) and are deleted after the run.
  - Secrets exposure: no `secrets.*` in the harness, `permissions: contents: read`.
- Backward compatibility: any later implementation must keep the `test`, `docker` and `product-updates` context names and every guard step listed under Current state.
