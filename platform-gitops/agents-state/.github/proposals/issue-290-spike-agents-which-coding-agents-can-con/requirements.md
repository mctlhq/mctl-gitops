# Spike: which coding agents can connect to mctl over MCP (agent-client-compatibility)

## Context

mctlhq/.github#290 asks how many of the twelve coding agents on Cloudflare's
agent-setup page (Claude Code, Codex, Cursor, Devin, Droid, GitHub Copilot,
OpenCode, Pi, Vibe, Visual Studio Code, Command Code, Bionic) can complete one
smoke test against `https://api.mctl.ai/mcp` by following only a public guide:
(1) connect and authenticate as a tenant user, (2) call
`mctl_list_platform_skills` and get a non-empty list, (3) call
`mctl_read_platform_skill` on one public skill and get its body. An optional
fourth step loads the `platform-skill` MCP prompt and is recorded separately.
For any agent that fails, the spike records the step where it fails. Today the
only documented and exercised clients are Claude Code and Codex
(mctlhq/mctl-agents#909). The spike manifest already exists at
`roadmap/spikes/agent-client-compatibility.yaml` (`lifecycle: proposed`,
`evidence.report: docs/spikes/agent-client-compatibility.md`).

This matters because the platform properties mctl adds (review gates,
lifecycle ownership, budgets and receipts, tenant isolation, cross-agent
handoff from .github#281) only reach a user if that user's agent can connect.
The spike produces a re-runnable probe, a 12-row matrix and a proposed verdict
(`PLATFORM_READY | FIX_PROTOCOL_FIRST | AUTH_PATH_PER_AGENT | NOT_A_FIT`). The
owner records the decision. The spike itself changes nothing in mctl-api.

## User stories

- AS the platform owner I WANT a per-agent matrix of the step each agent
  reaches, with the error quoted verbatim, SO THAT I can decide whether to file
  a "Pick your agent" epic, fix mctl-api first, open an auth-path decision, or
  stop.
- AS a platform engineer I WANT a scripted probe that reproduces each agent's
  documented MCP client behaviour SO THAT the matrix can be re-run in CI after
  an mctl-api change, without twelve licences.
- AS a reviewer I WANT proof that the probe goes red against a broken endpoint
  SO THAT a green matrix is evidence and not an artefact of a probe that always
  passes.

## Acceptance criteria (EARS)

- WHEN the spike is complete THE SYSTEM SHALL contain
  `docs/spikes/agent-client-compatibility.md` with exactly 12 matrix rows in
  the column order `agent | version | transport | auth method supported | step
  reached | failing error verbatim | what mctl would have to change`, plus a
  separate column or table for optional step 4 (`platform-skill` prompt).
- WHEN the probe runs a client profile against an MCP endpoint THE SYSTEM SHALL
  report, per profile, the highest step reached (0-3), step 4 separately, and
  the first failing response quoted verbatim (status line, `WWW-Authenticate`,
  and the JSON-RPC or OAuth error body, with tokens redacted).
- WHEN the probe runs against `https://api.mctl.ai/mcp` with a valid tenant-user
  token THE SYSTEM SHALL reach step 3 for the reference profile
  (streamable HTTP, OAuth with DCR and PKCE S256), which is the green proof.
- WHEN the probe runs against a deliberately broken endpoint (wrong path,
  invalid bearer, an authorization server without `registration_endpoint`, and
  a server that returns an empty skill list) THE SYSTEM SHALL report a failure
  at the expected step for each case. The unit tests SHALL assert each
  expected failure step, which is the red proof.
- WHEN an agent has no public MCP client documentation and no trial or real
  client is available THE SYSTEM SHALL record the row as `UNTESTED` with the
  reason. The report SHALL count it as neither pass nor fail.
- WHEN a real client (Claude Code, Codex, Cursor) is run by hand THE SYSTEM
  SHALL record its observed step next to the scripted result. Any divergence
  SHALL be recorded as a finding against the probe profile.
- WHEN the matrix is complete THE SYSTEM SHALL derive the proposed verdict with
  a deterministic rule written in the report and implemented in the probe
  (`verdict()`): `PLATFORM_READY` if at least 8 of 12 pass steps 1-3 with no
  mctl change; `FIX_PROTOCOL_FIRST` if a majority fail on the same mctl-side
  step; `AUTH_PATH_PER_AGENT` if transport works but several agents fail only
  at the OAuth step; otherwise `NOT_A_FIT` if fewer than 4 pass and the
  failures are structural.
- WHILE the spike runs THE SYSTEM SHALL NOT add, enable or change any auth path,
  OAuth grant, client registration policy or token type in mctl-api. A static
  token or device-code need is recorded as a finding only (fail-closed rule).
- WHILE the probe runs against production THE SYSTEM SHALL use only read
  operations (`initialize`, `tools/list`, `tools/call` on the two skill tools,
  `prompts/list`, `prompts/get`) and DCR registration. It SHALL NOT print or
  persist access tokens, refresh tokens or client secrets.
- IF a probe step depends on an interactive browser login THEN THE SYSTEM SHALL
  take the token from an environment variable (`MCTL_PROBE_TOKEN`) and SHALL
  mark steps 2-3 as `not run (no token)`, never as failed, when the variable is
  absent.
- WHEN a pull request touches `docs/spikes/agent-client-compatibility/**` THE
  SYSTEM SHALL run the probe's offline unit tests in
  `.github/workflows/workflow-tests.yml`. The live run SHALL NOT be a required
  PR check.

## Out of scope

- Any change to mctl-api (new grant types, static tokens, a device flow,
  redirect URI policy, a stdio bridge). These are findings for the follow-up
  issue chosen by the verdict.
- Recording the decision in `roadmap/spikes/agent-client-compatibility.yaml`
  (the owner does that) and changing its `lifecycle`.
- The "Pick your agent" page on mctl.ai and any epic manifest.
- Buying licences or creating accounts for agents to test them by hand, beyond
  Claude Code, Codex and Cursor.
- The .github#281 handoff protocol itself. Only the connect/list/read path is
  measured.

## Open questions

- Verdict precedence when more than one outcome rule matches (for example, 5
  agents pass and 6 fail only at OAuth). Proposed order: `PLATFORM_READY`,
  then `FIX_PROTOCOL_FIRST`, then `AUTH_PATH_PER_AGENT`, then `NOT_A_FIT`. If
  none matches, the report says "no rule matched" and the owner decides.
- Whether `UNTESTED` rows count in the denominator of "8 of 12". Proposed:
  yes, so an `UNTESTED` row counts as not passing. The report also states the
  rate over tested agents.
- "Several agents cannot do the OAuth flow" has no number. Proposed: 3 or more.
- Which tenant identity the live run uses. The run identity observed here
  (`agent:issue-investigator`, no teams) could list public skills, so a
  dedicated low-privilege tenant user is enough. Its owner and credential
  storage are not settled.
- Whether `api.mctl.ai/oauth/register` accepts the redirect URI forms that
  agents use (`http://127.0.0.1:<port>`, `vscode://`, `cursor://`, hosted
  callbacks for cloud agents). This was not observed: the spike did not POST a
  registration while investigating, and the probe measures it.
- "Pi", "Vibe", "Command Code" and "Bionic" are taken as named on the
  Cloudflare page. Their vendor and MCP documentation are identified during
  task 1. They are not assumed.
