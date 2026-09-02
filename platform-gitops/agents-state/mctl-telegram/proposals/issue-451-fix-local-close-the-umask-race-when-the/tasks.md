# Tasks: issue-451-fix-local-close-the-umask-race-when-the

- [ ] 1. Add `cmd/local/umask_unix.go` with `//go:build !windows`, package
      `main`, exporting `func restrictUmask() { syscall.Umask(0o077) }` and a
      doc comment explaining why (closes the SQLite driver's file-creation
      race that `restrictDBPerms` only repairs after the fact) — DoD: file
      compiles under default (`linux`/`darwin`) `go build ./cmd/local/...`,
      `restrictUmask` is exported and callable from `main.go`.

- [ ] 2. Add `cmd/local/umask_windows.go` with `//go:build windows`, package
      `main`, exporting `func restrictUmask() {}` as a no-op, with a comment
      noting NTFS does not use POSIX mode bits and that ACL-based hardening
      on Windows is a deferred follow-up — DoD:
      `GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build ./cmd/local/...`
      succeeds (mirrors the release-please cross-compile step), matching the
      signature from task 1 exactly so only one of the two files is compiled
      per platform.

- [ ] 3. Call `restrictUmask()` as the first statement of `runLogin`
      (`cmd/local/main.go:146`) and of `runDaemonCmd`
      (`cmd/local/main.go:292`), before any config load or `openLocalStore`
      call (depends on 1, 2) — DoD: both call sites invoke `restrictUmask()`
      before `loadConfig`/`openLocalStore`; `runInit` and `runConnect` are
      left untouched since they already pass explicit `0o600` to
      `writeFileAtomic`.

- [ ] 4. Add a umask regression test — either extend
      `cmd/local/perms_test.go` or add `cmd/local/umask_unix_test.go`
      (`//go:build !windows`) — that calls `restrictUmask()`, writes a file
      into `t.TempDir()` with an explicit wide mode (e.g. `0o644`), and
      asserts `os.Stat(...).Mode().Perm() == 0o600` (depends on 1) — DoD:
      test fails without task 1's change (verify by temporarily commenting
      out the `restrictUmask()` body) and passes with it; test file is
      excluded from the Windows build via its build tag, so there is
      nothing to explicitly skip.

- [ ] 5. Note the Windows ACL gap in `internal/bridge/DESIGN.md`'s
      "Daemon-side (`cmd/local`, ...)" section, alongside the existing
      description of `restrictDBPerms`, so the deferred question the issue
      raises is discoverable from the design doc and not only from the
      issue thread (depends on 3) — DoD: one or two sentences added, no
      other content in that section altered.

- [ ] 6. Run `go fmt ./...`, `go vet ./...`, and `golangci-lint run` per
      `CONTRIBUTING.md`/`CLAUDE.md` conventions across the changed files
      (depends on 1, 2, 3, 4) — DoD: all three pass with no new findings.

## Tests
- [ ] T1. New unit test from task 4: file created after `restrictUmask()`
      in a temp dir is `0600` on Unix (build-tag excluded on Windows).
- [ ] T2. Existing `cmd/local/perms_test.go` (`TestRestrictDBPerms`)
      continues to pass unmodified — confirms the chmod repair path is
      untouched and still narrows pre-existing `0644` files.
- [ ] T3. Full package build for both `!windows` and `windows` GOOS
      (`go build ./cmd/local/...` and
      `GOOS=windows GOARCH=amd64 CGO_ENABLED=0 go build ./cmd/local/...`)
      to prove the build-tag split compiles cleanly on both, matching the
      five release targets in `.github/workflows/release-please.yml`.
- [ ] T4. Manual/CI smoke: run `mctl-telegram-local daemon` (or `login`)
      against a fresh config dir on Linux/macOS and confirm via `stat` that
      `state.db`, `state.db-wal`, and `state.db-shm` are `0600` immediately
      after creation, with no intermediate `0644` window observable (this is
      inherently a timing property that the unit test in T1 stands in for
      deterministically; this item is for a human reviewer to eyeball once).

## Rollback
Revert the PR (single conventional commit per this repo's squash-merge
convention). The change is additive and self-contained: two new small files
plus one call at the top of each of two functions plus one doc-comment
addition. Reverting drops the umask hardening and returns to today's
behavior — `restrictDBPerms` alone, with its known but low-severity
creation-time race — with no data migration, no schema change, and no
config format change to unwind. If only the Windows no-op file were somehow
broken post-merge (e.g. a build-tag typo caught after merge rather than in
CI), the fix is to correct the tag, not to revert the whole change; a full
revert is the only rollback path needed for anything else.
