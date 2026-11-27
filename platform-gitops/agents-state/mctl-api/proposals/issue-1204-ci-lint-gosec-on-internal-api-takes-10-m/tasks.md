# Tasks: issue-1204-ci-lint-gosec-on-internal-api-takes-10-m

- [ ] 1. Add `timeout-minutes: 15` to the `lint` job in `.github/workflows/validate.yml`. — DoD: the job definition contains the timeout; nothing else in the `test` job changes.
- [ ] 2. In `validate.yml`'s `lint` job, change the golangci-lint action args from `--timeout 10m` to `--timeout 10m --disable gosec`; keep the job name `lint` and `version: v2.11.4`. (depends on 1) — DoD: locally, `golangci-lint run --timeout 10m --disable gosec ./...` with v2.11.4 runs the other eight linters from `.golangci.yml` and not gosec (check with `-v` output listing active linters).
- [ ] 3. Add a `gosec` job to `.github/workflows/security.yml` with `timeout-minutes: 30`, checkout + `actions/setup-go@v6` (`go-version-file: go.mod`, `cache: true`) and golangci-lint v2.11.4 run as `--enable-only gosec --timeout 25m`, wrapped so elapsed time and max RSS are printed (for example `/usr/bin/time -v`). — DoD: on the implementation PR the `gosec` job runs, prints the timing lines and passes with 0 issues; it reads the existing `.golangci.yml` (G104/G704/G706 still excluded).
- [ ] 4. Add `scripts/gosec-rule-timing.sh` that, for each gosec rule known to golangci-lint v2.11.4, writes a temporary config with `gosec.includes: [<rule>]` and times `golangci-lint run --enable-only gosec` on `./internal/api/`, printing `rule seconds issues`. Run it once and paste the table in the PR description. — DoD: script is executable, uses only a temp dir, does not modify `.golangci.yml`; the PR description contains the table.
- [ ] 5. In the PR description, state the bounds (`lint` 15 min, `gosec` 30 min / 25m golangci timeout), ask the owner to add `gosec` as a required status check on `main`, and ask for a decision on any rule exclusion based on task 4. No rule is excluded in this PR unless the owner approves in review. (depends on 3, 4) — DoD: PR description contains all three items.
- [ ] 6. If and only if the owner approves an exclusion: add the rule to `.golangci.yml` `linters.settings.gosec.excludes` with a comment giving the reason and the measured seconds from task 4. (depends on 5) — DoD: comment present in G704/G706 style; gosec job time drops accordingly.

## Tests
- [ ] T1. On the implementation PR, `lint` passes and its golangci-lint step finishes in under 5 minutes.
- [ ] T2. On the implementation PR, `gosec` passes with 0 issues and its logged elapsed time is under 25 minutes.
- [ ] T3. Hang simulation on a throwaway branch (not merged): temporarily set the `lint` job's `timeout-minutes: 1` and confirm GitHub fails the job with a timeout and no manual cancellation; revert.
- [ ] T4. Negative check on a throwaway branch: add a file with a known gosec finding (for example `exec.Command` on a variable, G204) and confirm the `gosec` job fails and `lint` does not report it; revert.
- [ ] T5. After merge, confirm the `gosec` job runs on the push to `main` via `security.yml`.

## Rollback
Revert the PR. That restores the single `lint` job running all linters with `--timeout 10m`. If only the split causes trouble, keep task 1's `timeout-minutes: 15` (which alone is safe) and revert tasks 2 and 3. If a rule exclusion from task 6 is regretted, delete its line from `gosec.excludes`. Remove `gosec` from required checks if the job is reverted, or merges will wait on a check that no longer runs.
