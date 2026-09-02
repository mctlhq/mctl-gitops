# Design: issue-454-feat-local-accept-the-mcp-token-from-a-f

## Current state

`cmd/local/main.go` implements the `connect` subcommand in `runConnect`
(around line 214):

```go
fs := flag.NewFlagSet("connect", flag.ExitOnError)
mcpToken := fs.String("token", "", "MCP JWT from your mctl-telegram connector settings")
server := fs.String("server", "", "Override the server URL (default: from config.json)")
if err := fs.Parse(args); err != nil {
    die(err)
}

if *mcpToken == "" {
    fmt.Fprintln(os.Stderr, "Get your MCP token from your mctl-telegram connector settings, then run:")
    fmt.Fprintln(os.Stderr, "  mctl-telegram-local connect --token <token>")
    os.Exit(2)
}
```

`*mcpToken` then flows straight into the `Authorization: Bearer` header of the
bridge-token exchange request, and into `bridgeTokenFile.MCPToken`, which
`saveBridgeToken` persists to `~/.config/mctl-telegram-local/bridge_token.json`
(`cmd/local/config.go`, `bridgeTokenFile` struct at line 59-ish,
`saveBridgeToken` at line 167). That stored copy is what `runDaemon` /
`refreshBridgeToken` (`cmd/local/daemon.go`) use to mint new bridge tokens
later — the flag value itself is never referenced again after `connect`
returns.

The project already has a precedent for "accept a secret from a file, not just
inline" in this same file: `promptPassphrase` / `passphraseFromEnv`
(`cmd/local/main.go` lines ~414-506) resolve the DB-encryption passphrase from
`MCTL_LOCAL_PASSPHRASE_FILE` (preferred) or `MCTL_LOCAL_PASSPHRASE`, falling
back to an interactive `term.ReadPassword` prompt only when neither is set and
a TTY is present. That function trims `\r\n` with `bytes.TrimRight(data,
"\r\n")` and rejects an empty result — exactly the trimming behavior this issue
asks for ("Trim a trailing newline, as `MCTL_LOCAL_PASSPHRASE_FILE` already
does").

`docs/local-bridge.md` (lines 166-191) documents the `connect` step, states the
`ps`/`/proc` exposure explicitly, recommends deleting the token file after use,
and says "A `--token-file` option that avoids the argument list entirely is
tracked in #454" — i.e. the docs already anticipate this exact change and just
need the placeholder sentence replaced with real instructions.

There is no existing "-" (stdin) convention anywhere in `cmd/local/`, so that
part of the design is new, though a common CLI pattern elsewhere.

## Proposed solution

Add a `--token-file` flag to the `connect` `FlagSet` in `runConnect`, alongside
the existing `--token`, and add a small resolver function that both flags feed
into.

1. **New flag.**
   ```go
   tokenFile := fs.String("token-file", "", "Read the MCP token from this file (\"-\" for stdin)")
   ```

2. **Resolver function** `resolveMCPToken(token, tokenFile string, stdin io.Reader, readFile func(string) ([]byte, error)) (string, error)`,
   placed near `passphraseFromEnv` for locality with the existing "secret from
   file" pattern, with injectable I/O for the same reason
   `passphraseFromEnv` takes `getenv`/`readFile` params — testability without
   touching the real filesystem/stdin. Behavior:
   - `token != "" && token != "-" && tokenFile != ""` -> error: "--token and
     --token-file are mutually exclusive".
   - `token == "-"` -> treat as `tokenFile = "-"` (alias), fall through to the
     stdin/file branch below.
   - `tokenFile == "-"` -> read all of `stdin` with `io.ReadAll`, trim
     `\r\n` via `bytes.TrimRight`, error if empty ("no MCP token on stdin").
   - `tokenFile != ""` (and not `-`) -> `readFile(tokenFile)`, wrap read errors
     with the path (`fmt.Errorf("read --token-file %s: %w", tokenFile, err)`),
     trim `\r\n`, error if empty ("%s contains no MCP token", tokenFile).
   - `token != "" && token != "-"` -> return `token` as-is (existing behavior,
     unchanged).
   - all empty -> return `"", nil` (caller keeps today's "print usage, exit 2"
     path for this case, so the resolver does not need to know about usage
     text).

3. **`runConnect` changes.** Replace the direct `*mcpToken == ""` check with:
   ```go
   mcpTokenVal, err := resolveMCPToken(*mcpToken, *tokenFile, os.Stdin, os.ReadFile)
   if err != nil {
       die(err)
   }
   if mcpTokenVal == "" {
       fmt.Fprintln(os.Stderr, "Get your MCP token from your mctl-telegram connector settings, then run:")
       fmt.Fprintln(os.Stderr, "  mctl-telegram-local connect --token-file <path>   (or --token-file - to read stdin)")
       os.Exit(2)
   }
   ```
   Every later use of `*mcpToken` in `runConnect` (the `Authorization` header,
   `bridgeTokenFile.MCPToken`) switches to `mcpTokenVal`. No other function
   signature in the file needs to change — `mcpTokenVal` is a local `string`,
   same type as `*mcpToken` was.

4. **Docs.** Update `docs/local-bridge.md` section "3. `connect`" (lines
   166-191): keep the existing `--token "$(cat ...)"` example but mark it as
   the interactive/convenience form, add the `--token-file mcp-token.txt` and
   `op read ... | mctl-telegram-local connect --token-file - --server ...`
   forms as the recommended ones, and replace the "tracked in #454" sentence
   (it is no longer forward-looking once this lands).

This keeps the change entirely inside `cmd/local/main.go` (plus the doc file):
no changes to `internal/`, no new persisted state, no protocol change against
the server. The mutual-exclusion and empty-file/empty-stdin checks all happen
before any HTTP request is built, matching the acceptance criteria ("without
making any network request").

## Alternatives

1. **Environment variable (`MCTL_LOCAL_MCP_TOKEN[_FILE]`), mirroring
   `MCTL_LOCAL_PASSPHRASE[_FILE]`.** Rejected as the primary mechanism: the
   issue explicitly asks for `--token-file` and stdin, not an env var, and an
   env var is a different (not obviously better) exposure surface — visible to
   the whole process tree via `/proc/<pid>/environ` and inherited by children,
   and it would need its own `connect`-only lifetime story since `connect` is a
   one-shot command, not a long-running daemon like the passphrase case. Could
   be added later as a genuinely separate follow-up without conflicting with
   this design.

2. **Only support `--token-file <path>`, drop the `--token -` stdin alias and
   require `--token-file -` for stdin.** Simpler (one less alias branch), and
   still satisfies the issue's parenthetical "(or `--token-file -`)". Rejected
   because the issue's suggested shape lists `--token -` first as the primary
   form for stdin, and supporting both is a few lines of resolver code, not a
   new mechanism — keeping both maximizes compatibility with whatever the user
   ends up typing.

3. **Change `--token`'s meaning so a bare `--token` (no value) implicitly reads
   stdin**, instead of requiring the explicit `-` sentinel. Rejected: Go's
   `flag` package cannot distinguish "flag present with no argument" from
   "flag absent" for a string flag in a way that is unambiguous and portable,
   and an implicit-stdin default is a footgun (a script that forgets to pass
   `--token` at all would hang reading stdin instead of failing fast with the
   current "flag required" usage message). The explicit `-` sentinel, matching
   common Unix CLI convention (e.g. `tar`, `curl -d @-`), avoids that ambiguity
   entirely.

## Platform impact

- **Migrations:** none. No schema, no config-file format change.
  `bridgeTokenFile.MCPToken` continues to hold a plain string exactly as
  before; only how that string is obtained inside `runConnect` changes.
- **Backward compatibility:** full. `--token <value>` keeps working exactly as
  today for any value that is not the literal string `-`. Existing scripts and
  the current `docs/local-bridge.md` example (`--token "$(cat
  mcp-token.txt)"`) are unaffected.
- **Resource impact:** negligible — one extra flag definition, a few lines of
  string handling, at most one `os.ReadFile` or `io.ReadAll` of a short-lived
  CLI invocation.
- **Risks + mitigations:**
  - *Risk:* a caller passes `--token -` intending the literal two-character
    string `-` as a token value, and gets stdin-read behavior instead.
    *Mitigation:* `-` is the standard stdin sentinel in Unix CLIs and is not a
    plausible real token value (MCP tokens are JWTs); documented explicitly in
    both `--help`/usage text and `docs/local-bridge.md`.
  - *Risk:* `--token-file` read from a path that is itself group/world
    readable does not fully close the exposure the issue raises (the token
    still passes through the process's argument list is avoided, but a poorly
    permissioned file is its own leak). *Mitigation:* out of scope per the
    issue (it only asks to stop putting the secret in `argv`); the existing
    doc guidance to delete the token file after use, and `restrictUmask()`
    already running at process start for files this binary creates itself,
    are unaffected and still apply. Reading an existing file's permissions is
    not something `connect` can enforce on a file it did not create.
  - *Risk:* reading all of stdin with `io.ReadAll` on a caller that pipes an
    unbounded stream (e.g. accidentally `cat /dev/urandom |`) could block or
    consume memory. *Mitigation:* this is a short-lived, manually invoked CLI
    command already trusted with the same secret via a flag argument; no
    existing code in `cmd/local` bounds `os.ReadFile` reads either (e.g. the
    passphrase file path), so this matches established practice in the file
    rather than introducing a new risk class.
