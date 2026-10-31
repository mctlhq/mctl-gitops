# Tasks: issue-290-spike-agents-which-coding-agents-can-con

- [ ] 1. Research the public MCP client documentation of each of the 12 agents
  (Claude Code, Codex, Cursor, Devin, Droid, GitHub Copilot, OpenCode, Pi,
  Vibe, Visual Studio Code, Command Code, Bionic), following the links from
  https://developers.cloudflare.com/agent-setup/. Write
  `docs/spikes/agent-client-compatibility/agents.json`. — DoD: 12 profiles with
  `name`, `version_documented`, `doc_url`, `transport`, `auth`,
  `redirect_uri_form`, `surfaces_prompts`, `runs_where`; each profile without a
  public guide has `auth: unknown` and an `untested_reason`; no field is
  guessed.
- [ ] 2. Write `docs/spikes/agent-client-compatibility/probe.py` (Python
  stdlib only): step ladder 1a-1d, 2, 3 and optional 4; profile loading;
  token from `MCTL_PROBE_TOKEN`; opt-in `--register`; redaction; JSON and
  `--markdown` output; pure `verdict()` with the precedence from design.md.
  (depends on 1) — DoD: `python3 probe.py --endpoint https://api.mctl.ai/mcp`
  runs discovery for all profiles without a token, and steps 2-3 report
  `not run (no token)`.
- [ ] 3. Write the offline red/green tests
  `docs/spikes/agent-client-compatibility/tests/test_probe.py` with
  local fake-server fixtures (`good`, `wrong_path`, `bad_bearer`, `no_dcr`,
  `empty_skills`, `no_prompt`). (depends on 2) — DoD: every variant asserts the
  exact failing step; `good` reaches step 3; verdict and redaction tests pass
  under `python3 -m unittest discover -s docs/spikes/agent-client-compatibility/tests -v`.
- [ ] 4. Wire CI: add `docs/spikes/agent-client-compatibility/**` to both path
  filters in `.github/workflows/workflow-tests.yml` and add one unittest step.
  (depends on 3) — DoD: the workflow runs the new tests on a PR that touches
  the directory, with `permissions: {}` unchanged and no network access needed.
- [ ] 5. Live run against production: obtain a token for a low-privilege
  tenant user through the reference OAuth flow; run the probe green against
  `https://api.mctl.ai/mcp`, run it red with `/mcpx` and with an invalid token,
  and run `--register` once per distinct redirect URI form. (depends on 2) —
  DoD: redacted outputs saved for the report with date and probe commit; the
  OAuth client IDs created are listed for revocation; no token appears
  anywhere in the repo.
- [ ] 6. Hand cross-check with the real Claude Code, Codex and Cursor clients
  (smoke test steps 1-4 each). (depends on 5) — DoD: observed step and
  verbatim error per client recorded next to the probe result; each divergence
  is filed as a probe-profile finding and the profile is corrected or the
  difference is explained.
- [ ] 7. Write `docs/spikes/agent-client-compatibility.md`: non-claims and
  evidence tags, pin table, observed auth surface, method, red/green proof,
  12-row matrix plus step-4 column, real-client table, findings per failing
  step with "what mctl would have to change", and the proposed verdict from
  `verdict()` with the rule. Add the `# Spikes` entry in `AGENTS.md`. (depends
  on 5, 6) — DoD: 12 rows in the issue's column order; `UNTESTED` rows have
  reasons; the verdict is reproducible by re-running the probe on the recorded
  results; `roadmap/spikes/agent-client-compatibility.yaml` is unchanged and
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes.

## Tests

- [ ] T1. `good` fixture: the reference profile (streamable HTTP,
  `oauth-dcr`, PKCE S256) reaches step 3, and step 4 passes.
- [ ] T2. `wrong_path`: the probe fails at 1a with the `404` recorded verbatim.
- [ ] T3. `bad_bearer`: the probe fails at 1d with the `401` and
  `WWW-Authenticate` recorded verbatim, and the token value is not present in
  the output.
- [ ] T4. `no_dcr`: an `oauth-dcr` profile fails at 1b and an `oauth-cimd`
  profile passes 1b.
- [ ] T5. `empty_skills`: the probe fails at step 2.
- [ ] T6. `no_prompt`: steps 1-3 pass and step 4 fails, recorded separately.
- [ ] T7. A `static-header` or `device-code` profile against the observed AS
  metadata (grants `authorization_code`, `refresh_token` only) fails at 1d
  without sending a request, and its `mctl_change` names the missing auth path.
- [ ] T8. `verdict()`: 8 passes give `PLATFORM_READY`; 7 failures at the same
  step give `FIX_PROTOCOL_FIRST`; 3 or more OAuth-only failures with fewer
  than 8 passes give `AUTH_PATH_PER_AGENT`; fewer than 4 passes with
  structural failures give `NOT_A_FIT`; a matrix matching no rule gives
  `NO_RULE_MATCHED`; `UNTESTED` counts as not passing.
- [ ] T9. Profile with `auth: unknown` renders as `UNTESTED` with its reason
  in the markdown table.
- [ ] T10. Live (manual, recorded in report): green against
  `https://api.mctl.ai/mcp`, red against `/mcpx` and against an invalid token.

## Rollback

Everything is additive in mctlhq/.github: revert the PR, which removes the
report, the probe directory, the `AGENTS.md` entry and the CI step. No
service, gitops value or roadmap manifest is changed. The only production
side effect is OAuth client registrations from `--register`. The report lists
their IDs, and an operator can revoke or delete them in mctl-api. Without
`--register`, the run leaves nothing behind.
