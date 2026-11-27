# Tasks: issue-1476-spike-ci-mctl-ci-performance-runner-opti

These are research tasks only. None of them modifies `main`, `build.yml`, rulesets or runners, and none reruns or cancels a real CI run.

- [ ] 1. Commit the baseline collector, a read-only `gh api` script (runs, jobs with `filter=all`, steps, cache list, cache usage), to a research branch or issue attachment, then re-run it over the latest 100 `build` runs and over the `push` runs of `release-please.yml`, `go-cache.yml` and `codeql.yml`. DoD: output tables match or supersede design.md's baseline. Each run row pins `head_sha` and the `build.yml` blob SHA. Sample size, selection rule, missing timestamps, cancellations and `run_attempt>1` are listed.
- [ ] 2. Record governance facts with authorized read-only access (depends on 1): required status checks, org and repo rulesets, and merge-queue state. DoD: each fact is either observed with its source, or listed as "not observed" with its HTTP status, and the 403 seen on `branches/main/protection` is re-tried with an admin token.
- [ ] 3. Profile the race-test critical path (depends on 1). From one trusted run, run `go test -race -json` for `internal/pa`, `internal/db`, `cmd/server` and `internal/oauth` and extract the top 20 slowest tests, compile time versus test time, and peak RSS. DoD: a ranked table with reproducible commands. Package timeout (`-timeout 20m`) is distinguished from the job wall-clock limit.
- [ ] 4. Measure cache behaviour (depends on 1). Record the restore duration against cache size, hit or miss per run, the growth of `go-race-*` across `main` pushes, and which jobs save PR-scoped caches (`setup-go` in `cross-build` and `test-cross-platform`, `cache-to` in `docker*`). DoD: a table with the eviction evidence against the 10 GB quota.
- [ ] 5. Build the benchmark harness on a scratch branch (depends on 3, 4): a `workflow_dispatch` workflow with `permissions: contents: read`, no secrets and `bench-`-prefixed cache keys. It holds the control (the current `test` job verbatim) and candidates (a) the package-sharded `test` with an aggregate gate and (b) the cache-hygiene variant. DoD: the harness is reviewed by someone other than its author before its first dispatch.
- [ ] 6. Run the benchmark (depends on 5): at least 10 interleaved repetitions per variant, scheduled with #2993 outside saturation windows. DoD: p50/p95 per variant with variance, runner minutes per variant, and a check that the number of tests executed (`go test -json` pass count) is equal or greater than the control's.
- [ ] 7. Quantify stale work (depends on 1). Count runs superseded by a newer push to the same PR, and the minutes they consumed. DoD: a figure handed to #2993, with no cancellation of real runs.
- [ ] 8. Write the S3 component inventory and routing design (depends on 1): the component table from design.md, extended with ownership and release provenance (`release-please-config.json`, `.release-please-manifest.json`), and the full-build trigger list. DoD: the routing rules are written against the fixtures in T5 and are not implemented.
- [ ] 9. Collect the Mac mini facts from the owner (model, RAM, storage, supported macOS, availability, overlap with the #2993 runners) and write the isolation checklist. DoD: a GO/AMEND/DEFER entry. No host is registered.
- [ ] 10. Write the final research report with sources, limitations, ranked options (measured versus estimated), and an explicit GO/AMEND/DEFER for Linux optimization, stale runs, the Intel runner and selective CI, linked to #2993, #2931 and mctlhq/.github#398 (depends on 2-9). DoD: an independent reviewer completes the checklist below, and research approval is recorded separately from any implementation approval.

## Tests

- [ ] T1. Baseline reproducibility: re-running task 1's script on the same run IDs reproduces the same percentiles.
- [ ] T2. Aggregate gate fail-closed (harness only): fault injection where one shard fails, one shard is cancelled, one shard is skipped, and one shard times out. In each case the aggregate `test` job must conclude `failure` and never `success` or `skipped`.
- [ ] T3. Package-coverage guard: add a dummy package that no explicit shard lists. It must be tested by the catch-all shard. Removing a package from the union assertion must fail the gate.
- [ ] T4. Postgres no-skip preserved: in the sharded variant, unset `TEST_DATABASE_URL` in the Postgres shard. The guard must fail and the `expected=14` floor must still be enforced.
- [ ] T5. Change-routing fixtures (design-level, table test of the routing rules): Telegram-only, Glovo-only (`internal/glovo/**`), `provider/glovo`-only, shared dependency (`internal/auth/**`, `go.sum`), `Dockerfile*`, `.github/**`, release-only (`CHANGELOG.md` + `.release-please-manifest.json`), unknown path, a rename across components, and merge-group. Every case that is uncertain or shared must route to the full build.
- [ ] T6. Regression guard: the benchmark candidate's executed test count, race-enabled package set, and PA S1, Glovo nested-module and product-updates results are identical to the control's.
- [ ] T7. Repeatability: the coefficient of variation per variant is reported, and a claimed improvement must exceed it.

## Independent review checklist

- [ ] Every number is labelled measured or estimated and cites run and job IDs.
- [ ] No required context name changes, and no mandatory check (race, Postgres, PA S1, Glovo nested modules, CodeQL, govulncheck, product-updates) is weakened.
- [ ] No secrets, fork PR code or persistent self-hosted runner is used.
- [ ] Recommendations defer capacity and paid-plan choices to #2993.

## Rollback

Nothing here reaches `main`. To roll back:
1. Delete the scratch branch and its `workflow_dispatch` workflow.
2. Delete the `bench-*` cache entries with `gh cache delete`.
3. Discard the report.

Real CI, caches, rulesets and runners are untouched. Any later implementation proposal must carry its own rollback: revert the `build.yml` commit so the single-job `test` returns, keeping the context name.
