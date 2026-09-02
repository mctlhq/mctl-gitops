# Design: issue-451-fix-local-close-the-umask-race-when-the

## Current state
`cmd/local` (~1600 lines with tests, per `internal/bridge/DESIGN.md:92`) is
the Local Bridge daemon CLI. Its database lifecycle is centralized in
`openLocalStore` (`cmd/local/main.go:356-403`):

1. `dbFilePath()` resolves the standard path under the user's config dir.
2. `db.Open(ctx, dsn, 0, 0)` opens/creates `state.db` via the SQLite driver
   (`_pragma=journal_mode(WAL)` in the DSN, so `-wal`/`-shm` sidecars are
   created and recreated on every open).
3. `db.Migrate(ctx, rawDB)` runs schema migrations.
4. `restrictDBPerms(dbPath)` (`main.go:464-471`) loops over
   `{dbPath, dbPath+"-wal", dbPath+"-shm"}` and `os.Chmod`s each to `0o600`,
   tolerating `os.IsNotExist` for sidecars that do not exist yet.
5. The AES-GCM `crypto.New` cipher and `db.NewStore` wrap the raw handle.

`openLocalStore` is called from exactly two places: `runLogin`
(`main.go:166`) and `runDaemonCmd` (`main.go:332`). Both are top-level
subcommand entry points invoked once per process (`main.go:59-87` dispatches
`os.Args[1]` to `runLogin`/`runDaemonCmd`/etc.), so there is no risk of
`openLocalStore` running concurrently with another umask-sensitive operation
in the same process.

Step 2 creates `state.db` (and, on every subsequent open, its `-wal`/`-shm`
siblings) using whatever mode SQLite's driver requests, narrowed by the
process's inherited umask — `0022` on a default account, yielding `0644`
files. Step 4 repairs that after the fact. Between step 2 and step 4 (and,
for the sidecars, on every single open of an existing database, since WAL
mode recreates them each time) the files are readable by every local
account for the duration of driver initialization plus migration.

Other file-writing paths in `cmd/local` already sidestep this class of bug
by requesting the mode explicitly rather than relying on the umask:
`config.go:139` and `config.go:179` both call `writeFileAtomic(..., 0o600)`
for `config.json` and `bridge_token.json`. The SQLite driver gives no such
explicit-mode hook through the `db.Open` wrapper used here, which is why
`restrictDBPerms` exists as a post-hoc chmod instead.

There is currently no per-platform (`GOOS`-tagged) source file anywhere in
`cmd/local` — `grep -rn "go:build" .` outside generated/vendor code returns
nothing in this package. The release pipeline
(`.github/workflows/release-please.yml:91`) cross-compiles
`mctl-telegram-local` for `darwin/arm64 darwin/amd64 linux/amd64 linux/arm64
windows/amd64` with `CGO_ENABLED=0`, confirming the Windows build is a real,
shipped artifact and not aspirational.

## Proposed solution
Add a process-wide umask restriction that runs before the database is ever
touched, implemented as a GOOS-split pair of tiny files, matching the shape
the issue suggests and the precedent of keeping platform-specific syscalls
behind build tags rather than runtime `runtime.GOOS` branches (the codebase
has no existing precedent either way here, but a build tag is the standard
Go idiom for a call that does not exist in another OS's `syscall` package at
all, as opposed to one that exists but behaves differently):

1. **`cmd/local/umask_unix.go`** — `//go:build !windows`. Exports
   `restrictUmask()` that calls `syscall.Umask(0o077)` and discards the
   previous mask (there is nothing meaningful to restore it to; the process
   is single-purpose and short-lived). `0o077` clears all group and world
   bits, matching the `0600` that `restrictDBPerms` already enforces and the
   `0o600` explicit mode used by `writeFileAtomic` elsewhere in the package,
   so every file this process creates from here on — the database, its WAL
   /SHM sidecars, and incidentally anything else — is born owner-only.

2. **`cmd/local/umask_windows.go`** — `//go:build windows`. Exports the same
   `restrictUmask()` signature as a no-op, with a comment explaining NTFS
   does not use POSIX mode bits and that ACL-based hardening on Windows is
   an explicitly deferred follow-up (cross-referenced from
   `internal/bridge/DESIGN.md`'s existing "Daemon-side" section, which is
   the natural place to note the gap once this lands).

3. **Call sites**: add `restrictUmask()` as the first statement of
   `runLogin` (`main.go:146`, right after the `flag.Parse`/`--phone`
   validation and before `loadConfig`/`openLocalStore`) and of
   `runDaemonCmd` (`main.go:292`, before `loadConfig`). Calling it at the
   very top of each function — not just immediately before
   `openLocalStore` — is simpler to reason about (one umask policy for the
   whole subcommand invocation) and costs nothing, since neither function
   creates any file before this call today; the issue's "before
   `openLocalStore`" requirement is satisfied either way. `runInit` and
   `runConnect` are not touched: both already pass an explicit `0o600` to
   `writeFileAtomic` and do not depend on the umask (see Open Questions in
   requirements.md).

4. **`restrictDBPerms` is unchanged.** It keeps running in `openLocalStore`
   exactly as today. With the umask now `0o077` for the whole process, the
   files it chmods will already be `0600` by the time it runs in the normal
   case, making the chmod a no-op — but it remains the only mechanism that
   repairs databases created by an older daemon binary (pre-fix, still
   `0644` on disk) or by any code path that does not route through these two
   call sites.

5. **Test**: extend `cmd/local/perms_test.go` (or add a sibling
   `umask_unix_test.go` with the same `!windows` build tag) with a test that
   calls `restrictUmask()`, creates a file in `t.TempDir()` via
   `os.WriteFile(path, data, 0o644)` (a deliberately wide requested mode, to
   prove the umask — not the explicit argument — is what narrows it), and
   asserts `os.Stat(path).Mode().Perm() == 0o600`. Skipped on Windows via
   `if runtime.GOOS == "windows" { t.Skip(...) }` or, more idiomatically
   given the file is already `!windows`-tagged, simply excluded from the
   Windows build entirely so there is nothing to skip.

## Alternatives
- **Runtime `runtime.GOOS == "windows"` branch instead of build tags.**
  Rejected: `syscall.Umask` is not merely behaviorally different on
  Windows, it does not exist in the `windows` build of the `syscall`
  package at all, so a runtime branch would still fail to compile for the
  `windows/amd64` release target. Build tags are the only option that
  compiles on both platforms, and the issue explicitly asks for this shape.

- **Drop `restrictDBPerms` and rely on the umask alone.** Rejected per the
  issue's own reasoning and confirmed by reading `restrictDBPerms`'s
  doc comment (`main.go:450-463`): the umask only affects files created
  *after* the process starts. Every daemon already installed before this
  fix ships has a `state.db` sitting at `0644` on disk right now, and the
  umask does nothing to narrow a file that already exists. The chmod is the
  only mechanism that repairs those. Both must stay.

- **Move the umask call inside `openLocalStore` itself, right before
  `db.Open`.** Considered instead of putting it at the top of `runLogin`/
  `runDaemonCmd`. Rejected in favor of the call-site placement the issue
  requests: `openLocalStore` is a shared helper and setting the process
  umask is a decision that belongs to the subcommand entry point, not
  buried inside a "open the database" helper — a future reader of
  `runDaemonCmd` should be able to see the security posture of the whole
  subcommand invocation at the top of the function, and a future
  `openLocalStore` caller (if one is ever added) should not silently
  inherit a process-wide umask change as a side effect of just wanting a
  database handle.

- **Use `os.OpenFile` with an explicit mode instead of a process umask.**
  Not viable: `state.db`/`-wal`/`-shm` are created internally by the SQLite
  driver via `database/sql`'s `sql.Open`/driver machinery reached through
  `db.Open`, which gives no hook to pass a file mode. The umask is the only
  lever available without vendoring or patching the driver.

## Platform impact
- **Migrations**: none. No schema change.
- **Backward compatibility**: fully backward compatible. Existing databases
  at `0644` are corrected by the unchanged `restrictDBPerms` on next open,
  exactly as they are today; new databases are additionally born `0600`.
  No config, DSN, or CLI flag changes.
- **Resource impact**: negligible — one extra syscall per `login`/`daemon`
  invocation, both of which are already slow, human-interactive or
  long-running paths.
- **Windows**: no behavior change at all — `restrictUmask()` is a true
  no-op on that GOOS, and `restrictDBPerms` (which does the real work on
  Windows today, however imperfectly given NTFS ACL semantics) is
  untouched. The build must still succeed for `windows/amd64`; this is the
  primary risk this design is structured to avoid, hence the build-tag
  split rather than any conditional syscall usage.
- **Risks + mitigations**:
  - *Risk*: forgetting the `windows` build tag on the unix file, breaking
    the release cross-compile. *Mitigation*: `go vet ./...` and the
    project's standard `go build` are run per `CONTRIBUTING.md`/CI before
    merge; a missing/wrong build tag on `umask_unix.go` would fail the
    `GOOS=windows` build step in `release-please.yml` immediately.
  - *Risk*: `syscall.Umask` affects the whole process, including any
    goroutine — if `runDaemonCmd`'s long-running websocket loop
    (`runDaemon`) ever writes files (e.g. logs, future cache files) they
    will now also be `0600`. *Mitigation*: this is the intended, desired
    effect (owner-only by default for the whole process lifetime); no code
    today needs wider permissions, and none of the reviewed file-writing
    call sites (`config.go`) request one.
  - *Risk*: someone later adds a new `openLocalStore` caller and forgets
    `restrictUmask()`. *Mitigation*: `restrictDBPerms` remains as a safety
    net inside `openLocalStore` regardless, so the failure mode degrades to
    "same race as today," not silent unprotected `0644` forever.
