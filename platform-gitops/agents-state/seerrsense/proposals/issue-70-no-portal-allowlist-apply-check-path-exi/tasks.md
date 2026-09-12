# Tasks: issue-70-no-portal-allowlist-apply-check-path-exi

- [ ] 1. Read the reference implementation before writing anything:
  `mctlhq/mctl-telegram` `scripts/portal-allowlist-apply.sh` and
  `scripts/portal_allowlist_apply_test.go` at `main`. — DoD: the exit-code
  table (0 applied/in sync, 1 could not apply or check, 2 usage error, 3 drift),
  the pre-flight order, and the exact output strings (`drift: <tool>
  portal=<v> file=<v>`, `drift: default_disabled portal=<v> file=<v>`,
  `drift: <tool> synced by the server with no decision in
  docs/portal-allowlist.json`, `in sync: default_disabled=<b> tools=<n>
  enabled=<names>`, `held back (not synced by the server): <names>`,
  `applied: default_disabled=<b> tools=<n> enabled=<names>`, `<n>
  difference(s) between the portal and docs/portal-allowlist.json`,
  `is not tracked`, `differs from HEAD`, `expected exactly one`) are written
  down and used verbatim. No string is re-invented.

- [ ] 2. Add `scripts/portal-allowlist-apply.mjs` skeleton: header comment in the
  style of `scripts/sync-tokens.mjs` (why it exists, what is sent, the token
  discipline, the exit-code table), argument parsing for
  `""` / `--dry-run` / `--check` / `-h` / `--help`, `usage()`, and the
  credential check on `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`.
  (depends on 1) — DoD: `--help` exits 0 and names all four modes and all four
  exit codes; an unknown flag and a second argument both exit 2 with usage on
  stderr; a missing credential refuses before any network call.

- [ ] 3. Implement the git pre-flight in the reference's order, via
  `execFileSync("git", ["-C", root, ...])`: `rev-parse --git-dir`, then
  `ls-files --error-unmatch -- docs/portal-allowlist.json`, then
  `diff --quiet HEAD -- docs/portal-allowlist.json`; then read the vetted
  content with `git show HEAD:docs/portal-allowlist.json` and use only that
  afterwards. (depends on 2) — DoD: not-a-checkout, untracked-but-on-disk,
  staged-only edit and unstaged edit each exit 1 with the reference's message
  fragment; no code path re-reads `docs/portal-allowlist.json` from the working
  tree after this step.

- [ ] 4. Pin the target: refuse unless `vetted.portal === "mcp"` and
  `vetted.server === "seerrsense"`, with the message
  `docs/portal-allowlist.json targets portal=<p> server=<s>; expected
  mcp/seerrsense`. (depends on 3) — DoD: a committed fixture naming any other
  portal or server exits 1 and no request is made.

- [ ] 5. Implement the guard-test gate: spawn `node_modules/.bin/vitest run
  tests/portal-allowlist.test.ts --reporter=json --outputFile <tmp>` with cwd at
  the repository root, `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`
  deleted from the child environment, and `SEERR_API_KEY`,
  `SEERRSENSE_AUTH_TOKEN`, `LOG_LEVEL` set as `package.json`'s `test` script
  sets them. Verify the installed vitest 5 JSON report field names first and
  fail closed on an unrecognised shape. (depends on 4) — DoD: a missing
  `node_modules/.bin/vitest` exits 1 telling the operator to run `npm ci`; a
  failing guard exits 1 and prints the captured output; a run that reports zero
  passed tests, any failed test, or no result for
  `tests/portal-allowlist.test.ts` is treated as a failure even if the process
  exited 0; the temp report file lives under the OS temp directory and is
  removed.

- [ ] 6. Implement the Cloudflare reads: `GET {base}/portals/mcp` and
  `GET {base}/servers/seerrsense` against
  `https://api.cloudflare.com/client/v4/accounts/{account}/access/ai-controls/mcp`,
  with `Authorization: Bearer` taken from the in-process variable; require
  `success === true`, exactly one mapping for `server_id === "seerrsense"`, and
  a non-empty `result.tools`. Add the `SEERRSENSE_PORTAL_API_BASE` override,
  honoured only for hostname `127.0.0.1`, `::1` or `localhost` and exiting 2
  otherwise. (depends on 5) — DoD: each failure exits 1 with the reference's
  wording; the token appears in no argument, no message and no thrown error; a
  non-loopback override exits 2 without making a request.

- [ ] 7. Build the request body: deep copy `result`, delete `created_at`,
  `created_by`, `modified_at`, `modified_by`, rewrite only the `seerrsense`
  element's `default_disabled` and `updated_tools`, where `updated_tools` is the
  vetted tools filtered to names the server has synced, each projected to
  `{name, enabled: <boolean>}` and never `null`. (depends on 6) — DoD:
  `--dry-run` prints the body and exits 0; no other server element and no other
  field differs from what was read; a vetted entry with a non-boolean `enabled`
  still writes a boolean.

- [ ] 8. Handle synced-but-undecided tools per mode: in apply and `--dry-run`,
  refuse with exit 1, list them and print the "the portal may not have
  re-synced yet; do not add them back to the file" hint; in `--check`,
  accumulate them as `drift: <tool> synced by the server with no decision in
  docs/portal-allowlist.json` and keep evaluating the rest of the run.
  (depends on 7) — DoD: both behaviours are reachable from the same fixture by
  changing only the mode.

- [ ] 9. Implement `--check`: expected side read out of the task-7 body, actual
  side read out of the task-6 portal response, a `sentinel(side, name)` helper
  built from `Object.hasOwn` that yields `true`, `false` or the string
  `"absent"`, drift lines for `default_disabled` and for the sorted union of
  tool names, the `held back (not synced by the server): <names>` line, the
  `in sync: ...` line on agreement, the `<n> difference(s) ...` line to stderr,
  and exits 0 / 3. (depends on 8) — DoD: no `||`, `??` or other defaulting
  operator appears anywhere in the comparison path (grep the diff for it in
  review); `--check` issues no `PUT` on any path, including the drift path and
  every guard-refusal path.

- [ ] 10. Implement the apply: `PUT` the body to `{base}/portals/mcp`, require
  `success === true`, verify the response's `updated_tools` for `seerrsense`
  projected to `{name, enabled}` and sorted by name equal what was sent, then
  print the `applied: ...` summary. (depends on 9) — DoD: a dropped, flipped,
  added or missing entry in the response exits 1 with "verify the portal by
  hand"; a successful apply prints exactly one summary line.

- [ ] 11. Add `scripts/portal-allowlist-apply.sh`: resolve its own directory,
  refuse with exit 1 naming Node when `command -v node` fails, then
  `exec node "$dir/portal-allowlist-apply.mjs" "$@"`. Mark it executable.
  (depends on 10) — DoD: `scripts/portal-allowlist-apply.sh --check` and
  `--help` behave identically to the `.mjs` invocation, exit codes 0/1/2/3 pass
  through unchanged, and a host without Node exits 1 rather than 127.

- [ ] 12. Add `"portal:allowlist": "node scripts/portal-allowlist-apply.mjs"` to
  `package.json` scripts, next to `sync:tokens` / `check:tokens`. (depends on
  11) — DoD: `npm run portal:allowlist -- --check` reaches the same code path
  and preserves the exit code.

- [ ] 13. Update the `$comment` in `docs/portal-allowlist.json` to name this
  repository's own `scripts/portal-allowlist-apply.sh` (with `--check`) instead
  of pointing at mctl-telegram's, and add the operator subsection to `README.md`
  (the two environment variables, the four modes, the exit-code table, the
  `npm ci` prerequisite, and `--dry-run` as the documented first step).
  (depends on 11) — DoD: no tool's `enabled` value and no `reason` changes;
  `npm test` still passes, including `tests/portal-allowlist.test.ts` and
  `tests/landing.test.ts`.

- [ ] 14. Open the PR with the mutation proof recorded in the description:
  the matching fixture going green and the one-field-changed fixture going red,
  pasted as command output, plus a statement that no `PUT` was recorded in
  either. Use a conventional-commit subject (`feat(scripts): ...`) so
  release-please picks it up. (depends on T1-T5) — DoD: a reviewer can see both
  directions without running anything, and the PR says explicitly that no
  allowlist decision moved.

## Tests

All in `tests/portal-allowlist-apply.test.ts`, spawning the command rather than
importing it, with a per-case fixture repository under `mkdtemp` (the two
scripts, a two-tool fixture `docs/portal-allowlist.json`, a fixture
`tests/portal-allowlist.test.ts` the case controls, a fixture `package.json`, a
symlink to the real `node_modules`, `git init` plus a commit) and a loopback
`node:http` stub for the Cloudflare API that logs every request and answers any
`PUT` with a `success:false` "unexpected write" envelope. Skip the suite when
`git` is not on `PATH`.

- [ ] T1. Green half of the mutation proof: a stub portal matching the fixture
  exactly -> exit 0 and `in sync: default_disabled=true tools=2 enabled=<read
  tool>`; request log has no `PUT`.
- [ ] T2. Red half: T1's body with exactly one tool's `enabled` flipped ->
  exit 3, `drift: <tool> portal=true file=false`, no `PUT`.
- [ ] T3. `default_disabled` differing -> exit 3 and
  `drift: default_disabled portal=false file=true`.
- [ ] T4. Both absent directions: a tool live but not decided ->
  `... portal=<v> file=absent`; a tool decided but dropped from the live
  `updated_tools` -> `... portal=absent file=<v>`. Both exit 3.
- [ ] T5. A synced tool with no decision in the file -> exit 3 with the
  `synced by the server with no decision` line, and the other tool still
  evaluated in the same run.
- [ ] T6. A file entry for a tool the server has not synced -> exit 0, the
  `in sync` line, and `held back (not synced by the server): <name>`.
- [ ] T7. Inherited guards, each exit 1 with the reference's message fragment
  and an assertion that the request log is empty: uncommitted edit
  (`differs from HEAD`), staged-only edit (`differs from HEAD`), untracked but
  on disk (`is not tracked`), a committed file naming another portal/server
  (`expected mcp/seerrsense`), a missing local vitest binary (`npm ci`), a
  fixture guard that fails (output shown).
- [ ] T8. TOCTOU: a fixture guard that rewrites `docs/portal-allowlist.json` on
  disk to enable the write tool and then passes -> the `--dry-run` body still
  carries the committed decision (`"enabled": false` for that tool).
- [ ] T9. Credential stripping: a fixture guard that fails if it can see
  `CLOUDFLARE_API_TOKEN` or `CLOUDFLARE_ACCOUNT_ID` -> the run gets through the
  pre-flight, proving both were removed.
- [ ] T10. "Could not check" is not drift: a `success:false` portal envelope and
  a portal with no `seerrsense` mapping each exit 1 (not 3), with
  `read portal failed` and `expected exactly one` respectively.
- [ ] T11. Usage: unknown flag -> exit 2; two arguments -> exit 2; `--help` ->
  exit 0 and mentions `--check` and every exit code.
- [ ] T12. A non-loopback `SEERRSENSE_PORTAL_API_BASE` -> exit 2, empty request
  log.
- [ ] T13. Wrapper parity: run T1, T2 and T11 through
  `scripts/portal-allowlist-apply.sh` and assert identical exit codes and
  stdout.
- [ ] T14. Regression on the repository's own file: `--dry-run` against the real
  `docs/portal-allowlist.json` and a stub whose synced set is the five
  registered tool names produces `updated_tools` with all five and
  `enabled: true` for each, proving the real file round-trips through the body
  builder. (This asserts the current committed decision, not a new one.)
- [ ] T15. `npm test` and `npm run typecheck` pass unchanged, and
  `tests/source-hygiene.test.ts` still passes over the new `.ts` test file.

## Rollback

Nothing is deployed and no state is migrated, so rollback is a revert of the
single PR: `scripts/portal-allowlist-apply.mjs`, `scripts/portal-allowlist-
apply.sh`, `tests/portal-allowlist-apply.test.ts`, the `package.json` script
entry, and the `$comment` / `README.md` wording. `docs/portal-allowlist.json`'s
decisions are untouched by this change, so a revert cannot alter what the file
says. The repository returns to today's state: the allowlist is a statement of
intent with no apply and no detector, and mctlhq/mctl-gitops#1211 stays blocked.

If an apply has already been run and left the portal in an unwanted state, the
portal is recovered by committing the intended `docs/portal-allowlist.json` and
re-running the apply — the script is idempotent and the file is the source of
truth; `--check` then confirms agreement. If the portal must be restored without
this script, the same two `GET`s plus one `PUT` can be issued by hand from the
`--dry-run` output, which is exactly the body that would be sent. No Cloudflare
credential is added to this repository's CI by this change, so a revert leaves
no secret behind.
