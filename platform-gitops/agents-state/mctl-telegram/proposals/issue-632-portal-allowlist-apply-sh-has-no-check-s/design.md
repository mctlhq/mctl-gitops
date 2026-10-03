# Design: issue-632-portal-allowlist-apply-sh-has-no-check-s

## Current state

**The decision file.** `docs/portal-allowlist.json` holds `portal: "mcp"`,
`server: "tg"`, `default_disabled: true` and a `tools` array of
`{name, enabled, reason?}` — 30 entries today, three of them enabled
(`get_my_identity`, `get_my_send_status`, `list_dialogs`).

**The repository-side guard.** `internal/mcp/portal_allowlist_test.go`
(`TestPortalAllowlist_CoversEveryRegisteredTool`) parses the file into
`portalAllowlist`, where `Enabled` is a `*bool` so a missing key is a failure
rather than a silent `false`. It asserts the file targets `mcp`/`tg`, that
`default_disabled` is true, that the set of names equals the set of tools
`(&Server{ToolFilter: ""}).newMCPServer().ListTools()` registers in both
directions, and that an enabled tool carries `readOnlyHint=true` plus a
`reason` of at least `minReasonLen` (40) characters. This guard says nothing
about Cloudflare; it gates the repository.

**The apply script.** `scripts/portal-allowlist-apply.sh` (158 lines, bash,
`set -euo pipefail`) is the only thing that talks to Cloudflare. Its shape:

1. Argument parsing — a `case` on `${1:-}` accepting only `""` and
   `--dry-run`, anything else printing usage and `exit 2` (lines 27-32).
   There is no `--help`.
2. Pre-flight, in a deliberate order (lines 34-86): `CLOUDFLARE_API_TOKEN` and
   `CLOUDFLARE_ACCOUNT_ID` must be set, `jq` must exist; the tree must be a git
   checkout; the file must be *tracked* (`git ls-files --error-unmatch`) before
   it is compared, because `git diff HEAD -- <path>` exits 0 for a path `HEAD`
   does not have; it must be identical to `HEAD` (`git diff --quiet HEAD --`,
   not the index-relative form); `vetted=$(git show HEAD:docs/portal-allowlist.json)`
   is the blob everything downstream uses, closing the TOCTOU window against
   the guard test that runs next; the blob's own `portal`/`server` must read
   `mcp`/`tg`; `go` must exist; and the guard test must both exit 0 *and* print
   `--- PASS: TestPortalAllowlist_CoversEveryRegisteredTool`, because
   `go test -run` exits 0 when its pattern matches nothing. The guard runs with
   `env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID`.
3. HTTP helpers (lines 88-98): `cf()` invokes `curl -sS -K <(...)` so the
   bearer token is passed over a file descriptor and never appears on a command
   line; `must_succeed` fails the run unless the envelope has `.success`.
4. Reads (lines 100-124): `GET $base/portals/mcp` into `current`, `GET
   $base/servers/tg` into `server_body`. Exactly one `tg` mapping must exist.
   `synced` is `.result.tools[].name` from the server, sorted under `LC_ALL=C`;
   an empty set is a hard error. Every synced tool must have a decision in the
   file (`comm -23 synced listed`), or the script refuses — this is the drift
   *within the repository*, and it aborts before any write.
5. Body construction (lines 132-141): `body` is `.result` from the live portal,
   minus the four timestamps, with only the `tg` element rewritten:
   `default_disabled` from the file and `updated_tools` set to
   `[{name, enabled: (.enabled // false)}]` for file entries the server has
   synced. Entries for unsynced tools are held back because the API rejects an
   unknown name (error 7001).
6. `--dry-run` prints that body and exits 0 (line 143). Otherwise the script
   captures `sent` (the sorted `{name, enabled}` projection), `PUT`s the body,
   and asserts the response's `updated_tools` equal `sent` before printing the
   `applied:` summary (lines 147-157).

**The script's own test.** `scripts/portal_allowlist_apply_test.go` (package
`scripts`, so `go test -race ./...` in `.github/workflows/build.yml` runs it)
builds a throwaway checkout per case with `newFixture`: the real script copied
in, a `go.mod`, a synthesised `internal/mcp/guard_test.go` whose name and body
the case controls, a committed two-tool allowlist from `writeAllowlist`
(`get_my_send_status` enabled, `send_message` disabled), and a `stub/curl`
shell script placed first on `PATH`. Every case runs `--dry-run`, hardcoded at
line 136. `stubCurl` answers `*/servers/*` and `*/portals/*` with fixed
envelopes and never records anything; it does not distinguish a `PUT` from a
`GET`, so a `PUT` to `/portals/mcp` would currently be answered as a successful
read. Eleven cases cover the positive path and each refusal.

**The operator documentation.** `docs/cloudflare-portal-compat.md`, section
"Portal tool allowlist — the drift guard" (lines 139-150), is the written
record of the apply procedure and lists the two commands an operator runs.
`grep` shows the script is referenced from exactly that document, the JSON
file, and its own test — nothing else, and no workflow invokes it (CI holds no
Cloudflare credential by design, #1111).

**The gap.** Every one of those mechanisms points outward. Nothing reads the
portal and compares. With mctlhq/mctl-gitops#1092 deciding that the OpenTofu
import will not declare `servers`, there is no second place where per-tool
drift could be noticed.

## Proposed solution

Add a third mode to the existing script rather than a second script. The
pre-flight, the credential handling, the `cf`/`must_succeed` helpers and the
projection of the file into portal shape are precisely what a detector needs,
and a separate script would either duplicate them or drift from them — which
would be an ironic failure mode for a drift detector.

### 1. Mode selection (replaces lines 27-32)

```
mode=apply
case "${1:-}" in
  "")          mode=apply ;;
  --dry-run)   mode=dry-run ;;
  --check)     mode=check ;;
  -h|--help)   usage; exit 0 ;;
  *) usage "unknown argument: $1" >&2; exit 2 ;;
esac
```

`usage` becomes a function printing all three modes and their exit codes, used
for `--help` (stdout, exit 0) and for the error path (stderr, exit 2). The
`[ $# -le 1 ]` arity check is kept. The header comment (lines 1-24) gains a
paragraph describing `--check`: what it compares, that it never writes, and
that it is held to the same guards.

### 2. Guards apply unchanged

Nothing in steps 2-4 of the current flow is made conditional on the mode. A
`--check` run that cannot verify the file is refused with today's messages and
today's exit 1, because a check against an unreviewed file answers a question
nobody asked. This is free: the code already runs before any branch on
`dry_run`.

### 3. The uncovered-synced-tools block becomes mode-aware (lines 118-124)

In `apply`/`dry-run` the early refusal stays exactly as it is — it protects a
write. In `check` the same `uncovered` list is captured into a drift
accumulator and the run continues, so a single check reports everything it
found instead of stopping at the first category. The "server returned no synced
tools" condition (line 116) stays a hard `exit 1` in every mode: that is
"nothing was measured", not "drift was measured".

### 4. The comparison reuses the apply's own body construction

`body` (lines 132-141) is already "the live portal document with the `tg`
mapping rewritten to what the file says". So the expected value is not
recomputed: after `body` is built, `--check` extracts the `tg` mapping from
`body` (expected) and from `current` (actual) and diffs the two fields the
apply owns.

```
expected=$(jq -c --arg s "$server" '[.servers[]|select(.server_id==$s)][0]' <<<"$body")
actual=$(jq  -c --arg s "$server" '[.result.servers[]|select(.server_id==$s)][0]' <<<"$current")
```

This makes the comparison definitionally cover "what the apply writes" — the
property the issue asks for — and it cannot fall out of step with the apply,
because it *is* the apply's own body.

The diff is one jq program over the two documents, emitting one text line per
difference:

- `default_disabled`: compared with `==` on the raw values.
- tools: the union of names from `expected.updated_tools` and
  `actual.updated_tools`; for each name, a side's value is the literal
  `enabled` when the entry exists and has the key, and the string `absent`
  when the entry is missing or the key is not there. A row is emitted when the
  two sides are not `==`.

Two rules are load-bearing here, and both get a comment in the script:

- **No `//` anywhere in this path.** jq's `//` substitutes on `false` as well
  as on `null`. `mctl-gitops/scripts/portal-controls-apply.sh` carries the bug
  report: a comparison written with `//` reported the committed baseline as
  drifted against itself. Missing values are produced with `has("enabled")`
  and an explicit `absent` sentinel, never with a default.
- **`absent` is not `false`.** A tool the portal has dropped from
  `updated_tools` and a tool the portal has disabled are different facts, and
  `default_disabled: true` means they can even have the same effect today —
  which is exactly why collapsing them would let a real change go unreported.

Report lines are stable and greppable, so #1211 can key on them:

```
drift: default_disabled portal=false file=true
drift: send_message portal=true file=false
drift: list_dialogs portal=absent file=true
drift: legacy_tool portal=false file=absent
drift: some_tool synced by the server with no decision in docs/portal-allowlist.json
```

### 5. Result and exit codes

`--check` returns before line 143, so no code path in this mode reaches the
`PUT` at line 148. There is exactly one `PUT` in the script and the check mode
exits above it.

- In sync: one line on stdout, mirroring the `applied:` summary shape —
  `in sync: default_disabled=true tools=30 enabled=get_my_identity,get_my_send_status,list_dialogs`
  — plus, when the file decides tools the server has not synced, a second line
  `held back (not synced by the server): <names>`. Exit 0.
- Drift: the `drift:` lines on stdout, a `N difference(s) between the portal
  and docs/portal-allowlist.json` line on stderr, exit **3**.
- Could not check (guard refusal, API error, missing mapping, no synced
  tools): today's messages, exit **1**.
- Usage: exit **2**.

Three codes rather than two because the consumer is a scheduled CI job:
"a tool was flipped" and "the token expired" need different reactions.
`cmd/mcpprobe` sets the precedent in this repository, and
`docs/cloudflare-portal-compat.md` argues for it explicitly ("code 3 is the one
to watch ... a pipeline reading only 'not 1' would call that a pass"). The
issue requires only non-zero, so this is compatible either way.

### 6. Proving it, in `scripts/portal_allowlist_apply_test.go`

The test file is where this script's behaviour is proven, and the issue
requires the no-write property to be proven by observation rather than by
reading the code. Three changes to the harness:

- **The case gains `args []string`**, defaulting to `{"--dry-run"}`, replacing
  the hardcoded flag at line 136. Existing cases are untouched.
- **`stubCurl` learns to record and to refuse writes.** It appends one line per
  invocation (`method<TAB>url`) to `$STUB_CURL_LOG`, and answers any invocation
  carrying `-X PUT` with `{"success":false,...}` naming the unexpected write,
  so a stray `PUT` both fails the run and leaves evidence. It serves the portal
  body from `$STUB_PORTAL_BODY` when that file exists and its current constant
  otherwise, which is how a case makes the live portal match or differ.
- **A `wantCode int` field**, so a case can assert exit 3 rather than merely
  "non-zero" (`exec.ExitError.ExitCode()`).

The mutation proof is then a pair of cases over one fixture, differing in one
field of the stubbed portal body, which is what the issue asks to see in the
PR: green with `updated_tools` `[{get_my_send_status,true},{send_message,false}]`
and `default_disabled: true`; red with `send_message` at `true` and nothing else
changed. Every `--check` case additionally asserts the call log contains no
`PUT`.

### 7. Documentation

`docs/cloudflare-portal-compat.md` gains `--check` to the command block in the
"drift guard" section and a short paragraph: what it compares, that the guards
apply, the exit codes, that it never writes, and that the CI job which will run
it is mctlhq/mctl-gitops#1211 and is not part of this change. The script's
header comment (lines 1-24) and `usage` describe the mode, as the issue
requires.

## Alternatives

**A separate `scripts/portal-allowlist-check.sh`.** Cleanly separates a
read-only tool from a writing one, and makes "this script never writes" a
property of the file rather than of a branch. Dropped because it would have to
copy the entire 60-line pre-flight, the `cf`/`must_succeed` helpers and — worst
— the projection of the file into portal shape. Two copies of that projection
is two things that can disagree, and the disagreement would be invisible in
exactly the way this issue is about. The no-write property is instead proven by
the recorded call log, which is stronger than a structural argument because it
observes the run.

**A Go detector in `internal/mcp` or a new `cmd/portalcheck`.** Tempting in a Go
repository: typed comparison, no jq, testable without a shell fixture. Dropped
because the pre-flight this must inherit is git-shaped shell that already
exists and is already tested, because the operator procedure in
`docs/cloudflare-portal-compat.md` is written around the script, and because
the sibling implementation the issue names as the model
(`mctl-gitops/scripts/portal-controls-apply.sh --check`) is a shell script —
mctl-api#300 and seerrsense#70 are asked to follow this repository's shape, and
seerrsense has no Go module to put a detector in.

**Compare against the raw file rather than against the apply's body.** Simpler
to read: walk `.tools[]` from the vetted blob against `updated_tools` from the
portal. Dropped because it silently re-derives the apply's rules — the
intersection with the synced set, the `enabled` normalisation, the
`default_disabled` source. A detector that encodes a second opinion about what
the apply writes will eventually report drift that an apply would not fix, or
miss drift that it would create.

**Reuse the existing `--dry-run` output and diff it externally** (`diff <(dry-run)
<(GET portal)`). No script change beyond none at all. Dropped because the dry-run
body is the whole portal document including fields the apply does not own; the
diff would be dominated by noise, and the per-tool report the issue requires
would have to be reconstructed by the caller.

## Platform impact

- **Migrations:** none. No schema, no data, no deployment. The change touches
  `scripts/portal-allowlist-apply.sh`, `scripts/portal_allowlist_apply_test.go`
  and `docs/cloudflare-portal-compat.md`. No Go production code changes; no
  server behaviour changes.
- **Backward compatibility:** the default apply and `--dry-run` are
  byte-identical in behaviour. The only pre-existing surface that moves is the
  argument parser, which gains `--check`, `-h` and `--help`; an unknown
  argument still exits 2. No allowlist decision moves, so a `--check` run
  against a portal that an apply last touched must be green — which is itself
  the first manual verification.
- **Resource impact:** two `GET`s per check (the same two the apply already
  makes) plus one `go test -run` of a single guard test. Nothing is scheduled
  by this proposal.
- **Risk: a detector that can only go green.** The named failure mode, and the
  reason jq's `//` is banned from the comparison path. Mitigated by requiring a
  one-field-mutation red case in the test table alongside the green one, by the
  `absent`-vs-`false` sentinel, and by recording both runs in the PR body.
- **Risk: an accidental write in check mode.** Mitigated structurally (the mode
  returns above the script's single `PUT`) and observationally (the stub curl
  records every call, refuses `-X PUT`, and the `--check` cases assert the log
  holds no `PUT`).
- **Risk: a false positive wakes an operator for nothing.** The two known
  benign asymmetries are handled by design: a file entry for a tool the portal
  has not synced is held back by the apply and so is not drift (it is named in
  the summary), and fields of the live document the apply does not write are
  not compared. Remaining false-positive sources are genuine Cloudflare
  behaviour changes, which an operator should hear about.
- **Risk: the guards make `--check` unusable where it would be most wanted**
  (a host without `go`, a detached copy of the script). Accepted, because the
  issue states the guards apply; the consumer in #1211 runs from a checkout
  with Go, exactly as the `test` job in `.github/workflows/build.yml` does.
- **Exit-code contract:** 0 in sync, 1 could not check, 2 usage, 3 drift. It is
  new surface that mctlhq/mctl-gitops#1211 will depend on; it is documented in
  the script header, in `--help` and in `docs/cloudflare-portal-compat.md` so
  the downstream issue has something to key on.
- **Downstreams:** mctlhq/mctl-api#300 mirrors this change and seerrsense#70
  needs an apply script first. Neither is touched here; this lands as the
  reference shape.
