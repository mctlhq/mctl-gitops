# Tasks: issue-376-spike-mcp-apps-write-once-run-across-ai

Revision 2. design.md opens with the finding-to-change matrix.

Approval boundary:
- This investigator run implements nothing.
- The owner pre-approval check below is done by the owner, not by an implementer.
- After explicit owner approval, the implementer may do tasks 1-8 only (phase 0, `mctlhq/.github`).
- Tasks 9-10 are owner decisions.
- B1-B6 are backlog slices in other repositories. Each needs its own issue and its own explicit approval.
- No workflow is restarted automatically.

Pre-approval owner check (not an implementer task):

- [ ] P0. Re-fetch `.github/ISSUE_TEMPLATE/spike.yml` from `main` and re-read #376. Title and body already conform (re-read 2026-11-22T01:38:57Z), and only one issue carries the Source. The labels show only `spike:scout`. Confirm that `agents:intake` was consumed by intake, or restore it deliberately. DoD: the owner records the conformance result on the issue before approving. If it does not conform, fix the issue and do not approve.

Phase 0 (`mctlhq/.github`, after approval):

- [ ] 1. Add `roadmap/spikes/mcp-apps-portability.yaml` as described in design.md section 1:
  - `lifecycle: proposed`;
  - the issue's Question line verbatim;
  - the three outcomes;
  - no `decision`, no `epic`.
  DoD: `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` and `roadmap/tests/test_validate_spike.py` pass.
- [ ] 2. Vendor `schema/ext-apps-2.1.0.schema.json` from the `v2.1.0` tag, with a `SOURCE` file (repo, tag, path, SHA-256). DoD: a test recomputes the SHA-256 and it matches.
- [ ] 3. Write `host_matrix.json` using the four-field cell schema (design.md section 2):
  - Re-read every vendor page and record the access date. Set `claim` from it.
  - The pages not re-read in revision 2 are the ext-apps spec, the OpenAI extensions page, Claude getting-started, the rollout article, and the Grok overview, approvals and changelog pages.
  - Leave `transport`, `fixture` and `observed` as `untested`.
  - Record the MCP protocol revision, the Apps spec revision and the SDK version as separate values.
  - Add the `grok-bot` column and mark it exploratory.
  DoD: the file contains no `real_host_verified` cell and `matrix.py` passes.
- [ ] 4. Implement `matrix.py`, `conformance.py` and `bundle_scan.py` (depends on 2). They are stdlib only and run with `python3 -I`.
  - The rules are in design.md section 1-2.
  - `conformance.py` fails closed on any schema keyword it does not support.
  - `bundle_scan.py` output is advisory and never sets a gate.
  DoD: each script has `--help`, exits non-zero on violations, and produces deterministic output.
- [ ] 5. Add fixtures (depends on 4):
  - valid and invalid matrices: a forged `real_host_verified` cell, a hash mismatch within one (app, release, route), and a "mismatch" across releases that must be accepted;
  - a sanitisation-violation artifact;
  - conformant and non-conformant message logs;
  - the Telegram `static_hypothesis` log reconstructed from `triage.html` at `b11b8a2`.
  DoD: every fixture names its source commit, and the static log is rejected as evidence.
- [ ] 6. Add `docs/spikes/mcp-apps-portability/tests/` (unittest, T1-T6) and wire it into the paths and steps of `.github/workflows/workflow-tests.yml` (depends on 4, 5). DoD: CI is green.
- [ ] 7. Write `docs/spikes/mcp-apps-portability.md` with the operator runbook (depends on 3-5). It must contain:
  - the inventory with repo@revision and path;
  - the static findings labelled `static_hypothesis`;
  - the ADR;
  - the PoC four-layer isolation and preflight;
  - the security model;
  - gates G1-G6, the D1 outcome table, D2, and the stop conditions;
  - the Grok boundary;
  - the backlog, risks and product order;
  - an empty decision block.
  The runbook extends #650. It does not activate #650 and it does not do Portal work, which belongs to #236. It covers the preflight, the per-gate steps, the capture and sanitisation checklist, pseudonyms, cleanup, and how to record `cause`. DoD: every runbook step maps to a matrix cell and a gate, and the report claims no verdict.
- [ ] 8. Add one bullet under `# Spikes` in `AGENTS.md` (depends on 7). DoD: the link resolves.

Owner decisions (not implementer work):

- [ ] 9. D1: the first-consumer portability decision. It depends on B4, or on a recorded UNMEASURED state when #650 reaches `reviewBy` without a session. DoD: the outcome comes from the design.md section 6 table, and the SpikeDefinition records a `decision` only when D1 is ADOPT_* or DEFER, with evidence refs.
- [ ] 10. D2: the shared-extraction decision. It depends on B5 gate evidence. It is recorded as `not_reached` if D1 is DEFER or if B5 never started. DoD: the measured diff between the two consumers is attached.

Backlog (separate issues and approvals; not part of the phase 0 PR):

- [ ] B1. mctl-telegram: an executable browser fixture (design.md section 3), plus a bridge fix that vendors the pinned ext-apps `App` build, or a justified hand-rolled bridge. The fixture must fail on the current bundle before the fix and pass after it. Owner: mctlhq/mctl-telegram. This slice is a hard prerequisite for B4.
- [ ] B2. mctl-telegram: the `MCP_TOOL_FILTER=core-readonly` allowlist value, accepted by `config.go`, plus default-deny for an unrecognised filter in `toolPassesFilter`. Restrict the App link set to the allowlist subset, use `get_unread_messages {}` as the entry tool, bump `Version` and record the bundle SHA. Also add the headless golden test. Owner: mctlhq/mctl-telegram.
- [ ] B3. mctl-gitops: an owner-approved isolated PoC deployment (depends on B1, B2). It is not `tg.mctl.ai` and not `tg-preview.mctl.ai`. Its settings:
  - `MCP_APPS_ENABLED=true`;
  - `MCP_TOOL_FILTER=core-readonly`;
  - `ALLOW_SEND=false`;
  - read-only `MCP_CLIENT_PROFILES` scope ceilings;
  - a throwaway account.
  A preflight script checks the configuration and fails closed. Owner: mctlhq/mctl-gitops plus the operator.
- [ ] B4. Operator session under #650's runbook (depends on B3). It runs only when #650's activation is met, or the owner explicitly scopes a portability-only session with no submission.
  - Core hosts: ChatGPT, Claude and Antigravity.
  - Headless: Codex, Claude Code and agy.
  - Optional: the `cf-portal` route and Grok Bot.
  - Fill in the `observed` cells and evaluate G1-G6.
  Owner: a human operator.
- [ ] B5. mctl-api: a read-only DevLoop Run Inspector App (depends on D1 = ADOPT_*, all of G1-G6 GO, owner review, attached security fixture results, and #261). There is no deployment before its own T7-T11-equivalent fixture results exist. Owner: mctlhq/mctl-api.
- [ ] B6. Later consumers (Glovo, SeerrSense, Alice), each with its own issue (depends on D2).

## Tests

Phase 0 (`mctlhq/.github`, unittest):

- [ ] T1. `matrix.py` rejects a matrix with any of these defects:
  - a `real_host_verified` or `failed` cell missing any evidence field;
  - a `failed` or `blocked` cell without `cause`;
  - a `documented` claim without a URL and date;
  - a `transport` or `fixture` status copied into `observed`.
- [ ] T2. `matrix.py` rejects different `bundle_sha256` values within one (app, release, route). It accepts different hashes across releases or routes, and it never counts `grok-bot` toward a gate.
- [ ] T3. `conformance.py` behaves as follows:
  - It validates messages against the vendored schema and passes the conformant log.
  - It fails a log with `initialized` sent before the initialize result, a View-to-host `tools/list`, a `tool-result` carrying `name`, or an unknown method.
  - It treats a host-to-View `tools/list` (app tools) as legal and records it as a separate row.
- [ ] T4. `conformance.py` rejects any log tagged `static_hypothesis` as evidence, and exits non-zero on a schema keyword it does not support.
- [ ] T5. The sanitisation scan fails artifacts containing `Bearer `, JWT-shaped strings, `code=`, an email address or a phone number. `bundle_scan.py` flags its patterns, but its result alone never changes a gate.
- [ ] T6. The SpikeDefinition validates with `proposed`, no `decision`, and the three outcomes.

Specified now, implemented in product repos (B1, B2, B3, B5):

- [ ] T7. Enumeration on the PoC instance with a raw MCP client: `tools/list` equals the `core-readonly` allowlist and `resources/list` equals `{ui://mctl-telegram/triage}`. The test fails if any extra tool appears, whatever its `readOnlyHint`, including `draft_reply`, `get_media` and admin reads.
- [ ] T8. Raw `tools/call` for every tool in the full server registry that is not in the allowlist, and for unknown method names, is refused. Each call is made both through the App path (fixture host) and directly.
- [ ] T9. Fail-closed configuration: startup, or the preflight, refuses each of these:
  - `MCP_TOOL_FILTER=readonly` (a typo), and the preflight additionally refuses an unset filter, because an unset filter defaults to `all`;
  - an unknown value reaching `toolPassesFilter` directly (unit test);
  - `ALLOW_SEND=true`;
  - a scope ceiling wider than read;
  - an extra resource.
- [ ] T10. Authorization:
  - The static resource is refused without authentication and served with it; it carries no user data.
  - User-data tool calls without the read scope, with a cross-account id (answered like not-found), with a stale or replayed request, or after `revoke_session` are denied.
  - Each case runs for both model-originated and UI-originated calls.
  - Revocation latency is asserted against the measured current bound, not assumed to be immediate.
- [ ] T11. Audit for the same read is identical for both origins apart from an untrusted origin annotation, and a forged origin hint does not change the decision.
- [ ] T12. Browser fixture (B1), on the actual bundle bytes with the SHA-256 asserted:
  - handshake order;
  - render on `{}`;
  - refresh and filter re-call read tools;
  - `host-context-changed` applies theme and dimensions;
  - teardown and no-teardown both leave no error;
  - controls for unadvertised capabilities are absent;
  - DOM and screenshot assertions.
- [ ] T13. Malformed, unknown-method, wrong-source and oversized messages, and script-like Telegram text, are inert: nothing is rendered as HTML and no tool is called. The View never puts Telegram text into `ui/message` or `ui/update-model-context`.
- [ ] T14. Headless golden test: `content[].text` is byte-equal with `MCP_APPS_ENABLED` on and off for every App-linked tool.

## Rollback

- Phase 0: revert the single PR in `mctlhq/.github`. No runtime, GitOps or tenant is touched. If the CI step is flaky, remove only its `workflow-tests.yml` entry.
- B1 and B2: revert the mctl-telegram PRs. With `MCP_APPS_ENABLED` unset, the App surface is off (default false in `internal/config/config.go`), and the new filter value is unused unless it is set.
- B3: revert the mctl-gitops PR, which removes the isolated deployment. Then clean up the throwaway account per the runbook.
- B5: the mctl-api feature flag defined in that issue.
- A DEFER or UNMEASURED outcome leaves the artifacts as the recorded measurement.
