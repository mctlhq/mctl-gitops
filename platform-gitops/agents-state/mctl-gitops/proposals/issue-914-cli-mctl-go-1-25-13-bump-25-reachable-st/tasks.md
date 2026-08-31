# Tasks: issue-914-cli-mctl-go-1-25-13-bump-25-reachable-st

- [ ] 1. Bump the `go` directive in `cli/mctl/go.mod` from `go 1.25.0` to
      `go 1.25.13` — DoD: `cli/mctl/go.mod` line 3 reads `go 1.25.13`.
- [ ] 2. Run `go mod tidy` inside `cli/mctl` (depends on 1) — DoD:
      `cli/mctl/go.sum` is regenerated with no leftover stale hashes;
      running `go mod tidy` a second time produces no further diff;
      `git diff cli/mctl/go.mod` shows only the version-line and (if
      applicable) `// indirect` marker changes, no unrelated dependency
      version bumps.
- [ ] 3. Rebuild the CLI (depends on 2) — DoD: `cd cli/mctl && make build`
      exits 0 and produces an `mctl` binary in `cli/mctl/`.
- [ ] 4. Smoke-test the binary (depends on 3) — DoD: `./cli/mctl/mctl
      --help` exits 0 and prints the Cobra-generated usage text (matches
      the `Short`/`Long` strings in `cli/mctl/cmd/root.go`).
- [ ] 5. Run `govulncheck ./...` inside `cli/mctl` (depends on 2) — DoD:
      output reports 0 reachable vulnerabilities; save the output as
      `govulncheck-issue-914.txt` and attach/paste it in the PR
      description, matching the convention used in prior Go-CVE proposals
      in this repo (e.g. `mctl-api/proposals/pgx-sqli-patch`).
- [ ] 6. Check for a pinned CI Go version to bump (depends on nothing) —
      DoD: confirmed via repo-wide search that no `.github/workflows/*`
      file references `setup-go`, `go-version`, or `cli/mctl`; record this
      finding in the PR description so the "bump pinned CI Go version"
      acceptance criterion is visibly addressed rather than silently
      skipped. If a workflow is later found, update its `go-version` (or
      equivalent) input to `1.25.13` as part of this same task.
- [ ] 7. Update the documented prerequisite in `cli/mctl/README.md` from
      "Go 1.21+ (for building from source)" to "Go 1.25.13+ (for building
      from source)" (depends on 1) — DoD: README line updated; no other
      README content changed.
- [ ] 8. Clean up local build artifact before commit (depends on 3) — DoD:
      the `mctl` binary produced in task 3 is not committed (`cli/mctl/
      .gitignore` already covers this — confirm it still ignores the
      binary output, since the Makefile's `clean` target also removes it
      via `rm -f mctl`).

## Tests
- [ ] T1. `cd cli/mctl && go build ./...` exits 0 with no errors or
      warnings.
- [ ] T2. `cd cli/mctl && go vet ./...` exits 0.
- [ ] T3. `cd cli/mctl && govulncheck ./...` exits 0 and reports zero
      reachable vulnerabilities (primary acceptance gate from the issue).
- [ ] T4. `cd cli/mctl && make build && ./mctl --help` exits 0 and prints
      usage output (primary acceptance gate from the issue).
- [ ] T5. Manual spot-check: run at least one subcommand's `--help` (e.g.
      `./mctl deploy --help`) to confirm Cobra command wiring in
      `cmd/deploy.go` still registers correctly post-bump.

## Rollback
This is a two-line, single-module change (`go.mod` version directive +
regenerated `go.sum`) with no deployment, no Kubernetes manifest, and no
running service affected — `cli/mctl` is built and run ad hoc by whoever
invokes `make build`/`make install`, so there is no live rollout to revert.
If a problem surfaces after merge (e.g. an unexpected build failure on a
contributor's machine, or a dependency incompatibility missed in review):

1. `git revert` the merge commit on `mctl-gitops` main, restoring
   `cli/mctl/go.mod` to `go 1.25.0` and the prior `go.sum`.
2. Re-run `make build && ./mctl --help` to confirm the revert restores a
   working build.
3. Re-open (or leave open) issue #914 and re-triage — the underlying 25
   advisories remain unpatched until a corrected bump lands.

No data migration, no secret rotation, and no ArgoCD sync is involved in
either direction.
