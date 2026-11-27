# Design: issue-1204-ci-lint-gosec-on-internal-api-takes-10-m

## Current state
- `.github/workflows/validate.yml` triggers only on `pull_request` to `main`.
  Its `lint` job runs `actions/checkout@v7`, `actions/setup-go@v6`
  (`go-version-file: go.mod`, `cache: true`) and
  `golangci/golangci-lint-action@v8` with `version: v2.11.4` and
  `args: --timeout 10m`. The job has no `timeout-minutes`, so GitHub's default
  of 360 minutes applies. This is why the two hung attempts on #1201 ran until
  cancelled by hand.
- `.golangci.yml` (version 2) sets `run.timeout: 10m` and `run.go: "1.24"`,
  enables `errcheck, govet, staticcheck, unused, ineffassign, gocritic, gosec,
  bodyclose, nilerr`, and configures `gosec.excludes: [G104, G704, G706]` with
  comments explaining G704 (SSRF) and G706 (log injection).
- `go.mod` declares `go 1.26.11`, which differs from `run.go: "1.24"`.
- `.github/workflows/security.yml` triggers on `pull_request` to `main`,
  `push` to `main`, `workflow_dispatch` and a weekly schedule, and already uses
  job-level timeouts (`govulncheck`: `timeout-minutes: 10`, `trivy`:
  `timeout-minutes: 15`). It is the repository's existing home for security
  scanners.
- `Makefile` has no lint target; `CLAUDE.md` asks contributors to run
  `golangci-lint` before committing.
- `internal/api/` holds 122 non-test Go files (about 44.8k lines; the largest
  are `router.go` 1717, `handlers_dev_loop.go` 1389, `handlers_read.go` 1092,
  `handlers_identity_link.go` 1090) plus about 68.6k lines of tests. No file in
  `internal/api` carries a `#nosec` annotation.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/*/mctl-api`: no such directory was found in the
  available gitops checkout. This change touches only CI configuration of the
  repository and nothing that is deployed, so no deployed state is relied on.
- mctl MCP tools: not called; the change has no tenant, service or runtime
  surface to check.

## Proposed solution
Three changes, all in CI configuration; no Go code changes.

1. Hard job timeouts. Add `timeout-minutes: 15` to `validate.yml`'s `lint` job.
   golangci-lint's `--timeout` cancels its context, but analyzers that do not
   check the context can keep running (the observed hang); the job-level
   timeout is enforced by the runner and kills the step regardless.

2. Split gosec out of the `lint` job.
   - `validate.yml` `lint`: keep the job name `lint` (the existing required
     check) and change args to `--timeout 10m --disable gosec`. The remaining
     eight linters take 2 to 4 s each on `internal/api` per the issue, so the
     job should finish well inside 15 minutes.
   - New job `gosec` in `.github/workflows/security.yml`, next to `govulncheck`
     and `trivy`, so it inherits that workflow's triggers (PR, push to main,
     weekly schedule, manual dispatch). That satisfies "on main and on pull
     requests" without adding a push trigger to `validate.yml` (which would also
     run the Postgres/Chrome test job on every main push). The job uses the same
     checkout/setup-go steps and `golangci/golangci-lint-action@v8` with
     `version: v2.11.4` and `args: --timeout 25m --enable-only gosec`, and sets
     `timeout-minutes: 30`. Because it reads the same `.golangci.yml`, the
     `gosec.excludes` list and its comments stay the single source of truth.
   - Instrumentation: the gosec job also gets a short follow-up step (or wraps
     the action's run with `/usr/bin/time -v` via `install-mode` plus a plain
     `run:` step, whichever the implementer finds works with action v8) that
     prints elapsed time and maximum resident set size. If wrapping is awkward,
     a plain `run:` step that installs the pinned golangci-lint binary and runs
     `/usr/bin/time -v golangci-lint run --enable-only gosec --timeout 25m ./...`
     is acceptable; the action's caching is then replaced by setup-go's module
     cache, which is already on.

3. Measurement for the owner decision (no config change by itself). Add
   `scripts/gosec-rule-timing.sh` that runs the pinned golangci-lint with
   `--enable-only gosec` on `./internal/api/` once per gosec rule group (using a
   temporary config that sets `gosec.includes` to one rule at a time, taken from
   golangci-lint's own gosec rule list for v2.11.4) and prints a table of rule,
   seconds and issues. The implementer runs it once, records the table in the
   PR description, and the owner decides whether to exclude anything. If a rule
   is excluded, it goes into `.golangci.yml` `gosec.excludes` with a comment
   giving the reason and the measured cost, matching the G704/G706 style.

Bounds stated by this proposal: `lint` at most 15 minutes (nominal under 5);
`gosec` at most 30 minutes with a 25-minute golangci-lint timeout (nominal about
10). Both bounds are visible in the workflow files.

## Alternatives
- Only add `timeout-minutes` to the existing `lint` job. Smallest change and it
  meets "a hung linter fails the job", but gosec still sits close to the 10m
  golangci-lint timeout, so `lint` would keep failing intermittently and every
  failure would hide eight fast linters' results. Kept as step 1, rejected as the
  whole fix.
- Exclude the slow taint rules now. Would fix runtime directly, but the issue
  says it weakens a security check and needs an owner decision, and which rule
  dominates is not yet measured. Deferred to task 4's data.
- Split `internal/api` into smaller packages. gosec's SSA/taint cost is driven
  by the call graph, so splitting may not help, and it is a large refactor of
  the busiest package. Rejected as disproportionate for a CI problem.
- Put the `gosec` job in `validate.yml` instead of `security.yml`. Works for PRs
  but does not run on main without adding a push trigger that also re-runs the
  heavy `test` job. Rejected.

## Platform impact
- No migrations, no runtime or API change, no Helm change.
- CI cost: one extra runner per PR and per main push for the `gosec` job (about
  10 minutes). The `lint` job gets faster by roughly the same amount, and the two
  run in parallel, so wall-clock time to a green PR drops.
- Risk: once gosec leaves `lint`, gosec findings no longer block merges unless
  `gosec` is made a required check. Mitigation: the PR description tells the
  owner to add the `gosec` check to `main`'s branch protection; the PR is not
  merged before that (requirements Open questions).
- Risk: the `gosec` job's longer timeout still allows up to 30 minutes on a
  hang. Mitigation: it fails on its own; the bound can be tightened once the
  instrumentation shows real CI numbers.
- Risk: `--disable gosec` / `--enable-only gosec` flag semantics in
  golangci-lint v2.11.4. Mitigation: task 2 and 3 verify locally with
  `golangci-lint linters` / a dry run that the intended linter sets run.
