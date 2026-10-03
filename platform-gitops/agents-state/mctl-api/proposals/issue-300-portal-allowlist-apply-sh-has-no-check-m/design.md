# Design: issue-300-portal-allowlist-apply-sh-has-no-check-m

## Current state

**The source of truth.** `docs/portal-allowlist.json` (378 lines) carries
`portal: "mcp"`, `server: "api"`, `default_disabled: true` and a `tools` array
of 74 entries, every one currently `"enabled": true` with a `reason` (all
enabled since PR #297, merge `31135f4`).

**The guard test.** `internal/mcp/portal_allowlist_test.go` holds the file
honest against the running server:
`TestPortalAllowlist_CoversEveryRegisteredTool` compares the file's names
against `NewServer(...).NewMCPServer().ListTools()` and `recordedHints` from
`internal/mcp/annotations_test.go`, requires `default_disabled` true, requires a
tool-specific `reason` of at least `minReasonLen` characters beyond the shared
provenance sentence on every enabled tool, and requires every enabled tool that
is not `readOnly` to be named in the `mutatingOnPortal` map. It never talks to
Cloudflare.

**The apply script.** `scripts/portal-allowlist-apply.sh` (132 lines) is the
only thing that writes to the portal. Today it:

- accepts `""` or `--dry-run` only; anything else exits 2 with a one-line usage
  (lines 30-35), and there is no `-h`/`--help`;
- requires `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` and `jq`;
- refuses when `git diff --quiet HEAD -- docs/portal-allowlist.json` reports a
  difference (line 53), then pins `portal=mcp`/`server=api` (line 56) reading
  those keys from the **on-disk** file (line 43);
- runs the guard test with
  `go test ./internal/mcp/ -run 'TestPortalAllowlist_CoversEveryRegisteredTool' -count=1 >/dev/null`
  (line 58) and refuses when `go` is absent (line 61);
- reads the portal (`GET /portals/mcp`) and the server (`GET /servers/api`)
  through `cf()`, which hands the bearer token to curl over a file descriptor
  (line 66), and asserts `success` via `must_succeed()`;
- requires exactly one mapping for `api` (lines 81-82), requires every synced
  tool to have a decision in the file (subset, not equality — lines 89-98, and
  a synced tool with no decision is an immediate refusal);
- builds the PUT body from the GET body minus the four timestamps, rewriting
  only the `api` element's `default_disabled` and `updated_tools`, where
  `updated_tools` is `{name, enabled}` restricted to tools the server has
  synced (lines 106-115);
- on `--dry-run` prints that body and exits; otherwise PUTs it and verifies the
  response's `updated_tools` equals what was sent (lines 117-131).

There is no read-back mode. `--dry-run` prints what *would* be written; it
never says whether the portal already agrees.

**What is missing relative to the reference.** mctlhq/mctl-telegram#632 landed
as mctlhq/mctl-telegram#634. Its script has `--check`, `-h/--help` and a
`usage()` block, and it also carries pre-flight hardening this repository's copy
does not have: a `git rev-parse --git-dir` checkout test, a
`git ls-files --error-unmatch` tracked test (`git diff HEAD -- <path>` exits 0
for a path `HEAD` does not have, so an untracked-but-present file passes the
check this repository relies on), reading the decisions from
`git show HEAD:docs/portal-allowlist.json` instead of the on-disk copy (closing
the window between the `diff HEAD` check and the body build — the guard test
itself runs in that window and could rewrite the file), an anchored
`-run '^Test…$'` plus a `grep -q '^--- PASS: …'` assertion (`go test -run`
exits 0 when the pattern matches nothing, so a renamed or deleted guard reads
as a pass), and `env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID` around
the guard-test run.

**Test and CI shape.** `scripts/` in this repository holds only the `.sh` —
there is no shell-script test harness of any kind, and no `bats`/`shellcheck`
step in `.github/workflows/`. `mctl-telegram` has
`scripts/portal_allowlist_apply_test.go` (641 lines, `package scripts`) which
drives the script against throwaway checkouts with a stub `curl` on `PATH`.
`.github/workflows/validate.yml` runs `go build ./...` and `go test -p 1 ./...`
on `ubuntu-latest` (git, bash, jq, curl and Go all present), plus
`golangci-lint` v2.11.4 with the config in `.golangci.yml`. The module is
`github.com/mctlhq/mctl-api`, Go 1.26.6. `README.md` lines 386-397 ("Portal tool
allowlist") is where the apply and `--dry-run` are documented for operators;
this repository has no `docs/cloudflare-portal-compat.md`.

## Proposed solution

Port mctlhq/mctl-telegram#634 into this repository, substituting the server id
`api` for `tg`, and keeping every user-visible string, flag and exit code
identical so mctlhq/mctl-gitops#1211 can drive both with one code path. Three
files change; nothing in `internal/`, no tool set change, no allowlist decision
change.

### 1. `scripts/portal-allowlist-apply.sh`

**Mode dispatch and usage.** Replace the two-way `case` with
`mode=apply|dry-run|check`, add `-h|--help` printing a `usage()` heredoc that
names all three modes and the exit-code table, and route the unknown-argument
and too-many-arguments paths through `usage >&2` + exit 2 -- with the one
mirrored exception that `-h|--help` is matched before the arity guard, so
`--help extra` prints usage and exits 0 rather than 2. Usage is answered
before credentials, `jq`, git or Go are touched.

**Pre-flight parity (applies to all three modes).** Bring over the hardening
listed above in the reference's order: `rev-parse --git-dir` → `ls-files
--error-unmatch` → `diff --quiet HEAD` → `vetted=$(git show
HEAD:docs/portal-allowlist.json)` → `portal`/`server` pin read from `$vetted`
→ `command -v go` → guard test with `-v`, an anchored `-run
'^TestPortalAllowlist_CoversEveryRegisteredTool$'`, `env -u` on both Cloudflare
variables, and a `grep -q '^--- PASS: …'` assertion whose failure prints the
captured test output. Downstream, `--slurpfile a "$file"` / `$a[0]` becomes
`--argjson a "$vetted"` / `$a`, and `jq -r '.tools[].name' "$file"` reads
`<<<"$vetted"`. A check run against an unreviewed file answers a question
nobody asked, so `--check` gets exactly these guards and no exemption.

**The comparison.** `--check` branches *after* `$body` — the apply's own PUT
body — has been built, and compares:

- `expected` = `[.servers[] | select(.server_id=="api")][0]` out of `$body`;
- `actual` = `[.result.servers[] | select(.server_id=="api")][0]` out of the
  untouched portal GET.

Deriving `expected` from the apply's body rather than recomputing it from the
file is the load-bearing choice: the check then covers exactly what a PUT would
write and cannot fall out of step with the apply's own rules (notably that
tools the server has not synced are held back from `updated_tools`).

The jq comparison emits one line per disagreement:
`drift: default_disabled portal=<live> file=<committed>` and
`drift: <tool> portal=<live|absent> file=<committed|absent>` over the union of
tool names on both sides. Every default is built with `has()` and an explicit
conditional — never jq's `//`, which substitutes on `false` as well as `null`
and previously made `mctl-gitops/scripts/portal-controls-apply.sh` report its
own committed baseline as drifted. With 74 committed decisions that are all
`true` today and a `default_disabled` of `true`, a `//`-based comparison would
look correct here and silently break the first time a tool is disabled.

**Uncovered tools.** The existing "synced tool with no decision" refusal
(lines 93-98) stays a hard refusal for apply and `--dry-run`, because it
protects a write; under `--check` it is folded into a drift accumulator
(`drift: <tool> synced by the server with no decision in
docs/portal-allowlist.json`) so one run reports every category at once instead
of stopping at the first.

**Output and exit codes.** Drift lines print on stdout, the
`<n> difference(s) …` count on stderr, exit 3. Agreement prints
`in sync: default_disabled=… tools=… enabled=…` — the same projection the
apply's `applied:` line uses, guarded by `select(. != null)` so a missing
mapping cannot print an empty success — and, when the file decides tools the
server has not synced, a `held back (not synced by the server): …` line, then
exit 0. Exit codes: `0` in sync/applied, `1` could not check or apply (guard
refusal or API failure), `2` usage error, `3` drift -- with one documented
exception carried over from the reference: a missing `jq` exits 2, not 1. `1`
and `3` are both failures; the split says which happened, and the header
comment, `--help` and `README.md` all say so explicitly -- and all three carry
the missing-`jq` exception too, so that they are not misleading on the one host
where it shows (tracked in mctlhq/mctl-telegram#635, to move in both
repositories at once) -- because a caller that alerts on `3` alone would read
an expired token as "no drift".

**No write.** `--check` returns before the `sent=`/`PUT` block on every path,
including the drift path. This is asserted by observation (below), not by
reading the code.

### 2. `scripts/portal_allowlist_apply_test.go` (new, `package scripts`)

This repository has no harness for the script, so the reference's is ported
whole. It builds a throwaway checkout per case in `t.TempDir()`: the real
script copied from `scripts/`, a `module fixture` `go.mod` at the repository's
Go version, a synthetic `internal/mcp/guard_test.go` whose test name and body
the case controls, a committed two-tool `docs/portal-allowlist.json` naming
`mcp`/`api` (fixture tools: one enabled read-only-ish name such as
`mctl_whoami`, one disabled such as `mctl_delete_tenant`), and a `stub/`
directory prepended to `PATH` containing a stub `curl`.

The stub `curl` records `method<TAB>url` to `$STUB_CURL_LOG` for every
invocation, answers `GET /servers/api` with a canned synced-tool list, answers
`GET /portals/mcp` from `$STUB_PORTAL_BODY` when set (so a case can make the
live portal agree with or differ from the fixture by exactly one field), and
answers any `PUT` with an unsuccessful envelope naming the unexpected write —
so a stray write both fails the run and leaves evidence. The no-`PUT` assertion
is gated on the log being readable and containing the expected `GET` lines, so
a stub that stopped recording cannot silently make the guarantee vacuous.

Cases skip on Windows and when `git`, `jq`, `go` or `bash` is missing, so the
package is inert on a host that cannot run it. A `nogo` sandbox directory of
symlinks (bash, sh, dirname, git, jq, stub curl — and no `go`) backs the
missing-Go case, rather than trimming `PATH`, which on a shared prefix would
take `git` and `jq` with it and refuse for the wrong reason.

### 3. `README.md`

Extend the "Portal tool allowlist" section (lines 386-397) with the `--check`
invocation, what it compares, the pre-flight parity, the never-writes
guarantee, the held-back rule, and the exit-code table including the explicit
statement that `1` and `3` are both failures and the missing-`jq`-exits-2
exception. Note that CI wiring is
mctlhq/mctl-gitops#1211 and that `--check` is operator-run today.

## Alternatives

1. **Write the drift detector in Go (a `cmd/portal-check` or a `go test`
   against the live API) instead of extending the script.** Dropped: the issue
   requires this script and `mctl-telegram`'s not to drift in behaviour, exit
   codes or output format, and mctlhq/mctl-gitops#1211 must parse neither
   specially. A second language on this side would guarantee format drift, and
   it would duplicate the apply's held-back rule — the very thing deriving
   `expected` from `$body` avoids. Go stays where it already is: the guard test
   and the harness that drives the script.

2. **Compare the two mapping objects wholesale (`expected == actual` in jq).**
   Dropped on two counts: the live element carries nested read-only fields the
   apply does not own, so equality would report drift the apply cannot fix; and
   the output would be "they differ", not "`mctl_delete_tenant` is enabled live
   and disabled in the file", which is what the acceptance criteria and an
   operator both need.

3. **Recompute the expected tool set directly from the committed file rather
   than from the apply's `$body`.** Dropped: the apply deliberately restricts
   `updated_tools` to tools the server has synced (a name the API has not seen
   is rejected with error 7001). A separately-computed expectation would report
   every not-yet-synced decision as `portal=absent` drift, and the two
   computations would diverge the next time the apply's projection rule
   changes.

4. **Use `jq`'s `//` for missing `enabled`/`default_disabled` values.**
   Dropped explicitly: `//` substitutes on `false` as well as `null`. That is
   the recorded bug in `mctl-gitops/scripts/portal-controls-apply.sh`, where a
   committed `false` compared as `null != false` and the detector could only go
   red. `has()` plus an explicit `"absent"` sentinel distinguishes "the portal
   has no entry" from "the portal has `enabled: false`", which are different
   findings.

## Platform impact

- **Migrations / API surface:** none. No Go source under `internal/` or `cmd/`
  changes, no route, no tool, no database. `internal/mcp/server_test.go`'s tool
  count expectation is untouched.
- **Backward compatibility:** the default apply and `--dry-run` keep their
  behaviour and exit codes. One intentional behaviour change on those paths:
  they now read the committed blob rather than the on-disk copy, and refuse an
  untracked file and a renamed guard test. Both are refusals of states that
  should never have been applied; a legitimate operator run (clean checkout,
  committed file, guard passing) is unaffected.
- **Resource impact:** `--check` issues the same two GETs the apply already
  does and no PUT. CI grows by one test package that compiles and runs a
  fixture Go module per case; with `go test -p 1 ./...` in
  `.github/workflows/validate.yml` that is roughly one to two extra minutes of
  wall time. Mitigation if that proves unacceptable: the cases are already
  `t.Parallel()` within the package, and the fixture module is
  dependency-free, so no network fetch is involved.
- **Risk: `--check` needs a Cloudflare token, and CI has none**
  (mctlhq/mctl-gitops#1111). Mitigation: it stays operator-run in this change;
  wiring is mctlhq/mctl-gitops#1211, which owns the credential question.
- **Risk: a caller treats exit 1 as "no drift".** An expired token, a revoked
  scope or an API outage would then read as a clean portal. Mitigation: the
  exit-code table in the header, `--help` and `README.md` all state that every
  non-zero status is a failure a caller must surface, and the harness holds
  exit 1 (not 3) for both the unsuccessful-envelope and the missing-mapping
  cases.
- **Risk: the guard test executes repository code during a check.**
  Mitigation (carried over from the reference): the Cloudflare variables are
  removed from its environment with `env -u`, narrowing the obvious path. This
  is not a trust boundary — a checkout you would not trust with a token is one
  you should not build.
- **Risk: the detector can only go one way.** Mitigation: the mutation-proof
  pair (T1 green, T2 red, differing by exactly one field of the same stubbed
  portal body) is a required, permanent test, not a one-off manual
  demonstration.
