# Tasks: issue-300-portal-allowlist-apply-sh-has-no-check-m

- [ ] 1. Read the reference implementation before writing anything:
      `mctlhq/mctl-telegram` at `scripts/portal-allowlist-apply.sh` and
      `scripts/portal_allowlist_apply_test.go` (landed in
      mctlhq/mctl-telegram#634), plus `docs/cloudflare-portal-compat.md`
      sections on the apply and `--check`. — DoD: the diff written in tasks 2-6
      is a port of that shape with `tg` replaced by `api`, not an independent
      design; every user-visible string, flag and exit code matches.
- [ ] 2. Add mode dispatch and usage to `scripts/portal-allowlist-apply.sh`:
      `mode=apply|dry-run|check`, `-h|--help` printing a `usage()` heredoc that
      names all three modes and the exit-code table, unknown argument and
      >1 argument both `usage >&2` + exit 2. Usage answers before credentials,
      `jq`, git or Go are consulted. (depends on 1) — DoD: `--help` exits 0 and
      prints `--check` with no environment set; `--bogus` and `--check extra`
      exit 2.
- [ ] 3. Port the pre-flight hardening the reference carries and this copy
      lacks, in its order: `git rev-parse --git-dir`, `git ls-files
      --error-unmatch -- docs/portal-allowlist.json`, the existing
      `git diff --quiet HEAD`, then `vetted=$(git show
      HEAD:docs/portal-allowlist.json)`; read `portal`/`server` from `$vetted`
      and keep the `mcp`/`api` pin; run the guard test as
      `env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID go test -v
      ./internal/mcp/ -run '^TestPortalAllowlist_CoversEveryRegisteredTool$'
      -count=1`, capture its output, and require
      `^--- PASS: TestPortalAllowlist_CoversEveryRegisteredTool` in it,
      printing the captured output on refusal. Switch the downstream jq calls
      from `--slurpfile a "$file"` / `$a[0]` and `jq -r … "$file"` to
      `--argjson a "$vetted"` / `$a` and `<<<"$vetted"`. (depends on 2) —
      DoD: apply, `--dry-run` and `--check` all pass through the identical
      pre-flight; the body is built from the committed blob on every path.
- [ ] 4. Fold the "synced tool with no decision" case into a
      `uncovered_drift` accumulator when `mode = check`, leaving the immediate
      refusal in place for apply and `--dry-run`. (depends on 3) — DoD: a
      `--check` run with one undecided synced tool still evaluates the other
      tools and reports both categories in one run.
- [ ] 5. Implement the comparison after `$body` is built: `expected` read out
      of `$body`'s `api` element, `actual` read out of the portal GET's `api`
      element, a jq program emitting
      `drift: default_disabled portal=… file=…` and
      `drift: <tool> portal=<v|absent> file=<v|absent>` over the union of names,
      with every default built from `has()` and an explicit conditional and no
      `//` anywhere in the comparison. (depends on 4) — DoD: `enabled: false`
      on both sides compares equal (not "absent"), and a missing entry is
      reported as `absent`.
- [ ] 6. Wire the `--check` exit path: print the accumulated drift lines on
      stdout, the `<n> difference(s) between the portal and
      docs/portal-allowlist.json` count on stderr, exit 3; on agreement print
      the `in sync: default_disabled=… tools=… enabled=…` line (guarded by
      `select(. != null)`), then the
      `held back (not synced by the server): …` line when the file decides
      tools the server has not synced, and exit 0. Return before the
      `sent=`/PUT block on every path. (depends on 5) — DoD: no code path from
      `mode = check` reaches `cf -X PUT`.
- [ ] 7. Rewrite the script's header comment: the new usage line
      `[--dry-run|--check|-h|--help]`, what `--check` compares, that it is held
      to the same pre-flight as an apply, that it never PUTs on any path, and
      the exit-code table (0/1/2/3) with the statement that every non-zero
      status is a failure a caller must surface. (depends on 6) — DoD: the
      header, `usage()` and `README.md` agree with each other and with the
      implementation.
- [ ] 8. Add `scripts/portal_allowlist_apply_test.go` (`package scripts`,
      new file — this repository has no shell-script harness today), ported
      from the reference: `newFixture` building a throwaway checkout (real
      script, `module fixture` `go.mod` at Go 1.26.6, synthetic
      `internal/mcp/guard_test.go` with a controllable name/body/imports, a
      committed `mcp`/`api` allowlist with two fixture tools, and a `stub/`
      directory prepended to `PATH`); `stubCurl` recording `method<TAB>url` to
      `$STUB_CURL_LOG`, serving `GET /servers/api` from a canned list, serving
      `GET /portals/mcp` from `$STUB_PORTAL_BODY` when set, and answering any
      `PUT` with an unsuccessful envelope; `sandboxWithoutGo` for the missing-Go
      case; skips on Windows and on a host missing `git`/`jq`/`go`/`bash`.
      (depends on 7) — DoD: `go test ./scripts/` passes locally and the package
      is inert (skips, does not fail) where a binary is missing.
- [ ] 9. Update the "Portal tool allowlist" section of `README.md`
      (lines 386-397): add the `--check` invocation alongside `--dry-run` and
      the apply, what it compares, the pre-flight parity, the never-writes
      guarantee, the held-back rule, the exit-code table with `1` vs `3`
      spelled out, and the note that CI wiring is mctlhq/mctl-gitops#1211 so
      `--check` is operator-run today. (depends on 7) — DoD: an operator can
      run `--check` correctly from the README alone.
- [ ] 10. Record the both-directions mutation proof in the PR body: paste the
      `go test -run 'TestApplyCheck/(in_sync|.*enabled_live)' -v` output showing
      T1 exiting 0 on the matching fixture and T2 exiting 3 on the same fixture
      with exactly one field changed, and the assertion that the recorded call
      log holds no `PUT`. (depends on 8) — DoD: the PR body shows the detector
      going green and red, as the issue's acceptance requires.
- [ ] 11. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run` and
      `go test -p 1 ./...` as `.github/workflows/validate.yml` does. (depends
      on 8, 9) — DoD: clean, and the new `scripts` package neither breaks
      `go build ./...` nor the lint run.
- [ ] 12. Confirm no allowlist decision moved: `git diff` touches only
      `scripts/portal-allowlist-apply.sh`, `scripts/portal_allowlist_apply_test.go`
      and `README.md`. (depends on 11) — DoD: `docs/portal-allowlist.json`,
      `internal/mcp/portal_allowlist_test.go` and
      `internal/mcp/annotations_test.go` are unchanged in the diff.

## Tests

All in `scripts/portal_allowlist_apply_test.go` unless stated otherwise.

- [ ] T1. **Mutation proof, green half** — `--check` against a stubbed portal
      whose `api` mapping matches the committed fixture exactly exits 0 and
      prints `in sync: default_disabled=true tools=2 enabled=<enabled tool>`.
- [ ] T2. **Mutation proof, red half** — the same stub body with exactly one
      field changed (the disabled fixture tool flipped to `enabled: true` live)
      exits 3 and prints `drift: <tool> portal=true file=false`.
- [ ] T3. `default_disabled: false` live against `true` in the file exits 3 and
      prints `drift: default_disabled portal=false file=true`.
- [ ] T4. A tool live but absent from the file reports `file=absent`; a tool
      the file decides and the portal has dropped from `updated_tools` reports
      `portal=absent`. Both exit 3.
- [ ] T5. **No write, on every `--check` path** — the recorded curl log
      contains the two `GET` lines and no `PUT`, asserted for the in-sync case
      and for every drift case; the assertion is gated on the log being
      readable and showing the GETs, so a stub that stopped recording fails
      rather than passing vacuously.
- [ ] T6. A synced tool with no decision in the file is reported as
      `drift: <tool> synced by the server with no decision in
      docs/portal-allowlist.json` with exit 3 under `--check`, while the other
      decided tool is still evaluated in the same run — and is still an
      immediate refusal under `--dry-run`.
- [ ] T7. A file entry for a tool the server has not synced is not drift: exit
      0 with `held back (not synced by the server): <tool>`.
- [ ] T8. `--check` inherits the guards, proven per guard with an empty call
      log (nothing reached the network): uncommitted edit, staged-but-
      uncommitted edit, file untracked but present on disk, file retargeted to
      another server, host without `go`, guard test failing (its message is
      shown to the operator), guard test renamed, copy outside a checkout. Each
      exits 1.
- [ ] T9. "Could not check" is not "no drift": an unsuccessful API envelope
      exits 1 naming `read portal failed`, and a portal with no `api` mapping
      exits 1 naming `expected exactly one` — neither exits 3. Both reach the
      network, so both carry the same call-log evidence T5 requires: the log
      must be readable and show the GETs, and must contain no `PUT`. An error
      path is where an unexpected write is least likely to be looked for.
- [ ] T10. Usage: `--help` and `-h` exit 0 and name `--check` with no
      credential, checkout or Go present; `--bogus` exits 2; `--check extra`
      exits 2.
- [ ] T11. Regression on the existing paths: `--dry-run` still reaches and
      prints the PUT body for a clean committed fixture, and the body is built
      from the committed blob even when the guard test rewrites the on-disk
      file mid-run (the TOCTOU case).
- [ ] T12. Existing suite unaffected: `go test -p 1 ./...` green, in particular
      `internal/mcp` (`TestPortalAllowlist_CoversEveryRegisteredTool`,
      `server_test.go`'s tool-count expectation).
- [ ] T13. Manual, operator-run once against the live portal with a real
      credential: `--check` exits 0 on the current `api` mapping, or names what
      differs. Record the outcome in the PR; do not run an apply as part of
      this change.

## Rollback

`--check` never writes, so nothing on the portal can be in a bad state because
of this change; the rollback surface is this repository only.

1. Revert the single commit (`git revert <sha>`) — `scripts/portal-allowlist-apply.sh`
   returns to apply + `--dry-run` only, `scripts/portal_allowlist_apply_test.go`
   disappears, and `README.md` returns to the previous section. No portal call
   is needed and no allowlist decision is touched either way.
2. If only the new tests are the problem (CI wall time, a host without `jq`),
   delete `scripts/portal_allowlist_apply_test.go` and keep the script: the
   `--check` mode still works, but the mutation proof is gone, so re-add it
   before mctlhq/mctl-gitops#1211 depends on this script.
3. If `--check` is found to report drift wrongly, the safe intermediate state
   is to stop calling it — it has no side effects — rather than to "fix" the
   portal to match it. Confirm against the Cloudflare dashboard before any
   apply, since an apply is the only thing here that writes.
4. Ordering note: mctlhq/mctl-gitops#1211 will call both this script and
   `mctl-telegram`'s. Reverting here after that job lands makes it fail on
   `unknown argument: --check` (exit 2) for the `api` upstream, which is a
   loud, correct failure — but tell the owner of #1211 rather than leaving it
   to be discovered.
