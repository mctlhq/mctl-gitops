# Bound the lint check and isolate gosec so a slow or hung linter fails fast

## Context
The required `lint` job (`.github/workflows/validate.yml`, job `lint`) runs
golangci-lint v2.11.4 with every linter in `.golangci.yml`, including `gosec`,
under `--timeout 10m`. Issue #1204 reports that `gosec` alone takes about 600 s
on `./internal/api/` (122 non-test files, about 44.8k lines), which is close to
the 10-minute timeout. On 2026-11-27 the `lint` job hung twice on #1201 for 25+
minutes and had to be cancelled by hand: golangci-lint's own timeout did not end
the step, and the job has no `timeout-minutes`, so GitHub's 360-minute default
applies. All other linters finish in 2 to 4 s on the same package.

This proposal makes every lint job end within a hard, stated bound without
manual cancellation, moves `gosec` into its own job with its own budget so the
fast linters are no longer held hostage by it, and adds a measurement step that
gives the owner the per-rule data needed to decide whether any `gosec` rule
should be excluded. No `gosec` rule is removed by this proposal without an
explicit owner decision.

## User stories
- AS a contributor I WANT a hung linter to fail the check on its own SO THAT I can re-run it instead of waiting for someone to cancel it.
- AS a reviewer I WANT the fast linters to report within a few minutes SO THAT ordinary lint feedback is not gated on gosec's runtime.
- AS the repository owner I WANT per-rule gosec timing on `internal/api` SO THAT any rule exclusion is a deliberate, documented decision.
- AS a security maintainer I WANT gosec to keep running on pull requests and on main SO THAT splitting it out does not weaken coverage.

## Acceptance criteria (EARS)
- WHEN a pull request targets `main` THE SYSTEM SHALL run a `lint` job that executes every linter in `.golangci.yml` except `gosec`.
- WHEN a pull request targets `main`, or a commit is pushed to `main` THE SYSTEM SHALL run a separate `gosec` job that executes only the `gosec` linter with the same `.golangci.yml` settings (including the `G104`, `G704`, `G706` excludes).
- WHILE the `lint` job runs THE SYSTEM SHALL enforce a job-level `timeout-minutes: 15` and a golangci-lint `--timeout 10m`.
- WHILE the `gosec` job runs THE SYSTEM SHALL enforce a job-level `timeout-minutes: 30` and a golangci-lint `--timeout 25m`, so a nominal run (about 10 minutes measured) has more than 2x headroom under both bounds.
- IF a lint or gosec step exceeds its golangci-lint timeout and does not exit THEN THE SYSTEM SHALL fail the job at its `timeout-minutes` bound without manual cancellation.
- WHEN the `gosec` job finishes THE SYSTEM SHALL have printed the elapsed wall-clock time and peak memory of the gosec step to the job log, so the bound can be checked against real runs.
- IF any `gosec` rule is excluded as a result of this work THEN THE SYSTEM SHALL list that rule in `.golangci.yml` with a comment stating its reason and the measured cost, in the same style as the existing `G704` and `G706` comments.
- WHILE the `gosec` job is not yet a required status check THE SYSTEM SHALL keep the old behaviour of gosec being blocking by not merging the split until the owner has added `gosec` to the required checks of `main`.

## Out of scope
- Excluding or replacing any `gosec` rule. The proposal produces the timing data; the exclusion is a separate owner decision (see Open questions).
- Splitting the `internal/api` package into smaller packages.
- Changing the `test` job, `security.yml`'s existing `govulncheck` and `trivy` jobs, or any runtime code.
- Upgrading golangci-lint or gosec.
- Root-causing why golangci-lint's own timeout did not end the step (the job-level timeout makes the outcome bounded regardless).

## Open questions
- Branch protection: the required check is named `lint`. After the split, `gosec` is a new check that only the owner can mark required in the repository settings. Until then gosec findings would not block merges. The proposal assumes the owner adds it before or together with merging.
- Rule exclusion: the issue names the taint analyzers (G7xx) as first suspects. Whether to exclude the dominating rule(s), and which, needs an owner decision after the measurement in tasks.md task 4.
- `.golangci.yml` sets `run.go: "1.24"` while `go.mod` declares `go 1.26.11`. It is unknown whether this mismatch affects gosec's runtime; the proposal does not change it but records it for the owner.
- Runner memory: a full nine-linter run peaked at 5.1 GB locally. Whether the CI hangs were memory pressure on `ubuntu-latest` is not established. The proposal records peak memory in the gosec job so this can be confirmed or ruled out.
- The bounds (15 min for `lint`, 30 min for `gosec`) are chosen from the issue's numbers (lint jobs normally 4 to 6 min, gosec about 10 min locally); the owner may prefer different values.
