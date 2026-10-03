# Drift detection for the Cloudflare portal allowlist (`--check`)

## Context

`docs/portal-allowlist.json` is the committed decision about which of this
server's MCP tools the Cloudflare portal (`mcp.mctl.ai`, server `tg`) exposes.
`scripts/portal-allowlist-apply.sh` pushes that decision to Cloudflare with a
single `PUT`, and `internal/mcp/portal_allowlist_test.go` keeps the file honest
against the tool set the server registers. Nothing reads the portal back. The
file therefore records what was decided, and no automated path can say whether
the portal still agrees: a tool flipped in the Cloudflare dashboard, an apply
that died between the read and the write, or a `default_disabled` changed while
debugging are all invisible until a human opens the portal UI. On a shared
surface the failure mode is a tool being exposed that this repository believes
is off.

The gap became load-bearing on 2026-09-12: the owner decided in
mctlhq/mctl-gitops#1092 that the OpenTofu import of the portal will not declare
the `servers` attribute, so `tofu plan` will never surface per-tool drift. The
detector has to live in this repository. This proposal adds a `--check` mode to
`scripts/portal-allowlist-apply.sh` that compares the committed allowlist
against the live portal, reports disagreement per tool, never writes, and is
held to the same pre-flight guards as an apply. It is modelled on
`mctl-gitops/scripts/portal-controls-apply.sh --check`, which already does this
for the portal's own switches.

## User stories

- AS a platform operator I WANT to ask whether the live portal still matches
  `docs/portal-allowlist.json` SO THAT I learn about drift from a command
  instead of from a dashboard inspection.
- AS an operator running an unfamiliar branch I WANT `--check` to refuse an
  unreviewed or untracked allowlist exactly as an apply does SO THAT a check
  run cannot answer a question about a file nobody reviewed.
- AS the author of the future CI job (mctlhq/mctl-gitops#1211) I WANT a
  deterministic exit status and a machine-greppable per-tool report SO THAT a
  scheduled run can fail loudly and name what moved.
- AS a reviewer of this change I WANT the detector proven red and green by
  mutation SO THAT I know it can actually detect, not merely exit 0.

## Acceptance criteria (EARS)

Invocation and guards

- WHEN `scripts/portal-allowlist-apply.sh --check` is invoked THE SYSTEM SHALL
  run the same pre-flight as an apply, in the same order: `CLOUDFLARE_API_TOKEN`
  and `CLOUDFLARE_ACCOUNT_ID` present, `jq` present, the directory is a git
  checkout, `docs/portal-allowlist.json` is tracked, it is identical to `HEAD`,
  the committed blob names `portal=mcp`/`server=tg`, `go` is present, and
  `TestPortalAllowlist_CoversEveryRegisteredTool` reports itself passed.
- IF any pre-flight check fails under `--check` THEN THE SYSTEM SHALL print the
  same refusal message it prints today and exit non-zero without contacting
  Cloudflare.
- WHEN `--check` reads the allowlist THE SYSTEM SHALL read the committed blob
  (`git show HEAD:docs/portal-allowlist.json`), not the copy on disk, so that a
  file edited after the guard ran is not the file compared.
- WHEN `--help` or `-h` is passed THE SYSTEM SHALL print usage naming
  `--check`, `--dry-run` and the default apply, and exit 0.
- IF an unknown argument, or more than one argument, is passed THEN THE SYSTEM
  SHALL print usage and exit 2, as today.

Comparison

- WHEN the pre-flight passes under `--check` THE SYSTEM SHALL `GET` the portal
  and the server, and compare the live `tg` mapping against exactly the mapping
  an apply would write: the mapping's `default_disabled`, and for every tool in
  the committed file that the server has synced, that tool's `enabled`.
- WHILE comparing THE SYSTEM SHALL treat a tool present in the live
  `updated_tools` but absent from the committed file as drift, and a tool the
  committed file decides and the server has synced but that is absent from the
  live `updated_tools` as drift; neither may be silently skipped.
- WHILE comparing THE SYSTEM SHALL treat a synced tool with no decision in the
  committed file as drift and report it, rather than exiting early the way the
  apply path does.
- WHILE comparing THE SYSTEM SHALL NOT use jq's `//` operator to supply a
  default for any value being compared, because `//` substitutes on `false` as
  well as on `null` and would report a matching baseline as drifted (the bug
  recorded in `mctl-gitops/scripts/portal-controls-apply.sh`).
- WHILE comparing THE SYSTEM SHALL distinguish "absent" from `false` in the
  report, so that a missing entry and a disabled entry do not read alike.
- WHILE the committed file decides a tool the server has not synced THE SYSTEM
  SHALL NOT report that tool as drift, because the apply deliberately holds
  such entries back from the write; it SHALL name them in the summary as held
  back.

Result

- IF the live mapping matches the committed decision THEN THE SYSTEM SHALL
  print a one-line summary naming `default_disabled`, the number of tools
  compared and the enabled tools, and exit 0.
- IF the live mapping differs THEN THE SYSTEM SHALL print one line per
  difference, naming the tool (or `default_disabled`), the value the portal
  has and the value the file says, and exit non-zero.
- WHILE running under `--check` THE SYSTEM SHALL NOT issue any `PUT` or other
  write to the Cloudflare API, including on the path where the file and the
  portal disagree.
- IF the API returns an unsuccessful envelope, the portal has no mapping for
  `tg`, or the server reports no synced tools THEN THE SYSTEM SHALL exit with
  the "could not check" status, distinct from the drift status, because nothing
  was measured.
- WHILE documenting the exit statuses THE SYSTEM SHALL state that every
  non-zero status is a failure a caller must surface, and that the distinction
  between "drifted" and "could not check" exists to tell a human what happened,
  never to let a caller treat one of them as tolerable. A detector that a
  guard refusal, an expired token or an API outage can quietly silence reports
  "no drift" for the same reason a broken one does.

Unchanged behaviour

- WHILE invoked with no argument or with `--dry-run` THE SYSTEM SHALL behave
  exactly as it does today, including the `PUT`, the post-write `applied:`
  summary, and the early refusal on a synced tool with no decision in the file.

Proof

- WHEN the change is submitted THE SYSTEM SHALL be covered by tests in
  `scripts/portal_allowlist_apply_test.go` that drive the real script against
  throwaway checkouts: one showing `--check` green against a matching fixture,
  and at least one showing it red against a fixture differing in exactly one
  field, with the drift report naming that field.
- WHEN `--check` runs in those tests THE SYSTEM SHALL be proven to have issued
  no write by observing the stubbed `curl` (a recorded call log), not by
  reading the script.
- WHEN the change is submitted THE SYSTEM SHALL record the red and the green
  run in the pull request body.

## Out of scope

- Calling `--check` from CI. The `cloudflare-drift.yml` job is
  mctlhq/mctl-gitops#1211 and depends on this landing first.
- Changing any allowlist decision. No tool's `enabled` value and no
  `default_disabled` moves in this proposal.
- Mirroring the change into mctlhq/mctl-api#300 or mctlhq/seerrsense#70. This
  repository is the reference implementation and goes first.
- Repairing drift. `--check` reports; the operator re-runs the apply.
- A JSON output mode. The report is human text; #1211 can key on exit status
  and grep the per-tool lines.
- Comparing fields of the live mapping the apply does not write (nested
  read-only fields on server elements, the four top-level timestamps).

## Open questions

- **Exit status for drift.** The issue requires only "non-zero". This proposal
  uses `3` for drift, keeping `1` for "could not check" (guard refusal, API
  error, missing mapping, no synced tools) and `2` for usage, following the
  four-code precedent of `cmd/mcpprobe` documented in
  `docs/cloudflare-portal-compat.md` ("the endpoint is wrong" and "nothing was
  measured" call for different reactions). If mctlhq/mctl-gitops#1211 prefers a
  single non-zero code, collapsing 3 into 1 is a one-line change. Proceeding
  with 3. **Amended during review:** whichever way that lands,
  mctlhq/mctl-gitops#1211 must go red on any non-zero status. The distinct
  codes are for the human reading the run, not a licence to alert on 3 alone --
  treating 1 as "infrastructure noise" would turn an expired token into a
  green run.
- **A file entry for a tool the portal has not synced.** Read as not drift,
  because the apply holds those entries back by design (a deployment on
  `MCP_TOOL_FILTER=read-only`, or a portal that has not re-synced since a
  release). It is named in the summary so it is visible. Proceeding with that
  reading.
- **`--check` on a host without `go`.** The issue says the existing guards
  apply to `--check`, so a host that cannot run the guard test is refused even
  though a check writes nothing. Proceeding with the strict reading.
- **Live `enabled` that is neither `true` nor `false`** (null, or absent from
  an otherwise present entry). Never observed; reported as drift with the
  literal live value rather than coerced, so it cannot vanish into `false`.
