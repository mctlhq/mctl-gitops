# portal-allowlist-apply.sh --check for the `api` upstream

## Context

`docs/portal-allowlist.json` is this repository's source of truth for which of
the 74 tools registered by `internal/mcp/server.go` the Cloudflare MCP portal
(`mcp.mctl.ai`) exposes for server id `api`, and
`scripts/portal-allowlist-apply.sh` writes that decision to Cloudflare. Nothing
reads it back. A tool flipped in the Cloudflare dashboard, a half-finished
apply, or a `default_disabled` changed while debugging is invisible until a
human opens the portal UI. On 2026-09-12 the owner decided
(mctlhq/mctl-gitops#1092) that the OpenTofu import of the portal will not
declare the `servers` attribute, so `tofu plan` will never surface per-tool
drift; the detector has to live in this script instead. The blast radius is
largest here: the `api` mapping is the widest of the three upstreams (the
committed file currently enables all 74 entries, every one of the mutating ones
vouched for in the `mutatingOnPortal` map in
`internal/mcp/portal_allowlist_test.go`).

mctlhq/mctl-telegram#632 is the reference implementation and has already landed
(mctlhq/mctl-telegram#634: `scripts/portal-allowlist-apply.sh` plus
`scripts/portal_allowlist_apply_test.go`). This proposal is the mirror for
`mctl-api`: the same `--check` mode, the same exit codes, the same output
strings, differing only in the server id (`api`) — a shared
`cloudflare-drift.yml` job (mctlhq/mctl-gitops#1211) will call both and must
not need to parse either specially.

## User stories

- AS the platform operator I WANT `scripts/portal-allowlist-apply.sh --check`
  to compare the committed allowlist against the live portal SO THAT I learn
  that `mcp.mctl.ai` exposes something this repository believes is off without
  opening the Cloudflare dashboard.
- AS the platform operator I WANT `--check` to name every disagreeing tool,
  with what the portal has and what the file says SO THAT I can tell a
  deliberate dashboard edit from a failed apply before I re-run the apply.
- AS a reviewer of mctlhq/mctl-gitops#1211 I WANT this script's flags, exit
  codes and output lines to be identical to `mctl-telegram`'s SO THAT one CI
  job can drive both upstreams with one code path.
- AS the platform operator I WANT `--check` to be provably incapable of writing
  SO THAT I can run it on a schedule, or against an unfamiliar branch, without
  risking a change to a shared surface.

## Acceptance criteria (EARS)

Invocation and usage

- WHEN the script is invoked with no argument THE SYSTEM SHALL apply the
  allowlist exactly as it does today.
- WHEN the script is invoked with `--dry-run` THE SYSTEM SHALL print the body
  it would PUT and exit 0, exactly as it does today.
- WHEN the script is invoked with `-h` or `--help` THE SYSTEM SHALL print a
  usage block that names `--check` and its exit codes, and exit 0, without
  requiring `CLOUDFLARE_API_TOKEN`, a git checkout or Go.
- IF the script is invoked with an unknown argument, or with more than one
  argument, THEN THE SYSTEM SHALL print usage to stderr and exit 2.

Pre-flight parity

- WHILE running in `--check` mode THE SYSTEM SHALL enforce the same pre-flight
  as an apply, in the same order: `CLOUDFLARE_API_TOKEN` and
  `CLOUDFLARE_ACCOUNT_ID` present, `jq` present, the script's parent is a git
  checkout, `docs/portal-allowlist.json` is tracked, the working tree copy is
  identical to `HEAD`, the committed file names `portal=mcp` and `server=api`,
  `go` is present, and `TestPortalAllowlist_CoversEveryRegisteredTool` in
  `internal/mcp/portal_allowlist_test.go` reports itself passed.
- WHEN the guard test is run THE SYSTEM SHALL run it with
  `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` removed from its
  environment, and SHALL require the run to print
  `--- PASS: TestPortalAllowlist_CoversEveryRegisteredTool` rather than merely
  exiting 0.
- WHEN any pre-flight check refuses in `--check` mode THE SYSTEM SHALL print
  the reason, make no HTTP call at all, and exit 1.
- WHEN the file has passed the pre-flight THE SYSTEM SHALL read the decisions
  from the committed blob (`git show HEAD:docs/portal-allowlist.json`), not
  from the copy on disk, on every path (apply, `--dry-run`, `--check`).

Comparison

- WHEN `--check` runs and the live mapping for `api` agrees with the committed
  file THE SYSTEM SHALL print a single line
  `in sync: default_disabled=<v> tools=<n> enabled=<comma-separated names>`
  and exit 0.
- WHEN a tool's `enabled` state on the portal differs from the committed
  decision THE SYSTEM SHALL print `drift: <tool> portal=<live> file=<committed>`
  for that tool and exit 3.
- WHEN the live mapping's `default_disabled` differs from the file's THE SYSTEM
  SHALL print `drift: default_disabled portal=<live> file=<committed>` and
  exit 3.
- IF a tool appears in the live `updated_tools` but has no decision in the
  committed file THEN THE SYSTEM SHALL report it as
  `drift: <tool> portal=<live> file=absent`.
- IF a tool is decided in the committed file, has been synced by the server,
  and is absent from the live `updated_tools` THEN THE SYSTEM SHALL report it
  as `drift: <tool> portal=absent file=<committed>`.
- IF a tool the server has synced has no decision in the committed file THEN in
  `--check` mode THE SYSTEM SHALL report
  `drift: <tool> synced by the server with no decision in docs/portal-allowlist.json`
  and continue evaluating the remaining tools, rather than refusing early the
  way apply and `--dry-run` do.
- WHEN `--check` finds any disagreement THE SYSTEM SHALL print every
  disagreeing item — not only the first — then a
  `<n> difference(s) between the portal and docs/portal-allowlist.json` line on
  stderr, and exit 3.
- IF the committed file decides a tool the server has not synced THEN THE
  SYSTEM SHALL NOT treat it as drift (the apply holds those back by design) and
  SHALL name it on a
  `held back (not synced by the server): <names>` line after the in-sync
  summary.
- WHILE comparing, THE SYSTEM SHALL NOT use jq's `//` operator to supply a
  default for `enabled` or `default_disabled`, because `//` substitutes on
  `false` as well as on `null` and would report a committed `false` as absent
  (the bug on record against `mctl-gitops/scripts/portal-controls-apply.sh`).

No write, and "could not check" is not "no drift"

- WHILE in `--check` mode THE SYSTEM SHALL issue no `PUT` on any path,
  including the path where it finds disagreement.
- IF the Cloudflare API answers an unsuccessful envelope, or the portal has
  other than exactly one mapping for `api`, or the server reports no synced
  tools, THEN in `--check` mode THE SYSTEM SHALL exit 1 (comparison could not
  be made), never 3.

Parity and documentation

- WHILE both scripts exist THE SYSTEM SHALL keep this script's flag set, exit
  codes (`0` in sync/applied, `1` could not check or apply, `2` usage error,
  `3` drift) and drift/summary line formats identical to
  `mctl-telegram/scripts/portal-allowlist-apply.sh`, the only difference being
  the server id `api`.
- WHILE mirroring THE SYSTEM SHALL copy `mctl-telegram`'s *landed* behaviour
  including its three known deviations from the published contract, rather than
  silently correcting them here: a missing `jq` exits `2` where the contract
  says `1`, `-h`/`--help` returns before the arity guard so `--help extra`
  exits 0, and a synced-but-undecided tool is counted twice in the
  `n difference(s)` total. They are tracked in mctlhq/mctl-telegram#635.
  Correcting them in one repository and not the other is the one thing parity
  cannot survive, because mctlhq/mctl-gitops#1211 drives both with one code
  path and would then see two different answers to the same condition. When
  #635 lands it must move both repositories in the same change; if it lands
  first, mirror the corrected behaviour instead and say so in the PR.
- WHEN this change lands THE SYSTEM SHALL describe `--check`, its exit codes
  and its no-write guarantee in the script's header comment, in `--help`, and
  in the "Portal tool allowlist" section of `README.md`.
- WHEN the exit codes are documented THE SYSTEM SHALL state that every non-zero
  status is a failure a caller must surface, and that the split between "could
  not check" and "drifted" exists to tell a human which happened, never to let
  a caller treat one of them as tolerable. A job alerting on `3` alone answers
  "no drift" when the token has expired, the scope was revoked or the API was
  down -- the same answer a working check gives when everything agrees.
  (mctl-telegram needed this added by hand after its implementation had already
  landed; it belongs in the contract here rather than in a second review.)
- WHEN the change is proposed for review THE SYSTEM SHALL carry an automated
  mutation proof in both directions: a `--check` run that exits 0 against a
  matching stubbed portal, and a `--check` run that exits 3 against the same
  stub with exactly one field changed, with the no-`PUT` guarantee proven by
  a recorded call log rather than by reading the script.
- WHILE asserting the no-`PUT` guarantee THE SYSTEM SHALL require the call log
  to exist and to show the reads, for every case that reaches the network,
  before the absence of a `PUT` is allowed to mean anything. An assertion
  gated only on a successful read skips itself when the log is missing -- a
  dropped `STUB_CURL_LOG`, a broken append -- and every case then passes with
  write-prevention silently switched off. This is not hypothetical: it is the
  P2 found on mctlhq/mctl-telegram#634 and fixed there in `f98920f`, after a
  mutation that made `--check` issue a `PUT` had already been taken as proof
  that the guard worked. `tasks.md` carries this; it belongs in the acceptance
  criteria too, because that is the half a reviewer checks against.

## Out of scope

- Wiring `--check` into CI. The scheduled `cloudflare-drift.yml` job that calls
  both upstreams is mctlhq/mctl-gitops#1211 and depends on this landing first.
  CI holds no Cloudflare credential (mctlhq/mctl-gitops#1111), so this stays
  operator-run.
- Changing any allowlist decision. No tool's `enabled`, no `reason`, no entry
  in `mutatingOnPortal` moves in this proposal.
- The third upstream, mctlhq/seerrsense#70 (no apply script exists there yet).
- Any change to `internal/mcp/portal_allowlist_test.go`,
  `internal/mcp/annotations_test.go`, the tool set, or the API server itself.
- Declaring the portal's `servers` attribute in OpenTofu — explicitly rejected
  by mctlhq/mctl-gitops#1092; this check exists because that will not happen.
- Auto-remediation: `--check` reports, it never fixes. Fixing is re-running the
  apply.

## Open questions

- The issue says "33 of ~74 tools enabled at last count". The committed file at
  `31135f4` (PR #297) enables all 74. That makes the drift blast radius larger,
  not smaller, and changes nothing about the work; recorded so the reviewer is
  not surprised by the count in the `in sync:` line.
- The `in sync:` summary interpolates every enabled tool name, so for `api`
  that line is roughly 2 KB against `mctl-telegram`'s handful of names.
  Proceeding with the identical format anyway: the issue requires that
  mctlhq/mctl-gitops#1211 need not parse either script specially, and
  truncating here would be exactly such a special case.
- `mctl-telegram` documents this in `docs/cloudflare-portal-compat.md`, which
  does not exist in this repository. Proceeding with the existing "Portal tool
  allowlist" section of `README.md` (the place that already documents
  `--dry-run` and the apply) rather than importing a new doc file.
- `mctl-telegram`'s header explains the file-may-exceed-portal case with
  `MCP_TOOL_FILTER=read-only`, which this repository does not have. Proceeding
  with this repository's existing wording ("a portal that has not re-synced
  since a release still holds the previous set"); the behaviour is identical,
  only the justifying sentence differs.
