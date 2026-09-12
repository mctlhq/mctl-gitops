# Portal allowlist apply/check path for the seerrsense upstream

## Context

`docs/portal-allowlist.json` is the committed decision for which of this
server's MCP tools the Cloudflare MCP portal (`mcp.mctl.ai`, portal `mcp`,
server `seerrsense`) exposes, and `tests/portal-allowlist.test.ts` is the guard
that every tool `createSeerrSenseMcpServer()` registers carries an explicit
decision with a reason, and that an enabled write tool is separately vouched
for. Nothing in this repository writes that decision to Cloudflare, and nothing
reads the live portal back. The file is a statement of intent that no
automation enforces or verifies: a tool flipped in the Cloudflare dashboard, a
half-finished manual change, or a `default_disabled` toggled while debugging is
invisible here.

That gap is now load-bearing. The owner decided on 2026-09-12
(mctlhq/mctl-gitops#1092) that the OpenTofu import of the portal will not
declare the `servers` attribute, so per-tool drift will never appear in
`tofu plan`. For the `seerrsense` upstream there is currently no detection
anywhere. mctlhq/mctl-telegram#632 landed the reference implementation
(`scripts/portal-allowlist-apply.sh` with `--dry-run` and `--check`, plus
`scripts/portal_allowlist_apply_test.go` proving both directions by mutation),
mctlhq/mctl-api#300 mirrors it, and mctlhq/mctl-gitops#1211 will call all three
from one daily job. This proposal supplies the missing third path: an apply and
a `--check` mode for this repository, with the reference's guards, exit codes
and output shape, implemented in this repository's own stack (Node ESM under
`scripts/`, tested with vitest) and reachable under the same
`scripts/portal-allowlist-apply.sh --check` invocation the other two upstreams
expose.

## User stories

- AS the platform owner I WANT `docs/portal-allowlist.json` to be applied to
  the Cloudflare portal by a scripted, guarded path SO THAT what a shared
  surface exposes for `seerrsense` is the reviewed committed decision rather
  than whatever a dashboard session last left behind.
- AS an operator I WANT a `--check` mode that never writes SO THAT I can answer
  "does the live portal still agree with this repository?" without risking a
  change while I am asking.
- AS the author of mctlhq/mctl-gitops#1211 I WANT the same command name,
  argument, exit codes and drift-line format as the other two upstreams SO THAT
  one CI job can run all three checks and produce one red light.
- AS a reviewer I WANT the drift detector proven green on a matching fixture and
  red on a one-field-changed fixture SO THAT I know it can go both ways and has
  not repeated the `jq //` false-substitution bug in its JavaScript form
  (`||`/`??` collapsing a genuine `false` into "absent").
- AS an operator previewing an unfamiliar branch I WANT the Cloudflare
  credential kept out of the environment of the repository code the script runs
  SO THAT running the guard test does not hand a portal token to a checkout.

## Acceptance criteria (EARS)

Invocation and modes

- WHEN `scripts/portal-allowlist-apply.sh` is invoked with no argument THE
  SYSTEM SHALL apply the committed `docs/portal-allowlist.json` to the
  `seerrsense` mapping of portal `mcp`, exiting 0 on success and 1 on any
  pre-flight or API failure.
- WHEN it is invoked with `--dry-run` THE SYSTEM SHALL print the request body
  that an apply would `PUT` and exit without issuing any write.
- WHEN it is invoked with `--check` THE SYSTEM SHALL compare the committed file
  against the live portal mapping and exit 0 when they agree, 3 when they
  disagree, and 1 when the comparison could not be made.
- WHEN it is invoked with `-h` or `--help` THE SYSTEM SHALL print usage naming
  all modes and the exit-code table, and exit 0.
- IF it is invoked with an unknown argument, or with more than one argument,
  THEN THE SYSTEM SHALL print usage to stderr and exit 2.
- WHILE running in `--check` or `--dry-run` mode THE SYSTEM SHALL issue no
  `PUT` on any path, including the path where the file and the portal disagree
  and the path where a guard refuses.

Pre-flight guards (identical in all three modes)

- IF `CLOUDFLARE_API_TOKEN` or `CLOUDFLARE_ACCOUNT_ID` is unset THEN THE SYSTEM
  SHALL refuse before any network call, naming the missing variable.
- IF the working directory is not a git checkout THEN THE SYSTEM SHALL refuse
  with exit 1, because the file cannot be compared against a committed one.
- IF `docs/portal-allowlist.json` is not tracked in the checkout THEN THE SYSTEM
  SHALL refuse with exit 1 and a message containing `is not tracked`, checked
  before the HEAD comparison (a path HEAD does not have compares clean however
  different the file on disk is).
- IF the on-disk `docs/portal-allowlist.json` differs from `HEAD` — staged or
  unstaged — THEN THE SYSTEM SHALL refuse with exit 1 and a message containing
  `differs from HEAD`.
- WHEN the file passes the HEAD comparison THE SYSTEM SHALL read the blob at
  `HEAD:docs/portal-allowlist.json` and use that content for every later step,
  so that an edit made on disk after the comparison is not what gets applied or
  checked.
- IF the vetted file's `portal` is not `mcp` or its `server` is not
  `seerrsense` THEN THE SYSTEM SHALL refuse with exit 1 and a message of the
  form `docs/portal-allowlist.json targets portal=<p> server=<s>; expected
  mcp/seerrsense`, so a file naming a portal or server this repository does not
  own cannot rewrite it.
- IF the repository's own guard test cannot be run on this host — no runnable
  Node, or no installed local vitest binary — THEN THE SYSTEM SHALL refuse with
  exit 1 and an actionable message (for the missing binary: run `npm ci`),
  rather than apply or check from a host that cannot verify the file.
- WHEN the guard test is run THE SYSTEM SHALL require positive evidence of a
  pass — process exit 0, zero failed tests, at least one passed test, and
  `tests/portal-allowlist.test.ts` among the files reported — and SHALL NOT
  treat "exited 0 having run nothing" as a pass.
- IF the guard test does not pass for the current file THEN THE SYSTEM SHALL
  refuse with exit 1 and print the captured test output, so the operator being
  refused is told which tool is undecided or unreasoned.
- WHILE running the guard test THE SYSTEM SHALL remove `CLOUDFLARE_API_TOKEN`
  and `CLOUDFLARE_ACCOUNT_ID` from the child environment.
- WHILE talking to Cloudflare THE SYSTEM SHALL keep the token out of any
  command line and out of any log line it prints.

Portal reads and the mapping

- WHEN a Cloudflare response envelope has `success` not true THE SYSTEM SHALL
  refuse with exit 1, naming which call failed and echoing `errors`; in
  `--check` this is exit 1 ("could not check"), never exit 3.
- IF portal `mcp` carries other than exactly one mapping for server
  `seerrsense` THEN THE SYSTEM SHALL refuse with exit 1 and a message
  containing `expected exactly one`, because rewriting a server that is not on
  the portal would be a silent no-op.
- IF the server read returns no synced tools THEN THE SYSTEM SHALL refuse with
  exit 1, asking whether the server has connected.

What the apply writes

- WHEN building the request body THE SYSTEM SHALL start from the portal body
  exactly as read, delete only the four top-level timestamps (`created_at`,
  `created_by`, `modified_at`, `modified_by`), and rewrite only the
  `seerrsense` element, leaving every other field and every other server
  element untouched.
- WHEN building `updated_tools` THE SYSTEM SHALL include only tools the server
  has synced, and SHALL write each tool's `enabled` as a boolean, never as
  `null`.
- IF the server has synced a tool that the committed file does not decide THEN
  in apply and `--dry-run` mode THE SYSTEM SHALL refuse with exit 1, list the
  uncovered tools, and say that a recently removed tool may mean the portal has
  not re-synced yet.
- WHEN an apply's `PUT` succeeds THE SYSTEM SHALL verify that the response's
  `updated_tools` for `seerrsense` are exactly the `{name, enabled}` set that
  was sent, and SHALL exit 1 telling the operator to verify the portal by hand
  if entries were dropped, flipped, added or the mapping is missing.
- WHEN an apply completes THE SYSTEM SHALL print one summary line of the form
  `applied: default_disabled=<bool> tools=<n> enabled=<comma-separated names>`.

What `--check` reports

- WHEN `--check` finds the portal and the file in agreement THE SYSTEM SHALL
  print `in sync: default_disabled=<bool> tools=<n> enabled=<comma-separated
  names>` and exit 0.
- WHEN `default_disabled` differs THE SYSTEM SHALL print
  `drift: default_disabled portal=<value> file=<value>` and exit 3.
- WHEN a tool's `enabled` differs THE SYSTEM SHALL print
  `drift: <tool> portal=<value> file=<value>` and exit 3.
- WHEN a tool is present in the live `updated_tools` but absent from what the
  apply would write THE SYSTEM SHALL report it as `file=absent`; WHEN it is
  present in what the apply would write but absent live, as `portal=absent`.
- WHEN the server has synced a tool the file does not decide THE SYSTEM SHALL
  report `drift: <tool> synced by the server with no decision in
  docs/portal-allowlist.json` rather than refusing, and SHALL still evaluate
  every other tool in the same run.
- WHEN the file decides a tool the server has not synced THE SYSTEM SHALL treat
  it as held back rather than drift, and SHALL name it on a
  `held back (not synced by the server): <comma-separated names>` line.
- WHEN any disagreement is found THE SYSTEM SHALL print every drift line it
  found, then a `<n> difference(s) between the portal and
  docs/portal-allowlist.json` line to stderr, and exit 3.
- WHILE comparing THE SYSTEM SHALL derive the expected side from the same body
  the apply would send, rather than recomputing it, so the comparison cannot
  fall out of step with the apply.
- WHILE computing the comparison THE SYSTEM SHALL distinguish absent from
  `false` using explicit own-property checks, and SHALL NOT use a defaulting
  operator (`||`, `??`, or an equivalent) anywhere a genuine `false` could be
  turned into "absent".

Interface parity for mctlhq/mctl-gitops#1211

- WHEN mctlhq/mctl-gitops#1211 runs `scripts/portal-allowlist-apply.sh --check`
  in a checkout of this repository THE SYSTEM SHALL behave as specified above,
  with the same exit-code contract as the mctl-telegram and mctl-api scripts
  (0 in sync, 1 could not check, 2 usage error, 3 drift).
- IF the wrapper cannot find a runnable Node THEN THE SYSTEM SHALL exit 1 with
  a message naming Node as the missing prerequisite, rather than failing with a
  shell "command not found" status.

Evidence

- WHEN the change is proposed for review THE SYSTEM SHALL carry automated tests
  that prove, by spawning the command rather than by reading its source: the
  green case on a matching fixture, the red case on a fixture differing by
  exactly one field, both absent directions, the synced-with-no-decision case,
  the held-back case, the inherited guards, and that no write request reaches
  the stubbed API in `--check` on any of those paths.

## Out of scope

- Calling this from CI in any repository. The `cloudflare-drift.yml` job that
  runs all three checks is mctlhq/mctl-gitops#1211 and depends on this landing.
  This proposal adds no job to `.github/workflows/ci.yml`.
- Changing any allowlist decision. No tool's `enabled` value and no `reason`
  moves here, and `tests/portal-allowlist.test.ts` keeps its current
  assertions and its `writeToolsOnPortal` vouch for `request_media`.
- Changing anything about the portal's own switches (`portal-controls-apply.sh`
  in mctl-gitops) or the OpenTofu import decided in mctlhq/mctl-gitops#1092.
- Provisioning or scoping the Cloudflare token. The script consumes
  `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`; obtaining them is the
  operator's (and #1211's) problem.
- Mirroring the mctl-api change (mctlhq/mctl-api#300) or editing the
  mctl-telegram reference.
- Any change to the MCP tool set in `src/mcp/server.ts`.

## Open questions

- The issue body describes the committed file as "4 read tools enabled,
  `request_media` off". The file at `HEAD` disagrees: `request_media` is
  `enabled: true`, carrying the owner decision of 2026-09-12
  (mctlhq/.github#35), and `tests/portal-allowlist.test.ts` vouches for it in
  `writeToolsOnPortal`. The issue text is read as stale prose, not as an
  instruction; this proposal changes no decision, so the apply will publish
  `request_media` enabled. Reviewer: confirm that is still the intent. If it is
  not, flipping it is a separate one-line change to the file, reviewed on its
  own.
- Implementation form. The issue permits a shell script or a repository-native
  command. This proposal chooses a Node ESM script (`scripts/portal-allowlist-
  apply.mjs`, following `scripts/sync-tokens.mjs`, which is this repository's
  only existing operator script and already carries a `--check` mode) plus a
  thin `scripts/portal-allowlist-apply.sh` wrapper that `exec`s it, so #1211
  can call one identical path in all three repositories. If the reviewer would
  rather have a literal bash port of the mctl-telegram script and no wrapper,
  say so at review time — the contract in this document is unchanged either way.
- Unlike the Go upstreams, running this repository's guard test needs installed
  devDependencies (`node_modules/.bin/vitest`). A #1211 job that checks out this
  repository must therefore run `npm ci` first. Confirm that is acceptable
  there; the alternative — trusting a recorded CI pass instead of running the
  test — is deliberately not offered, because the guard must run against the
  file being applied.
- The test harness needs the script to talk to a stub instead of Cloudflare.
  This proposal allows a base-URL override that is honoured only for loopback
  URLs. Reviewer: confirm the loopback restriction is the right shape, given
  that a non-loopback override would be a way to point an operator's token at
  someone else's endpoint.
- The exact field names of vitest 5's JSON reporter output (`numPassedTests`,
  `numFailedTests`, `numTotalTests`, per-file results) are assumed
  Jest-compatible; the implementer must verify against the installed version and
  fail closed if the shape is not recognised.
