# Tasks: issue-340-spike-agents-s1a-probe-offline-tests-and

- [ ] 1. Research the public MCP client documentation of the 12 agents
  linked from https://developers.cloudflare.com/agent-setup/ and write
  `docs/spikes/agent-client-compatibility/agents.json` in the schema from
  design.md. — DoD: 12 entries in the issue's order; every non-`unknown`
  value has a `doc_url`; undocumented fields are `unknown`; every
  `auth: unknown` entry has an `untested_reason`; access date recorded.
- [ ] 2. Write `docs/spikes/agent-client-compatibility/probe.py` (stdlib
  only): `load_profiles()`, ladder 1a-1d, 2, 3, optional 4 in `run_profile()`
  with injectable HTTP, `redact()`, `mctl_change()`, pure `verdict()` with the
  precedence and constants from design.md, CLI (`--endpoint`, `--profiles`,
  `--only`, `--register` off by default, `--markdown`, `--timeout`), token
  only from `MCTL_PROBE_TOKEN`. (depends on 1) — DoD: without a token, 1d-4
  report `not run (no token)`; without `--register` no request reaches the
  registration endpoint; no third-party imports.
- [ ] 3. Write `tests/fake_server.py`, `fixtures/` (protected-resource and AS
  metadata mirroring api.mctl.ai, a malformed `agents.json`) and
  `tests/test_probe.py` covering T1-T12. (depends on 2) — DoD:
  `python3 -I -m unittest discover -s docs/spikes/agent-client-compatibility/tests -v`
  passes locally offline; a manual mutation check (forcing each predicate to
  pass, disabling redaction, ignoring the `--register` gate) makes the guarding
  test fail, and the result is listed in the PR description.
- [ ] 4. Wire CI in `.github/workflows/workflow-tests.yml`: add
  `docs/spikes/agent-client-compatibility/**` to both `paths:` lists and one
  unittest step in job `test`. (depends on 3) — DoD: `permissions: {}`
  unchanged; step uses `python3 -I`; no network beyond loopback.
- [ ] 5. Run `python3 docs/spikes/agent-client-compatibility/probe.py --endpoint https://api.mctl.ai/mcp`
  (no token, no `--register`) and `--markdown`, from the committed probe.
  (depends on 2) — DoD: output saved for the report with date and probe
  commit; it shows only discovery (1a-1b, 1c as metadata or
  `not run (--register off)`); no write to production.
- [ ] 6. Write the draft `docs/spikes/agent-client-compatibility.md` and add
  a draft entry under `# Spikes` in `AGENTS.md`. (depends on 1, 5) — DoD:
  status banner, non-claims, evidence tags, pins, method, 12-row matrix plus
  step-4 column with every row and cell tagged `[DOC]`, `[OBSERVED]` (date +
  commit) or `UNTESTED` (reason); nothing beyond 1a-1c tagged `[OBSERVED]`;
  verdict section reads `pending live run (#290)` with no outcome proposed;
  remaining operator steps on #290 listed.
- [ ] 7. Verify invariants. (depends on 4, 6) — DoD:
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes and
  `git diff main -- roadmap/spikes/agent-client-compatibility.yaml` is empty.

## Tests

- [ ] T1. `good`: reference profile (streamable HTTP, `oauth-dcr`) with a test
  token reaches step 3; step 4 passes.
- [ ] T2. `wrong_path`: fails at 1a; 404 status recorded verbatim.
- [ ] T3. `bad_bearer`: fails at 1d; `WWW-Authenticate` recorded; the token
  string is absent from JSON and markdown output.
- [ ] T4. `no_dcr`: `oauth-dcr` profile fails at 1b; `oauth-cimd` profile
  passes 1b.
- [ ] T5. `empty_skills`: fails at step 2.
- [ ] T6. `no_prompt`: steps 1-3 pass, step 4 fails, recorded separately.
- [ ] T7. No token: 1d, 2, 3, 4 are `not run (no token)`; the fake server sees
  no `tools/call`.
- [ ] T8. Without `--register`: zero requests to the registration path and 1c
  is `not run (--register off)`; with `--register` against the fake, 1c
  passes with a `client_id`.
- [ ] T9. `static-header` / `device-code` profile against the observed AS
  metadata fails at 1d without sending a token request; `mctl_change` names
  the missing auth path.
- [ ] T10. `verdict()`: one matrix per outcome, precedence ties
  (`PLATFORM_READY` over `AUTH_PATH_PER_AGENT`, etc.), `NO_RULE_MATCHED`, and
  `UNTESTED`/`not run` counted as not passing; calling it twice on the same
  input gives the same result and does not mutate the input.
- [ ] T11. `redact()`: token value, `Bearer` values, `access_token`,
  `refresh_token`, `client_secret`, `code`, `code_verifier` replaced in nested
  structures and query strings.
- [ ] T12. `load_profiles()` on the committed `agents.json`: 12 names in order,
  enums valid, `doc_url` on every non-unknown value, `untested_reason` on every
  `auth: unknown`; malformed fixture raises. Report check: the draft report
  has 12 matrix rows, contains `pending live run (#290)`, and no step 1d-3
  cell is tagged `[OBSERVED]`.

## Rollback

All changes are additive in mctlhq/.github: revert the PR to remove
`docs/spikes/agent-client-compatibility/`, the draft report, the `AGENTS.md`
entry and the CI step/path filters. The spike manifest and all services are
untouched. The token-less discovery run writes nothing to production, so
there is nothing to clean up there.
