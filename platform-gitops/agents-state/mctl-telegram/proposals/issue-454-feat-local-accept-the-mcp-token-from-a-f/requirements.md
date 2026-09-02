# Accept the MCP token from a file or stdin, not only --token

## Context

`mctl-telegram-local connect` (`cmd/local/main.go`, `runConnect`) currently accepts
the MCP token only through the `--token` flag. The documented invocation is:

```sh
./mctl-telegram-local connect --token "$(cat mcp-token.txt)" --server https://tg.mctl.ai
```

Any argument passed on a process's command line is visible to every other local
account for the lifetime of the process, via `ps` or `/proc/<pid>/cmdline` on
Linux. `docs/local-bridge.md` already documents this exposure explicitly (lines
183-191) and tells the reader to delete the token file afterwards and to run
`connect` "when nobody else is logged in" as a mitigation.

The MCP token is the worst credential in this system to expose this way: unlike
the bridge token it is exchanged for (which lives about an hour, per
`bridgeTokenExpiry` / `tokenRefreshAdv` in `cmd/local/daemon.go`), the MCP token
is long-lived — months, per the doc and the `runConnect` comments — and the
daemon keeps re-exchanging it for fresh bridge tokens over the life of the
install. A single `ps` snapshot during `connect` is enough to capture it for
that entire window.

This is the same defect class the project already fixed once: the Local Bridge
pilot's one-shot SQL Job was changed to take its database password from
`PGPASSWORD` rather than a `psql` connection-string argument
(mctlhq/mctl-gitops#969). The fix here is the CLI-argument analogue: stop
requiring the secret to be typed into `argv`.

## User stories

- AS an operator running `connect` on a shared machine I WANT to supply the MCP
  token via a file path or stdin SO THAT the token never appears in `ps` output
  or `/proc/<pid>/cmdline` where other local accounts can read it.
- AS an operator using a password manager I WANT to pipe the token directly into
  `connect` SO THAT the token never touches a shell history file or an
  intermediate plaintext file on disk.
- AS an existing user who already scripts `connect --token "$(cat ...)"` I WANT
  that invocation to keep working SO THAT this change does not break existing
  automation or documented interactive use.

## Acceptance criteria (EARS)

- WHEN `connect` is invoked with `--token-file <path>` THE SYSTEM SHALL read the
  MCP token from the file at `<path>`, trimming a single trailing newline (and
  `\r\n`), before using it for the bridge-token exchange.
- WHEN `connect` is invoked with `--token-file -` THE SYSTEM SHALL read the MCP
  token as a single line from stdin, trimming the trailing newline.
- WHEN `connect` is invoked with `--token -` THE SYSTEM SHALL behave identically
  to `--token-file -` (read the token from stdin).
- WHEN `connect` is invoked with `--token <value>` (any value other than `-`)
  THE SYSTEM SHALL continue to accept the token as a literal flag argument,
  unchanged from current behavior.
- IF both `--token` and `--token-file` are supplied (and neither is the `-`
  sentinel making them equivalent forms of the same source) THEN THE SYSTEM
  SHALL reject the invocation with a clear error and a non-zero exit code,
  without making any network request.
- IF neither `--token` nor `--token-file` is supplied THEN THE SYSTEM SHALL
  print the existing usage guidance and exit non-zero, as it does today.
- IF `--token-file <path>` names a file that cannot be read (missing,
  permissions) THEN THE SYSTEM SHALL fail with an error naming the flag and the
  path, without making any network request.
- IF the token file (or stdin) is empty after trimming THEN THE SYSTEM SHALL
  fail with a clear error, without making any network request.
- WHEN the token is read from `--token-file` or from stdin THE SYSTEM SHALL NOT
  log or print the token value anywhere (matching current behavior for
  `--token`).
- WHILE the resolved token (from either source) is used for the bridge-token
  exchange and persisted to `bridge_token.json` THE SYSTEM SHALL treat it
  identically regardless of how it was supplied — same `Authorization: Bearer`
  header, same `bridgeTokenFile.MCPToken` persistence via `saveBridgeToken`.

## Out of scope

- Changing how the bridge token itself (`bridge_token.json`) is stored or
  protected — it already gets a 0600-equivalent path via `saveBridgeToken` /
  `restrictUmask`, and this proposal does not touch that.
- Adding a `--token-file`/stdin equivalent to `login`'s 2FA password or code
  prompts, or to `init`'s passphrase prompts — those are interactive by design
  and out of scope for this issue.
- Adding an environment-variable form (e.g. `MCTL_LOCAL_MCP_TOKEN`) analogous to
  `MCTL_LOCAL_PASSPHRASE` / `MCTL_LOCAL_PASSPHRASE_FILE`. The issue asks
  specifically for `--token-file` and stdin (`--token -`); an env var is a
  different exposure surface (visible via `/proc/<pid>/environ` and to child
  processes) and is not requested. Can be a follow-up if desired.
- Updating `docs/local-bridge.md` prose beyond the `connect` section's token
  guidance (the task list covers that section specifically).

## Open questions

- Should `--token -` and `--token-file -` both be accepted as stdin sentinels,
  or only `--token-file -` as the issue's primary suggestion states ("or
  `--token-file -`")? The issue body proposes both forms as acceptable
  ("`--token -` (or `--token-file -`)"), so this proposal implements both for
  consistency and to match the issue text exactly. Interpretation: both work,
  and they are the same code path.
- Exact error-exit convention: the codebase uses `os.Exit(2)` for usage errors
  (missing `--token`) and `die(err)` (message + `os.Exit(1)`) for operational
  failures elsewhere in `cmd/local/main.go`. This proposal follows that
  existing split: flag-usage problems (both-supplied, neither-supplied) use the
  `os.Exit(2)` + usage-message pattern already in `runConnect`; file/stdin read
  failures use `die(err)` like the rest of the file. Not called out further
  since it is a direct application of existing conventions, not a new decision.
