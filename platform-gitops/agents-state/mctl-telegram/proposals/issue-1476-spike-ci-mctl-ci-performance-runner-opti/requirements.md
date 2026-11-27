# CI performance spike: required-check critical path, scheduling and runner options for mctl-telegram

## Context

Issue mctlhq/mctl-telegram#1476 asks for a research-only spike. The goal is to shorten the time from PR HEAD until the required checks are green and the PR can be released, without weakening correctness, security or governance. The spike also asks for findings that the rest of the organization can reuse. Org-wide runner capacity is owned by mctlhq/mctl-gitops#2993, and merge-queue churn by mctlhq/mctl-gitops#2931; this spike complements both and does not compete with them. The 2026-11-26 refresh adds S3: component boundaries, plus selective (affected-component) CI for the Telegram MCP, PA agent worker, Glovo MCP and fake-provider worker images, all of which are built from this repository.

A read-only baseline taken for this proposal on 2026-11-27 measured the last 100 `build` runs (all `pull_request`, created 2026-11-24T11:54Z to 2026-11-27T11:12Z). In 97 of the 100 runs the `test` job in `.github/workflows/build.yml` was the last job to finish. Its execution time was p50 23.9m and p95 27.2m. Within it, the single step `go test -race -timeout 20m ./...` was p50 18.6m and p95 22.8m, and the go-race cache restore took p50 1.9m. On #1475 the slowest package was `internal/pa` at 591s (the other packages are listed in design.md); none of the five slowest packages call `t.Parallel()`. The Glovo jobs took 1.0-1.5m (p50), ran in parallel with `test`, and were never the last job to finish. The proposal therefore puts the Linux race-test critical path first, and treats the other areas (selective CI, scheduling, an extra macOS/Intel runner) as levers on runner minutes and capacity rather than on per-PR latency.

## User stories

- AS the repository owner I WANT a source-pinned, reproducible latency baseline that names the bottleneck SO THAT optimization decisions rest on measurements, not anecdotes.
- AS a PR author I WANT the required `test` check to finish sooner SO THAT the time from push to merge-eligible goes down.
- AS the governance reviewer I WANT every option to keep race, PostgreSQL no-skip, PA S1, Glovo nested-module, CodeQL, govulncheck and product-updates coverage SO THAT speed is never bought with silent coverage loss.
- AS the mctl-gitops#2993 capacity owner I WANT this repo's runner-minute and queue figures, plus its recommendations on stale runs and self-hosted runners, SO THAT org-wide capacity decisions use the same evidence.
- AS a platform engineer in another mctlhq repo I WANT the measurement scripts and the fail-closed aggregate-gate pattern documented SO THAT I can reuse them.

## Acceptance criteria (EARS)

- WHEN the baseline is produced THE SYSTEM SHALL record the sample size, selection rule, time window, workflow file revision, run and job IDs, and the counts of cancelled, failed, retried (`run_attempt > 1`) and in-progress runs.
- WHEN latency is reported THE SYSTEM SHALL report queue wait (job `created_at` to `started_at`), execution, the critical path of the required checks, merge-group wait and release/deploy latency as separate p50/p90/p95 distributions, broken down by event (`pull_request`, `push`, `merge_group`).
- IF a data source (branch protection, org rulesets, merge-queue settings, billing) cannot be read with the available credentials THEN THE SYSTEM SHALL list it as "not observed" with the HTTP status, and SHALL NOT infer its value.
- WHEN the blocking required job for #1475 is identified THE SYSTEM SHALL cite job 138703397953 and its step timestamps.
- WHEN options are ranked THE SYSTEM SHALL give, for each option, the expected wall-clock change, the runner-minute change, cost, complexity, isolation and risk, and SHALL label every figure as either measured or estimated.
- WHILE any candidate is being evaluated THE SYSTEM SHALL keep the required check context names (`test`, `docker`, `product-updates`, plus any others confirmed from settings) stable and reporting on every PR.
- WHILE any candidate is being evaluated THE SYSTEM SHALL keep `-race`, the Postgres no-skip guard with its `expected=14` floor, the PA S1 closing gate, both nested Glovo modules under `-race`, govulncheck, CodeQL and the product-updates gate.
- IF a sharded or selective design cannot determine that a required component was tested THEN THE SYSTEM SHALL fail the aggregate required check (fail closed). It SHALL NOT report the check as skipped, pending or green.
- IF a changed path is unknown or is a shared dependency (`go.mod`, `go.sum`, `internal/auth`, `internal/audit`, `internal/metrics`, `internal/edgectx`, `internal/jsonstrict`, any `Dockerfile*`, `.github/**`, toolchain pins) THEN THE SYSTEM SHALL run the full build.
- WHEN a benchmark is run THE SYSTEM SHALL run it only in a trusted sandbox (a fork-free branch or `workflow_dispatch` on a scratch branch), with synthetic inputs and no live secrets, repeated at least 10 times per variant, and SHALL report the variance.
- WHEN a latency improvement is claimed THE SYSTEM SHALL compare it with the comparable baseline under controlled validation, and SHALL NOT claim it from estimates alone.
- WHEN the spike concludes THE SYSTEM SHALL issue an explicit GO / AMEND / DEFER for (a) Linux test optimization, (b) stale-run scheduling, (c) the optional Intel Mac mini runner and (d) selective component CI, each linked to its #2993 counterpart.
- THE SYSTEM SHALL target a reduction of at least 30% in p95 latency of the `test` required check versus the comparable baseline (p95 27.2m execution in this sample), or else present an evidence-based alternative.

## Out of scope

- Any change to workflows, branch protection, rulesets or the merge queue, any runner registration, and any CI rerun or cancellation, merge or deployment. All of these need a separate implementation approval.
- Connecting the Intel Mac mini, or any host, as a runner.
- Extracting Glovo code into mctlhq/mctl-glovo, or creating any repository.
- Org-wide runner capacity and paid-plan decisions, which are owned by mctlhq/mctl-gitops#2993.
- Reviewer-bot latency (agy-review, claude-review), which is covered by mctlhq/.github#398.

## Open questions

- Required check contexts were not observed. `GET branches/main/protection/required_status_checks` returned 403 ("Resource not accessible by integration"), and `GET repos/.../rulesets` returned `[]`; org-level rulesets were not readable. The owner snapshot lists `test`, `docker` and `product-updates`; it is unknown whether `Analyze (go)` (CodeQL) or any other check is also required.
- Is a merge queue enabled for `main`? `build.yml` has no `merge_group` trigger. If a merge queue requires `test`, it could never report there. The 100-run sample contains only `pull_request` events.
- Why was the macOS job cancelled in run 45466703355? It was created and then cancelled 15 minutes later with no runner assigned and no steps, and the run conclusion is `failure` even though every other job succeeded. The sample has 6 macOS cancellations and 4 macOS failures out of 100.
- The exact model and resources of the owner's Intel Core i3 Mac mini, and whether it is already one of the two macOS x64 agy-reviewer runners from #2993, are unknown.
- Cost figures need the org's billing plan. The 4603 job-minutes measured are unrounded execution time and are not billed minutes.
