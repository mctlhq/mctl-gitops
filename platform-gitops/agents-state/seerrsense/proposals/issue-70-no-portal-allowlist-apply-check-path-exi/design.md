# Design: issue-70-no-portal-allowlist-apply-check-path-exi

## Current state

What exists in this clone (commit `6900d5a`, "Merge pull request #69 from
mctlhq/feat/portal-allowlist-guard"):

- `docs/portal-allowlist.json` — the committed decision. `"portal": "mcp"`,
  `"server": "seerrsense"`, `"default_disabled": true`, and five entries:
  `whoami`, `search_media`, `resolve_media`, `get_media` (all
  `enabled: true`, all read) and `request_media` (`enabled: true`, the one
  write, with the 2026-09-12 owner decision in its `reason`). Its `$comment`
  currently points the reader at another repository for the apply flow:
  "Apply with the same operator-run flow as the other upstreams (mctl-telegram
  scripts/portal-allowlist-apply.sh, one file per server)".
- `tests/portal-allowlist.test.ts` — the guard. It instantiates a real server
  with `createSeerrSenseMcpServer()` (`src/mcp/server.ts:202`, all parameters
  optional) and reads the registered set out of `_registeredTools`, deriving
  write-ness from `annotations.readOnlyHint !== true`. It asserts
  `portal === "mcp"`, `server === "seerrsense"`, `default_disabled === true`,
  set equality between listed and registered names, a boolean `enabled` on
  every entry, a `reason` of at least 40 characters on every enabled entry, and
  that an enabled write tool is named in the file-local `writeToolsOnPortal`
  map (today: `request_media`). It reads `docs/portal-allowlist.json` from the
  working tree with `readFileSync`, relative to the process cwd.
- `src/mcp/server.ts` — registers exactly those five tools (lines 243, 262,
  283, 304, 327) with the `READ_ONLY` / `WRITE` annotation constants at lines
  45-46. `src/core/config.ts` parses the environment with every key optional or
  defaulted, so instantiating the server needs no environment; `npm test`
  nonetheless sets `SEERR_API_KEY`, `SEERRSENSE_AUTH_TOKEN` and `LOG_LEVEL`.
- `scripts/sync-tokens.mjs` — the only operator script in the repository, and
  the local precedent for this kind of tool: a Node ESM script with a default
  "write the file" mode and a `--check` mode that compares and
  `process.exit(1)`s on a difference, exposed as `npm run sync:tokens` /
  `npm run check:tokens` and run in CI by `.github/workflows/ci.yml`
  ("Design tokens are in sync"). There is no shell script anywhere in the
  repository, and no `jq` dependency.
- `.github/workflows/ci.yml` — `npm ci`, `npm run check:tokens`,
  `npm run typecheck`, `npm test` (with a Postgres service and
  `TEST_DATABASE_URL`), `docker build`. Nothing Cloudflare-related; the
  repository holds no Cloudflare credential.
- `tests/source-hygiene.test.ts` — walks `src/` and `tests/` for `.ts` files and
  rejects control characters. It does not look at `scripts/`.
- Release tooling: `release-please` (`release-please-config.json`,
  `.release-please-manifest.json`, `CHANGELOG.md`), so commits are
  conventional-commit shaped.

Missing, exactly as the issue says: nothing applies the file to Cloudflare and
nothing reads the portal back.

The reference implementation is `mctlhq/mctl-telegram`
`scripts/portal-allowlist-apply.sh` (mctl-telegram#632, merged) with its
behavioural test `scripts/portal_allowlist_apply_test.go`. It was read in full
while writing this design; the contract below is taken from it rather than
re-derived: modes `apply` / `--dry-run` / `--check` / `--help`; exit codes 0, 1,
2, 3; pre-flight in a fixed order (credentials, `jq`, git checkout, tracked,
equal to `HEAD`, portal/server pin, toolchain present, guard test passed with
positive evidence); the body built from the `HEAD` blob rather than the working
tree; the guard test run with the Cloudflare variables removed from its
environment; `updated_tools` restricted to tools the portal has synced; the
comparison's expected side taken from the apply's own body; and the explicit
warning that `jq`'s `//` substitutes on `false` as well as `null`, which is what
once made a matching baseline report as drifted.

## Proposed solution

Add three things, plus two documentation touches.

### 1. `scripts/portal-allowlist-apply.mjs` — the implementation

A Node ESM script in the shape of `scripts/sync-tokens.mjs` (header comment
explaining why it exists, top-level `await`, `process.exit` with meaningful
codes). Node is chosen over bash because this repository has no shell scripts,
no `jq`, and Node gives three concrete advantages: the token never crosses a
command line at all (no `curl -K` file-descriptor trick needed — `fetch` takes
the header from memory), `JSON.parse` replaces the `jq` dependency, and the
comparison is ordinary code the repository's own test runner can drive.

Structure, in the order the script runs:

1. **Argument parsing.** `""` -> apply, `--dry-run`, `--check`, `-h`/`--help`.
   Anything else, or more than one argument, prints usage to stderr and exits 2
   — with `-h`/`--help` matched *before* the arity check, so `--help extra`
   prints usage to stdout and exits 0. That ordering is not an oversight to
   correct: it is what both reference scripts landed with, pinned as one of the
   three deviations in mctlhq/mctl-telegram#635, and the three upstreams move
   together or not at all. The usage text and the header comment name all four
   modes and the exit-code table, as the reference's does, including the
   missing-interpreter exception below.
2. **Credentials.** `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` must be
   set; missing either is a refusal naming the variable, before any network
   call.
3. **Git guards**, in the reference's order and with its messages, all via
   `git -C <repoRoot>` through `node:child_process` `execFileSync`:
   `rev-parse --git-dir` (is a checkout), `ls-files --error-unmatch --
   docs/portal-allowlist.json` (`is not tracked` — checked first, because
   `git diff HEAD -- <path>` says nothing about a path HEAD does not have),
   then `diff --quiet HEAD -- docs/portal-allowlist.json` (`differs from HEAD`,
   HEAD rather than the index so a staged edit is refused too).
4. **The vetted blob.** `git show HEAD:docs/portal-allowlist.json` is parsed
   once into `vetted`, and every later step reads only `vetted`. Nothing
   re-reads the working tree, which is what closes the window in which the
   guard test (step 6, which runs repository code) could rewrite the file
   between the comparison and the `PUT`.
5. **Portal/server pin.** `vetted.portal === "mcp" && vetted.server ===
   "seerrsense"`, else refuse with `docs/portal-allowlist.json targets
   portal=<p> server=<s>; expected mcp/seerrsense`. Pinned here as well as in
   the guard test, because this is the side that writes.
6. **The guard test.** Spawn the local vitest binary
   (`node_modules/.bin/vitest`, resolved relative to the repository root)
   as `run tests/portal-allowlist.test.ts --reporter=json --outputFile
   <tmpfile>`, cwd at the repository root, with `CLOUDFLARE_API_TOKEN` and
   `CLOUDFLARE_ACCOUNT_ID` deleted from the child environment and
   `SEERR_API_KEY` / `SEERRSENSE_AUTH_TOKEN` / `LOG_LEVEL` set the way
   `package.json`'s `test` script sets them. A missing binary is a refusal that
   says to run `npm ci`; the same class of refusal as the reference's "go is not
   installed here". The JSON report is then required to show
   `numFailedTests === 0`, `numPassedTests > 0`, and
   `tests/portal-allowlist.test.ts` among the reported files — positive
   evidence, the analogue of the reference's `grep '^--- PASS:'`, because "the
   process exited 0" is also what a renamed or deleted test file could produce
   under some invocations. An unrecognised report shape fails closed. On any
   failure the captured stdout/stderr is printed, so an operator being refused
   is told which tool is undecided.
   The `--outputFile` temp file is created with `mkdtemp` under the OS temp
   directory and removed afterwards, so nothing is written inside the checkout.
7. **Reads.** `GET {base}/portals/mcp` and `GET {base}/servers/seerrsense`,
   where `base` is
   `https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/access/ai-controls/mcp`.
   `Authorization: Bearer` comes from the in-process variable. Each envelope
   must have `success === true`, else refuse with exit 1 naming the call
   (`read portal failed: ...`, `read server failed: ...`). The portal must carry
   exactly one mapping with `server_id === "seerrsense"` (`expected exactly
   one`), and `result.tools` on the server read must be non-empty (else: has it
   connected?).
8. **The body.** Deep-copy `result`, delete `created_at`, `created_by`,
   `modified_at`, `modified_by`, and map over `servers`, rewriting only the
   `seerrsense` element: `default_disabled = vetted.default_disabled` and
   `updated_tools = vetted.tools.filter(synced).map(t => ({name: t.name,
   enabled: t.enabled === true}))`. Only synced tools go in (the API rejects an
   unseen name with error 7001), and `enabled` is always a boolean, never
   `null`. Every other field and every other server element goes back out as it
   came in, so a field Cloudflare adds later survives an apply.
9. **Uncovered synced tools.** Synced-minus-listed is a refusal in apply and
   `--dry-run` (exit 1, listing them, with the "the portal may not have
   re-synced yet; do not add them back to the file" hint, since the guard test
   rejects entries for unregistered tools). In `--check` the same set becomes
   drift lines instead, so one run reports every category of disagreement:
   refusing there would be protecting a write `--check` never makes.
10. **`--check`.** The expected side is the `seerrsense` element of the body
    built in step 8 — read out of the apply's own body, not recomputed, so the
    comparison covers exactly what a `PUT` would write. The actual side is the
    same element straight from the step-7 read, before any rewrite. The
    comparison emits `drift: default_disabled portal=<a> file=<e>` when those
    differ, and for the union of tool names on both sides,
    `drift: <name> portal=<a> file=<e>` where each side's value is
    `Object.hasOwn(entry, "enabled") ? entry.enabled : "absent"` and a missing
    entry is the string `"absent"`. **No defaulting operator appears in this
    function**: `entry.enabled || "absent"` and `entry.enabled ?? "absent"` are
    exactly the JavaScript forms of the `jq //` bug that once reported a
    matching baseline as drifted — `||` collapses a real `false`, and while `??`
    does not, using it here invites the wrong one on the next edit. A helper
    `sentinel(side, name)` with explicit `hasOwn` checks is the only reader of
    those values. Drift lines are printed to stdout in a stable order
    (`default_disabled` first, then tool names sorted with `localeCompare` under
    a fixed locale-independent comparison), the count goes to stderr as
    `<n> difference(s) between the portal and docs/portal-allowlist.json`, and
    the exit code is 3. With no drift: `in sync: default_disabled=<bool>
    tools=<n> enabled=<names joined by comma>`, plus `held back (not synced by
    the server): <names>` when the file decides a tool the portal has not
    synced, and exit 0.
11. **`--dry-run`** prints the body as indented JSON and exits 0.
12. **Apply** `PUT`s the body to `{base}/portals/mcp`, requires
    `success === true`, then verifies that the response's `updated_tools` for
    `seerrsense`, projected to `{name, enabled}` and sorted by name, equal what
    was sent; a mismatch or a missing mapping is exit 1 with "verify the portal
    by hand". On success it prints `applied: default_disabled=<bool>
    tools=<n> enabled=<names>`.

Testability without touching Cloudflare: the base URL may be overridden by
`SEERRSENSE_PORTAL_API_BASE`, **honoured only when it parses as a URL whose
hostname is `127.0.0.1`, `::1` or `localhost`**; anything else is exit 2 with a
message saying the override is loopback-only. That keeps the one hatch the tests
need from being a way to point an operator's token at another host.

### 2. `scripts/portal-allowlist-apply.sh` — the uniform entry point

Ten lines of bash: resolve its own directory, refuse with exit 2 and a message
naming Node if `command -v node` fails, then `exec node
"$dir/portal-allowlist-apply.mjs" "$@"`. `exec` preserves argv and the child's
exit code, so every code in the contract passes through untouched. Exit 2 for
the missing interpreter rather than the table's 1 is deliberate: a missing `jq`
exits 2 in both reference scripts, and a missing interpreter is the same
condition. #1211 reads a non-zero, non-3 status as "could not check" either way,
so the choice costs that job nothing and saves it from special-casing one
upstream. It is the third deviation pinned by mctlhq/mctl-telegram#635, and it
is written next to the exit-code table in the header, `--help` and README so a
reader meets the exception where they meet the rule. This is what
lets mctlhq/mctl-gitops#1211 run the identical
`scripts/portal-allowlist-apply.sh --check` in all three upstreams while the
implementation here stays repository-native. `npm run portal:allowlist --
--check` is added as the local ergonomic alias, next to `sync:tokens` /
`check:tokens`.

### 3. `tests/portal-allowlist-apply.test.ts` — the proof

A vitest suite that spawns the command, mirroring
`scripts/portal_allowlist_apply_test.go` case for case. It proves behaviour, not
source, because that is what the reference issue asked for.

Harness: a per-case fixture repository under `mkdtemp` containing
`scripts/` (a copy — or a symlink — of the two scripts), `docs/portal-
allowlist.json` (a small fixture: two tools, one enabled read, one disabled
write), `tests/portal-allowlist.test.ts` (a fixture guard the case controls),
`package.json`, and a symlink to the real repository's `node_modules` so the
fixture's vitest binary resolves without a second install. `git init`, commit,
then mutate per case. A `node:http` server on loopback stands in for the
Cloudflare API: it serves a per-case portal envelope for
`GET /portals/mcp`, a fixed synced-tools envelope for `GET /servers/...`,
appends every request (method, path, body) to a log array, and answers any `PUT`
with a `success:false` "unexpected write" envelope so a stray write is loud as
well as recorded. `SEERRSENSE_PORTAL_API_BASE` points at it.

Cases (the numbering is the reference's, adapted):

- green: matching portal -> exit 0 and the `in sync: ...` line;
- red: the same body with exactly one tool's `enabled` flipped -> exit 3 and
  `drift: <tool> portal=true file=false`;
- `default_disabled` differing -> exit 3 and its drift line;
- a tool live but not in the file -> `file=absent`; a tool in the file the
  portal dropped -> `portal=absent`;
- a synced tool with no decision -> the `synced by the server with no decision`
  drift line, with the other tool still evaluated in the same run;
- a file entry for an unsynced tool -> exit 0 plus `held back`;
- inherited guards: uncommitted edit, staged-only edit, file untracked but on
  disk, a file naming another portal/server, a missing vitest binary, a failing
  fixture guard — each exit 1 with the reference's message fragment and an
  **empty request log**;
- a nested guard that rewrites the file on disk and then passes -> the body
  still carries the committed decision (the TOCTOU case);
- a guard that fails when it can see `CLOUDFLARE_API_TOKEN` -> passes, proving
  the credential is stripped;
- API failures: `success:false` and a portal with no `seerrsense` mapping ->
  exit 1, not 3;
- usage: no-argument-plus-extra and an unknown flag -> exit 2; `--help extra` ->
  exit 0, pinning the help-first ordering; `--help` -> exit
  0 and mentions `--check`;
- a non-loopback `SEERRSENSE_PORTAL_API_BASE` -> exit 2, empty request log.

Every `--check` and `--dry-run` case additionally asserts the request log
contains no `PUT`. The suite skips (rather than fails) when `git` is not on
`PATH`, as the reference skips on Windows and on a missing toolchain.

### 4. Documentation

- `docs/portal-allowlist.json`'s `$comment` is updated to name this
  repository's own script instead of pointing at mctl-telegram's, and to
  mention `--check`. This is a comment-only edit to the file; no decision moves.
  Note the ordering consequence: the edit must be committed before it can be
  applied, which is exactly the guard working as intended.
- `README.md` gains a short operator subsection under the existing portal
  material: the two environment variables, the four modes, the exit-code table
  with the missing-interpreter-exits-2 exception stated next to it, and the
  `npm ci` prerequisite.

## Alternatives

1. **A literal bash port of `scripts/portal-allowlist-apply.sh` with `jq`**,
   the way mctl-api#300 will mirror it. Dropped: it would be the first shell
   script and the first `jq` dependency in a repository whose only operator
   script is Node, it needs the `curl -K <(...)` process-substitution dance to
   keep the token off the command line where `fetch` simply does not have the
   problem, and its test would have to be a second harness style (stub `curl`
   on `PATH`) rather than the repository's own runner. The issue explicitly
   permits a repository-native command; the wrapper preserves the uniform call
   site that the shell version would have bought. It remains the cheapest
   fallback if a reviewer wants byte-level parity across the three upstreams.
2. **A vitest test that performs the check** (`portal-drift.test.ts`, skipped
   unless the Cloudflare variables are present), instead of a script. Dropped:
   a test cannot have an apply mode, it cannot distinguish "could not check"
   (1) from "drift" (3) in an exit code, and #1211 wants one command with a
   three-way status, not a parse of vitest output. It also puts a production
   credential into the same runner that executes the whole suite.
3. **Reuse `scripts/sync-tokens.mjs`'s pattern of a single `--check` exit code
   1** and drop the 0/1/2/3 split. Dropped: #1211 must distinguish "the check
   could not run" from "the portal has drifted" to know whether the red light
   means fix the config or fix the job, and the two sibling upstreams already
   exit 3 for drift. Matching them is the whole point of the sequencing note in
   the issue.
4. **Let the guard command be injected by an environment variable** so the test
   harness can substitute a cheap stub. Dropped: that is a documented bypass of
   the one check standing between an unreviewed file and a shared surface.
   Symlinking `node_modules` into the fixture costs the harness a line and keeps
   the guard un-bypassable.

## Platform impact

- **Migrations:** none. No schema, no service, no deployment. The API surface of
  `seerrsense` itself does not change; `src/` is untouched.
- **Backward compatibility:** additive. `npm test`, `npm run typecheck`, the
  Docker build and every existing workflow keep working; the new test file is
  picked up by `npm test` automatically (no `vitest.config.ts` exists — tests are
  discovered under `tests/`), and by `tests/source-hygiene.test.ts`'s control-
  character scan, which already covers every `.ts` file under `tests/`.
- **CI cost:** the new suite spawns several short-lived vitest runs inside
  fixtures (the fixture guard is a one-file test), plus a loopback HTTP server
  per case. Expect the slowest addition in the suite, in the tens of seconds.
  Mitigation: keep the fixture guard trivial, run the cases with vitest's
  default concurrency (the reference test is `t.Parallel()` for the same
  reason), and give the spawns an explicit timeout so a hung child fails a case
  rather than the job.
- **Risk: a wrong apply changes what a shared surface exposes.** Mitigated by
  the guards inherited wholesale from the reference (committed-and-equal-to-HEAD,
  the guard test passing, the portal/server pin, the `HEAD` blob as the only
  source, the post-`PUT` readback verification), and by `--dry-run` being the
  documented first step.
- **Risk: a detector that can only go green.** Mitigated by the mutation proof
  being a review gate (requirements name it; `tasks.md` records the fixtures),
  and by the design forbidding defaulting operators in the comparison — the
  named repeat of the `jq //` bug this repository would otherwise be free to
  reinvent.
- **Risk: the loopback-only base-URL override becomes an exfiltration path.**
  Mitigated by the hostname allowlist (`127.0.0.1`, `::1`, `localhost`) and by
  the refusal being exit 2 rather than a silent fallback; an attacker who can
  set environment variables in an operator's shell already has the token.
- **Risk: credential leakage in logs.** The token is never an argument, never
  interpolated into a message, and is removed from the guard test's environment;
  the tests assert the latter by making the fixture guard fail if it can see it.
- **Resource impact on the platform:** two `GET`s and at most one `PUT` per run
  against the Cloudflare API. `--check` is read-only and safe on a schedule,
  which is what #1211 needs.
- **Sequencing:** mctl-telegram#632 is merged, so the reference exists and this
  proposal copies rather than invents. mctlhq/mctl-gitops#1211 stays blocked
  until this and mctl-api#300 land; nothing here assumes #1211's shape beyond
  the uniform `scripts/portal-allowlist-apply.sh --check` entry point and the
  `npm ci` prerequisite recorded as an open question.
