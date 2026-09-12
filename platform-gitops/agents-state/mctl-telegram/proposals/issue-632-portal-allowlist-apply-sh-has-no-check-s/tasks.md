# Tasks: issue-632-portal-allowlist-apply-sh-has-no-check-s

- [ ] 1. Add a `usage` function and a three-way mode parser to
      `scripts/portal-allowlist-apply.sh`, replacing the `case` at lines 27-32.
      `""` -> apply, `--dry-run` -> dry-run, `--check` -> check, `-h|--help` ->
      usage on stdout and exit 0, anything else -> usage on stderr and exit 2.
      Keep the `[ $# -le 1 ]` arity guard. — DoD: `--help` exits 0 and names all
      three modes and the exit codes; `--bogus` still exits 2; no behaviour
      change for `""` and `--dry-run`.

- [ ] 2. Extend the script's header comment (lines 1-24) to describe `--check`:
      what it compares (`default_disabled` plus each synced tool's `enabled`),
      that it never writes, that the same guards apply, and the exit codes
      (0 in sync, 1 could not check, 2 usage, 3 drift). (depends on 1) — DoD:
      the header and `usage` agree with each other and with the implementation.

- [ ] 3. Make the uncovered-synced-tools block (lines 118-124) mode-aware: keep
      today's early refusal for apply and dry-run; in check mode collect the
      names into a drift accumulator and continue. Leave the "no synced tools"
      hard error at line 116 unconditional. (depends on 1) — DoD: a check run
      against a portal with a synced tool absent from the file reports it as a
      drift row and still evaluates every other tool in the same run; the apply
      path's refusal message is unchanged.

- [ ] 4. Implement the comparison after `body` is built (after line 141):
      extract the `tg` mapping from `body` (expected) and from `current`
      (actual), and emit one `drift:` line per difference in `default_disabled`
      and in the union of `updated_tools` names. Use `has("enabled")` with an
      explicit `absent` sentinel; use no `//` operator anywhere in this path,
      with a comment saying why (it substitutes on `false` as well as `null`).
      (depends on 3) — DoD: the comparison reads the expected side from the
      apply's own `body`, so it covers exactly what a `PUT` would write; the
      report names the tool, the portal's value and the file's value.

- [ ] 5. Add the check-mode exit path above the `--dry-run` line (143), so the
      mode returns before the script's single `PUT` at line 148. In sync: the
      `in sync: default_disabled=… tools=… enabled=…` line, plus a
      `held back (not synced by the server): …` line when the file decides
      tools the server has not synced; exit 0. Drift: the `drift:` lines on
      stdout, a count on stderr, exit 3. (depends on 4) — DoD: `grep -n 'X PUT'`
      shows one call site and it is below the check-mode exit; the in-sync
      summary cannot print empty (same `jq -e`/`select(. != null)` discipline
      as the `applied:` summary at lines 154-157).

- [ ] 6. Extend the test harness in `scripts/portal_allowlist_apply_test.go`:
      add an `args []string` case field defaulting to `{"--dry-run"}` and use it
      at line 136; add `wantCode int` so a case can assert exit 3 via
      `exec.ExitError.ExitCode()`. (depends on 1) — DoD: all eleven existing
      cases pass unchanged with no edits to their literals beyond the new
      fields.

- [ ] 7. Extend `stubCurl` to record and to refuse writes: append
      `method<TAB>url` per invocation to `$STUB_CURL_LOG`, answer any
      invocation carrying `-X PUT` with an unsuccessful envelope naming the
      unexpected write, and serve the portal body from `$STUB_PORTAL_BODY` when
      that file exists (current constant otherwise). Set both variables in
      `cmd.Env` in the case runner. (depends on 6) — DoD: the existing dry-run
      cases still pass against the default body; a case can make the live portal
      match or differ by writing one file; a `PUT` is both visible in the log
      and fatal to the run.

- [ ] 8. Update `docs/cloudflare-portal-compat.md`, section "Portal tool
      allowlist — the drift guard" (lines 139-150): add `--check` to the command
      block and a paragraph covering what it compares, the guards, the exit
      codes, that it never writes, and that wiring it into CI is
      mctlhq/mctl-gitops#1211 and not part of this change. (depends on 5) —
      DoD: an operator can run the check from the document alone; no allowlist
      decision is described as changing.

- [ ] 9. Run `go fmt ./...`, `go vet ./...`, `golangci-lint`, `shellcheck` on
      the script, and `go test -race ./scripts/ ./internal/mcp/ -count=1`.
      (depends on 7) — DoD: clean; no emoji; conventional commit
      `feat(scripts): add --check drift detection to portal-allowlist-apply.sh`.

- [ ] 10. Record the mutation proof in the PR body: the green run and the red
      run from T1/T2 (command, output, exit status), and the call-log evidence
      from T5 that no `PUT` was issued. (depends on 9) — DoD: a reviewer can see
      the detector going both ways without running anything, as the issue's
      acceptance criteria require.

## Tests

All in `scripts/portal_allowlist_apply_test.go`, driving the real script
against throwaway checkouts built by `newFixture` (fixture allowlist:
`get_my_send_status` enabled, `send_message` disabled).

- [ ] T1. `--check` against a portal whose `tg` mapping matches the fixture
      (`default_disabled: true`, `updated_tools`
      `[{get_my_send_status,true},{send_message,false}]`) exits 0 and prints
      `in sync:`. The green half of the mutation proof.
- [ ] T2. The same fixture and the same stubbed body with exactly one field
      changed — `send_message` at `enabled: true` — exits 3 and prints
      `drift: send_message portal=true file=false`. The red half.
- [ ] T3. `default_disabled: false` live, nothing else changed: exits 3 and the
      report names `default_disabled`.
- [ ] T4. Live `updated_tools` carries a tool the file does not decide, and a
      second body omits a tool the file does decide: each exits 3 and the report
      names the tool with `file=absent` / `portal=absent` respectively — neither
      direction is skipped, and `absent` never reads as `false`.
- [ ] T5. Every `--check` case asserts `$STUB_CURL_LOG` contains no `PUT`,
      including T2/T3/T4 where the file and the portal disagree. The no-write
      proof, by observation of the stub rather than by reading the script.
- [ ] T6. A synced tool with no decision in the file: under `--check` it is
      reported as drift with exit 3 (not the apply path's early refusal), and
      the run still evaluates the other tools.
- [ ] T7. A file entry for a tool the server has not synced is not drift: exit 0
      with the `held back (not synced by the server):` line naming it.
- [ ] T8. `--check` inherits the guards: at least the uncommitted-edit case
      (`differs from HEAD`) and the missing-`go` case run with `--check`, each
      refused with exit 1, today's message, and an empty call log — the portal
      is never contacted.
- [ ] T9. An unsuccessful API envelope and a portal with no `tg` mapping each
      exit 1 under `--check`, distinct from the drift code: nothing was
      measured.
- [ ] T10. `--help` exits 0 and its output contains `--check`; `--bogus` exits 2;
      two arguments exit 2.
- [ ] T11. The existing eleven `--dry-run` cases still pass unchanged, including
      the positive case and the TOCTOU case — proof that apply and dry-run are
      untouched.

## Rollback

The change is three files in one merge commit and no deployed artifact: no
migration, no image, no GitOps values, nothing the server executes at runtime.
`git revert -m 1 <merge sha>` restores the two-mode script, the previous test
file and the previous document; nothing else in the repository depends on
`--check` (mctlhq/mctl-gitops#1211, the only prospective consumer, is out of
scope here and cannot exist before this lands).

If `--check` proves noisy in operator use rather than wrong — for example a
Cloudflare response shape that makes a benign field read as drift — the
narrower rollback is to leave the mode in place and stop running it, since
nothing schedules it and the apply and `--dry-run` paths are unaffected by it
in either direction. A false green is the more dangerous failure: if a check
reports "in sync" against a portal a human then finds drifted, treat the mode
as untrusted, re-verify by hand in the Cloudflare UI, re-apply, and fix the
comparison with a new mutation case covering whatever it missed before
trusting it again.
