# Close the umask race when the Local Bridge daemon creates its database

## Context
`cmd/local/main.go`'s `openLocalStore` opens (or creates) `state.db` via
`db.Open` / the SQLite driver, then calls `restrictDBPerms(dbPath)`
(`main.go:374`, defined at `main.go:464`) to `os.Chmod` `state.db`,
`state.db-wal`, and `state.db-shm` to `0600`. The chmod runs *after* the
driver has already created the file under the process umask, which is
`0644` on a default Linux/macOS account. Between file creation and the
chmod call, the database (and its WAL/SHM sidecars, which the driver
recreates on every open) briefly exists group- and world-readable. The row
contents are AES-GCM-encrypted with an Argon2id-derived key (`internal/crypto`),
so a local attacker who reads the file during that window gets ciphertext to
attack offline, not plaintext session data outright — but the window should
not exist at all when it costs one `syscall.Umask` call.

This is an explicit, scoped follow-up to the P3 raised on #450 (the daemon
unattended-start PR, `d951571`, which introduced `openLocalStore` and
`restrictDBPerms` as they exist today). It was deliberately not folded into
#450 because `syscall.Umask` is POSIX-only and has no equivalent on Windows,
and `cmd/local` now cross-compiles for `windows/amd64` as one of the five
release targets in `.github/workflows/release-please.yml`
(`darwin/arm64 darwin/amd64 linux/amd64 linux/arm64 windows/amd64`). A bare
`syscall.Umask` call would fail to compile on Windows, so the fix needs a
build-tagged pair of files rather than a one-line change in `main.go`.

## User stories
- AS a Local Bridge user running the daemon on Linux or macOS, I WANT the
  local session database to be created with owner-only permissions from the
  first byte SO THAT no other local account can ever observe even the
  encrypted session ciphertext.
- AS a Windows user of the Local Bridge daemon, I WANT the build to keep
  compiling and behaving exactly as it does today SO THAT this security
  hardening for POSIX systems does not regress the Windows binary that
  ships with every release.
- AS a maintainer, I WANT the existing chmod-based repair kept in place SO
  THAT databases created by daemons installed before this fix (or sidecar
  files recreated by the SQLite driver under a stale umask) are still
  corrected on every open.

## Acceptance criteria (EARS)
- WHEN `runDaemonCmd` or `runLogin` runs on a non-Windows GOOS, THE SYSTEM
  SHALL call `restrictUmask()` before `openLocalStore` is invoked, setting
  the process umask to `0o077` so any file the process creates thereafter
  is born without group or world permission bits.
- WHEN `runDaemonCmd` or `runLogin` runs on GOOS `windows`, THE SYSTEM SHALL
  call a no-op `restrictUmask()` that compiles cleanly and performs no
  syscall, since `syscall.Umask` does not exist on Windows and NTFS does not
  honor POSIX mode bits.
- WHILE the daemon or login command is running on a non-Windows platform,
  THE SYSTEM SHALL continue to call `restrictDBPerms(dbPath)` exactly as it
  does today, immediately after the database is opened and migrated, so
  that pre-existing files (from installs predating this fix, or sidecars the
  driver recreates) are still repaired to `0600`.
- IF `restrictUmask()` is called more than once in a single process
  lifetime (e.g. both `login` then later `daemon` in the same run, if that
  ever becomes possible), THEN THE SYSTEM SHALL remain correct — `syscall.Umask`
  is idempotent (each call sets and returns the previous mask), so calling
  it twice with the same value `0o077` is safe and requires no additional
  guard.
- WHEN a file is created in a temporary directory on a non-Windows platform
  after `restrictUmask()` has been called, THE SYSTEM SHALL create that file
  with mode `0600` (assuming the file is opened with a `0666`-or-narrower
  requested mode, as `os.WriteFile`/SQLite do), verified by a test that
  skips on Windows.
- IF the umask change and the chmod-based repair together are both present,
  THEN THE SYSTEM SHALL treat them as complementary, not redundant: the
  umask closes the creation-time race; the chmod remains the only mechanism
  that fixes files that already exist with wider permissions from before
  this fix shipped.

## Out of scope
- Any Windows ACL-based permission tightening for `state.db` on that
  platform. The issue explicitly defers this ("ACLs are the open question
  there") and only asks for a compiling no-op on Windows.
- Changing `restrictDBPerms` itself, its call site, or its chmod logic —
  it is retained unmodified per the issue's "both mechanisms are needed"
  requirement.
- Restricting the umask process-wide for unrelated file creation outside
  `cmd/local` (e.g. the server binary `cmd/server`, which does not manage a
  local encrypted SQLite file and is out of scope for this daemon-only fix).
- Retroactively auditing or rotating session data that may have been
  exposed by the pre-fix race on already-deployed installs; `restrictDBPerms`
  already covers repairing the file mode going forward, and re-keying is a
  separate concern not raised by the issue.

## Open questions
- The issue says "Called once in `runDaemonCmd` and `runLogin` before
  `openLocalStore`" but does not mention `runInit` (which also writes
  `config.json` with an explicit `0o600` via `writeFileAtomic`, so it is
  already safe) or `runConnect` (which writes `bridge_token.json`, also via
  `writeFileAtomic` with `0o600`). Interpretation used here: only the two
  call sites the issue names get the `restrictUmask()` call, since every
  other file-writing path in `cmd/local` already passes an explicit `0600`
  mode to `os.OpenFile`/`writeFileAtomic` and does not depend on the process
  umask. This proposal does not add the call to `runInit`/`runConnect`.
- Whether `restrictUmask()` should be process-wide (`syscall.Umask` has no
  per-goroutine or scoped variant) is not really an open question — Go's
  umask is always process-global — but it is worth recording: after this
  change, every file the `mctl-telegram-local` process creates for the rest
  of its lifetime (both `login` and `daemon` are short-lived, single-purpose
  invocations of the binary) will be born with no group/world bits,
  including any future file the codebase adds without thinking about
  permissions. Treated as a acceptable, even desirable, side effect, not a
  risk to mitigate.
- None beyond the above; the issue is otherwise fully specified down to
  suggested filenames, build tags, call sites, and the shape of the test.
