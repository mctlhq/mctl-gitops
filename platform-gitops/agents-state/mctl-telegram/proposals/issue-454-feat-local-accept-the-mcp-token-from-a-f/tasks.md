# Tasks: issue-454-feat-local-accept-the-mcp-token-from-a-f

- [ ] 1. Add `resolveMCPToken(token, tokenFile string, stdin io.Reader, readFile func(string) ([]byte, error)) (string, error)` to `cmd/local/main.go`, placed near `passphraseFromEnv`, implementing: mutual-exclusion check (`--token` with a non-`-` value together with `--token-file`), `--token -` / `--token-file -` reading and trimming stdin, `--token-file <path>` reading and trimming the file, plain `--token <value>` passthrough, and both-empty returning `"", nil`. — DoD: function compiles, has a doc comment describing each branch, and does not itself call `die`/`os.Exit` (all error handling returns via the `error` return so the caller decides usage-vs-fatal, matching how `passphraseFromEnv` is structured).
- [ ] 2. Wire `--token-file` into `runConnect`'s `flag.NewFlagSet("connect", ...)`, call `resolveMCPToken` in place of the current `*mcpToken == ""` check, replace every later use of `*mcpToken` in `runConnect` (the `Authorization: Bearer` header, `bridgeTokenFile.MCPToken`) with the resolved value, and update the printed usage hint to mention `--token-file`. (depends on 1) — DoD: `go build ./...` succeeds; `mctl-telegram-local connect --help`-equivalent (running with no args) still prints usage and exits 2; the resolved token is never logged (grep the diff for any `slog`/`fmt.Print*` of the token value — there must be none beyond what already existed for `*mcpToken`).
- [ ] 3. Update `docs/local-bridge.md` section "3. `connect`" (currently lines 166-191): keep the `--token "$(cat mcp-token.txt)"` example labeled as the interactive/convenience form, add `--token-file mcp-token.txt` and the `op read ... | mctl-telegram-local connect --token-file - --server ...` stdin-pipe example from the issue, and replace the "A `--token-file` option ... is tracked in #454" sentence with guidance that `--token-file` is now the recommended way to avoid the argument-list exposure. (depends on 2) — DoD: doc no longer references #454 as a pending item; both new invocation forms appear verbatim as runnable shell examples matching the final flag names.
- [ ] 4. Update the top-of-file `usage` const and the `connect` line in `cmd/local/main.go` (`connect --token <t>  Exchange an MCP JWT ...`) to mention `--token-file` exists, matching the pattern used for other subcommands' usage lines. (depends on 2) — DoD: `mctl-telegram-local help` output mentions `--token-file`.

## Tests

- [ ] T1. Unit tests for `resolveMCPToken` in a new `cmd/local/connect_test.go` (or alongside `passphrase_test.go`'s style with injected `stdin`/`readFile`), covering: plain `--token` passthrough; `--token-file <path>` happy path with trailing `\n` and `\r\n` trimmed; `--token-file -` reads from an injected `io.Reader` (e.g. `strings.NewReader`) with trimming; `--token -` is equivalent to `--token-file -`; both `--token <value>` and `--token-file <path>` set together is an error and no request would be attempted; unreadable `--token-file` path surfaces an error naming the path; empty file content after trim is an error; empty stdin after trim is an error; both empty returns `"", nil` (no error) so the existing usage-hint path still fires. — DoD: `go test ./cmd/local/...` passes, including these new cases, mirroring the table-driven style of `TestPassphraseFromEnv` in `passphrase_test.go`.
- [ ] T2. Manual/CI smoke check that `--token` (no `--token-file`) against a real or stubbed `/api/bridge/token` endpoint still succeeds unchanged (regression guard for the "keep `--token` working" requirement) — DoD: existing `connect` integration coverage (if any exists in CI) still passes; otherwise note in the PR description that this was exercised manually against a test server.
- [ ] T3. `go vet ./... && golangci-lint run` clean on the changed files, per repo convention (`CLAUDE.md` "Conventions"). — DoD: both commands exit 0.

## Rollback

The change is additive and fully backward compatible: `--token <value>` keeps
working exactly as before for any non-`-` value, so no caller is forced onto
the new path. If a regression surfaces in `resolveMCPToken` or the flag wiring,
revert the single commit/PR that lands tasks 1-4 (squash-merged per this repo's
convention, so it is one commit on `main`) — this restores the prior
`*mcpToken == ""` check with no data migration or state cleanup needed, since
no persisted format changed. No feature flag is warranted given the small,
self-contained blast radius (one subcommand, one file plus docs).
