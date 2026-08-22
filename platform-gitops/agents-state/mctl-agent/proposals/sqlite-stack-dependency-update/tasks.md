# Tasks: sqlite-stack-dependency-update

- [ ] 1. Bump `modernc.org/sqlite` from 1.34 to 1.57.0 in
      `go.mod`/`go.sum` (`go get modernc.org/sqlite@v1.57.0 && go mod
      tidy`) and confirm the resolved `modernc.org/libc` version is
      newer than v1.41.0 — DoD: `go.mod`/`go.sum` reference sqlite
      1.57.0; `go list -m modernc.org/libc` shows a version > v1.41.0.
- [ ] 2. Independently verify CVE-2026-50812 against sqlite.org/cves.html
      or an equivalent authoritative source, and check whether
      mctl-agent's codebase uses the SQLite Session Extension (depends
      on 1) — DoD: a documented outcome (confirmed real / confirmed
      fabricated / inconclusive, plus "extension used: yes/no") recorded
      in this task's completion note; no claim about this CVE is made
      elsewhere in the codebase or release notes without this
      documented basis.
- [ ] 3. Add/extend table-driven tests for the tickets DB data-access
      layer covering insert/read/update/delete paths against the
      upgraded driver (depends on 1) — DoD: passing table-driven test
      suite exercising the existing tickets-DB query surface with no
      behavior changes versus the 1.34 baseline.
- [ ] 4. Add/extend table-driven tests for the skill-metrics store
      covering counter increment/read paths against the upgraded driver
      (depends on 1) — DoD: passing table-driven test suite exercising
      the existing skill-metrics query surface with no behavior changes
      versus the 1.34 baseline.
- [ ] 5. Run a manual/scripted regression check: open an existing (pre-
      upgrade) tickets DB file with the upgraded driver and confirm it
      reads correctly, no migration required (depends on 3) — DoD:
      existing on-disk DB file opens and returns expected data under
      the new driver version.
- [ ] 6. Run the full test suite and build the container image (depends
      on 3, 4, 5) — DoD: `go build ./...` and `go test ./...` pass with
      no CGO introduced (`CGO_ENABLED=0` build still succeeds).
- [ ] 7. Deploy via the normal ArgoCD sync path for
      `admins-mctl-agent` (depends on 6) — DoD: ArgoCD Application
      shows health=Healthy, syncStatus=Synced on the new revision;
      `mctl_list_incidents` for admins/mctl-agent still returns 0 in
      the 24h following rollout.

## Tests
- [ ] T1. Table-driven test: tickets DB insert/read/update/delete
      behavior is unchanged under modernc.org/sqlite 1.57.0.
- [ ] T2. Table-driven test: skill-metrics store counter
      increment/read behavior is unchanged under modernc.org/sqlite
      1.57.0.
- [ ] T3. Regression test: an existing on-disk tickets DB file (created
      under 1.34) opens and reads correctly under 1.57.0 with no
      migration step.
- [ ] T4. `go list -m modernc.org/libc` resolves to a version newer
      than v1.41.0 (CVE-2025-26519 closed).
- [ ] T5. `CGO_ENABLED=0 go build ./...` succeeds, confirming the
      pure-Go/no-CGO property is preserved.
- [ ] T6. Full existing test suite (`go test ./...`) passes unchanged.

## Rollback
Revert the `go.mod`/`go.sum` `modernc.org/sqlite` version pin from
1.57.0 back to 1.34 in a single revert commit and redeploy the
previous known-good image tag through ArgoCD. Because the on-disk file
format is unchanged across this version range (verified in task 5/T3),
no data-level rollback or backup restore is required — the same DB
file remains readable by the reverted driver version.
