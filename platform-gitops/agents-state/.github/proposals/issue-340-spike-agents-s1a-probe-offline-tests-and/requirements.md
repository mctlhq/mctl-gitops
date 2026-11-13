# Spike slice S1a: agent-client compatibility probe, offline tests and draft matrix

## Context

mctlhq/.github#290 (manifest `roadmap/spikes/agent-client-compatibility.yaml`,
`lifecycle: proposed`) asks how many of the twelve coding agents on
https://developers.cloudflare.com/agent-setup/ can connect to
`https://api.mctl.ai/mcp`, list the platform skills and read one, and at which
step the others fail. Issue #340 carves out the part an implementer can finish
without a human or a production credential: agent profiles from public docs,
a stdlib Python probe, offline red/green tests wired into CI, and a draft
report whose matrix is filled only from documentation and a token-less
discovery run (steps 1a-1c). The live authenticated run, the hand checks in
real clients and the verdict stay on #290.

The design reuses the earlier, expired #290 proposal
(`platform-gitops/agents-state/.github/proposals/issue-290-spike-agents-which-coding-agents-can-con/`):
its step ladder, fixtures and `verdict()` precedence. This matters because the
eventual verdict must be computed by a probe that is proven to go red, and
the draft must not overstate what has been observed.

## User stories

- AS the platform owner I WANT a draft 12-row matrix in which every cell says
  whether it comes from documentation, an observed probe run, or is untested
  SO THAT I can see exactly what remains for the live run on #290.
- AS the operator who later does the live run I WANT a ready, tested probe
  that takes a token only from `MCTL_PROBE_TOKEN` and never registers a client
  unless asked SO THAT the live run is a single command with no production
  surprise.
- AS a reviewer I WANT each offline red fixture to fail at a named step and
  each test to fail when the guarded behaviour is removed SO THAT a green
  matrix is evidence and not an artefact of a probe that always passes.

## Acceptance criteria (EARS)

- WHEN the slice is merged THE SYSTEM SHALL contain
  `docs/spikes/agent-client-compatibility/agents.json` with exactly 12
  profiles (Claude Code, Codex, Cursor, Devin, Droid, GitHub Copilot,
  OpenCode, Pi, Vibe, Visual Studio Code, Command Code, Bionic), each field
  carrying or inheriting a `doc_url`, and every field the docs do not state
  set to `"unknown"`.
- WHEN `probe.py` runs a profile THE SYSTEM SHALL execute the ladder 1a
  (transport), 1b (discovery), 1c (registration), 1d (token), 2 (list skills),
  3 (read skill) and optional 4 (prompt) in order, stop the main ladder at the
  first failing step, and report `step_reached`, `failed_step`, step 4
  separately, and the first failing response verbatim with secrets redacted.
- WHILE `MCTL_PROBE_TOKEN` is unset THE SYSTEM SHALL report steps 1d, 2, 3 and
  4 as `not run (no token)`, never as failed.
- WHILE `--register` is not given THE SYSTEM SHALL NOT send any request to the
  registration endpoint, and step 1c SHALL report `not run (--register off)`
  for DCR profiles.
- THE SYSTEM SHALL read the bearer token only from the `MCTL_PROBE_TOKEN`
  environment variable; there SHALL be no command-line flag for it.
- WHEN the probe produces output THE SYSTEM SHALL redact the token value,
  any `Bearer <value>`, and `access_token`, `refresh_token`, `client_secret`,
  `code` and `code_verifier` values from JSON and markdown output.
- WHEN `--markdown` is given THE SYSTEM SHALL print the 12-row matrix table
  instead of JSON.
- WHEN `verdict(results)` is called THE SYSTEM SHALL be a pure function of its
  argument and apply the precedence `PLATFORM_READY` (>= 8 of 12 pass steps
  1-3), then `FIX_PROTOCOL_FIRST` (>= 7 fail at the same mctl-side step), then
  `AUTH_PATH_PER_AGENT` (>= 3 fail only at 1b-1d with 1a green), then
  `NOT_A_FIT` (< 4 pass), else `NO_RULE_MATCHED`; `UNTESTED` and
  `not run` rows SHALL count as not passing.
- WHEN the offline tests run against the local fake servers THE SYSTEM SHALL
  assert: `good` reaches step 3 (and step 4); `wrong_path` fails at 1a;
  `bad_bearer` fails at 1d; `no_dcr` fails a DCR profile at 1b while a CIMD
  profile passes 1b; `empty_skills` fails at 2; `no_prompt` passes 1-3 and
  fails step 4 only.
- IF the behaviour a test guards is removed (for example a predicate is
  replaced by `True`) THEN THE SYSTEM SHALL make that test fail.
- WHEN a pull request or push to main touches
  `docs/spikes/agent-client-compatibility/**` THE SYSTEM SHALL run
  `python3 -I -m unittest discover -s docs/spikes/agent-client-compatibility/tests -v`
  in `.github/workflows/workflow-tests.yml`, with `permissions: {}` unchanged
  and no network access beyond loopback.
- WHEN the draft report `docs/spikes/agent-client-compatibility.md` is
  merged THE SYSTEM SHALL contain the method, a 12-row matrix in which every
  row and cell is tagged `[DOC]`, `[OBSERVED]` (with date and probe commit) or
  `UNTESTED` (with a reason), the non-claims, and a verdict section that reads
  `pending live run (#290)` and proposes no outcome.
- WHILE writing the draft THE SYSTEM SHALL NOT tag any cell `[OBSERVED]`
  beyond steps 1a-1c of the token-less run against `https://api.mctl.ai/mcp`.
- WHEN the slice is merged THE SYSTEM SHALL leave
  `roadmap/spikes/agent-client-compatibility.yaml` byte-identical, and
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` SHALL
  pass.

## Out of scope

- Obtaining a tenant-user token, any authenticated run against production,
  and any `--register` run (operator steps on #290).
- Hand checks in real Claude Code, Codex and Cursor clients.
- The verdict, and any edit to `roadmap/spikes/agent-client-compatibility.yaml`.
- Any change to mctl-api, mctl-gitops or other services, including new grant
  types or redirect URI policy.
- A scheduled live probe in CI.

## Open questions

- Step 1c in a token-less run: with `--register` off by default, 1c is
  `not run (--register off)` for DCR profiles. The issue says the token-less
  run covers "steps 1a-1c"; this proposal reads that as "1c evaluated as far
  as metadata allows" (registration endpoint advertised, CIMD advertised),
  never as a registration POST. The report states this explicitly.
- Whether to add an `AGENTS.md` `# Spikes` entry for the draft report now or
  only once the report is final. Proposed: add it now, labelled draft,
  matching the existing entries.
- Several agents (Pi, Vibe, Command Code, Bionic) may have thin or no public
  MCP documentation; their fields become `unknown` and their rows `UNTESTED`.
  This is expected, not a defect.
- Thresholds ("several" = 3, "majority" = 7) and the precedence order come
  from the earlier #290 proposal and remain the owner's to confirm on #290;
  they are encoded in one place in `verdict()` so a later change is local.
