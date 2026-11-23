# Tasks: issue-376-spike-mcp-apps-write-once-run-across-ai

Revision 3. design.md opens with the revision 3 finding-to-change matrix
(P1-AP-R2-01, P2-AP-R2-02 to P2-AP-R2-05), each mapped to a negative test.

Approval boundary:
- This investigator run implements nothing.
- The owner pre-approval check below is done by the owner, not by an implementer.
- After explicit owner approval, the implementer may do tasks 1-8 only (phase 0 docs, schema snapshot, matrix and offline fixtures in `mctlhq/.github`).
- Tasks 9-10 are owner decisions.
- B1-B6 are backlog slices in other repositories. Each needs its own issue and its own explicit approval.
- No product deployment, real Telegram data, operator host linking, writes, payment or automatic workflow restart.

Pre-approval owner check (not an implementer task):

- [ ] P0. Re-fetch `.github/ISSUE_TEMPLATE/spike.yml` from `main` and re-read #376 (title, the six required lines, labels). Confirm that `agents:intake` was consumed by intake, or restore it deliberately. DoD: the owner records the conformance result on the issue before approving. If it does not conform, fix the issue and do not approve.

Phase 0 (`mctlhq/.github`, after approval):

- [ ] 1. Add `roadmap/spikes/mcp-apps-portability.yaml` (design.md section 1): `lifecycle: proposed`, the issue's Question line verbatim, the three outcomes, no `decision`, no `epic`. DoD: `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` and `roadmap/tests/test_validate_spike.py` pass.
- [ ] 2. Vendor `schema/ext-apps-2.1.0.schema.json` from the `v2.1.0` tag, with a `SOURCE` file (repo, tag, path, SHA-256). Generate the schema corpus deterministically: one valid and one mutated instance per `$defs` entry, plus explicit `$ref`, `anyOf`/`oneOf`, `const`/`enum`, `required` and `additionalProperties` cases, committed with the schema SHA-256. DoD: a test recomputes the SHA-256; `Draft202012Validator.check_schema` accepts the vendored schema; regenerating the corpus is byte-identical.
- [ ] 3. Write `host_matrix.json` using the `releases` table and four-field cell schema (design.md section 2):
  - one `releases` entry for (mctl-telegram-triage, 0.1.0) with `bundle_sha256 390a0338...0e88` and source commit `b11b8a2`;
  - routes `direct` (required) and `cf-portal` (`not_enabled`);
  - re-read every vendor page and record the access date; still unread: OpenAI extensions page, Claude rollout article, Grok overview, approvals and changelog pages, Antigravity `ui.domain` format;
  - leave `transport`, `fixture` and `observed` as `untested`;
  - record MCP protocol revision, Apps spec revision and SDK version separately;
  - add the `grok-bot` column marked exploratory.
  DoD: no `real_host_verified` cell; `matrix.py` passes.
- [ ] 4. Implement `matrix.py` (validator, renderer, D1 evaluator over the design.md section 6 gate scope table), `conformance.py` (oracle: `jsonschema.Draft202012Validator` over the vendored schema, plus explicit lifecycle rules), optional `lint.py` (stdlib structural lint, abstains on unknown keywords, never cited as conformance) and `bundle_scan.py` (advisory) (depends on 2). DoD: each script has `--help`, exits non-zero on violations, deterministic output; `conformance.py` fails, never skips, if `jsonschema` cannot be imported.
- [ ] 5. Add fixtures (depends on 4):
  - valid and invalid matrices: a forged `real_host_verified` cell; the route digest cases of T2a-T2d; a duplicate `releases` entry;
  - D1 evaluator inputs for T16;
  - `ui.domain` allowlist cases for T17 (as data, for the matrix and preflight rules);
  - a sanitisation-violation artifact;
  - conformant and non-conformant message logs;
  - the Telegram `static_hypothesis` log reconstructed from `triage.html` at `b11b8a2`.
  DoD: every fixture names its source commit; the static log is rejected as evidence.
- [ ] 6. Add `docs/spikes/mcp-apps-portability/tests/` (unittest, T1-T6, T15-T16) and wire it into the paths and steps of `.github/workflows/workflow-tests.yml` after the existing `pip install -r roadmap/requirements.txt` step, run as `python3 -m unittest discover -s docs/spikes/mcp-apps-portability/tests -v` (not `-I`, which would hide a user-site install of the oracle) (depends on 4, 5). DoD: CI is green and the oracle import is asserted in the log.
- [ ] 7. Write `docs/spikes/mcp-apps-portability.md` with the operator runbook (depends on 3-5): inventory with repo@revision and path (including the mctl-api bootstrap pin and the unobserved live state); static findings labelled `static_hypothesis`; ADR; PoC four-layer isolation and preflight; security model; `ui.domain` omission and allowlist rule; gate scope table, D1 outcome table, D2 and stop conditions; Grok boundary; backlog, risks and product order; empty decision block. The runbook extends #650, does not activate it and does no Portal work (#236). The operator checklist uses the same gate scope as the table (G2/G3 per core host on `direct`; G5 once per release; G6 per instance plus per-host trace; `cf-portal` optional). DoD: every runbook step maps to a matrix cell and a gate; the report claims no verdict.
- [ ] 8. Add one bullet under `# Spikes` in `AGENTS.md` (depends on 7). DoD: the link resolves.

Owner decisions (not implementer work):

- [ ] 9. D1: first-consumer portability decision (depends on B4, or a recorded UNMEASURED state when #650 reaches `reviewBy` without a session). DoD: the outcome is the `matrix.py` D1 evaluation of the design.md section 6 table, confirmed by the owner; the SpikeDefinition records a `decision` only when D1 is ADOPT_* or DEFER, with evidence refs.
- [ ] 10. D2: shared-extraction decision (depends on B5 gate evidence); `not_reached` if D1 is DEFER or B5 never started. DoD: the measured diff between the two consumers is attached.

Backlog (separate issues and approvals; not part of the phase 0 PR):

- [ ] B1. mctl-telegram: executable browser fixture (design.md section 3), with message logs checked by the same `jsonschema` oracle, plus a bridge fix vendoring the pinned ext-apps `App` build (or a justified hand-rolled bridge). The fixture must fail on the current bundle before the fix and pass after it; the fixed bundle gets a new release and a new `releases` digest. Owner: mctlhq/mctl-telegram. Hard prerequisite for B4.
- [ ] B2. mctl-telegram: `MCP_TOOL_FILTER=core-readonly` allowlist value, default-deny for unrecognised filters in `toolPassesFilter`, App link set restricted to the allowlist subset, `get_unread_messages {}` entry, headless golden test; `ui.domain` omitted by default, with an empty, reviewed allowlist mechanism (host, documented format, doc URL, access date, route server URL, exact bound client) that omits on zero or multiple matches. Owner: mctlhq/mctl-telegram.
- [ ] B3. mctl-gitops: owner-approved isolated PoC deployment (depends on B1, B2); not `tg.mctl.ai` or `tg-preview.mctl.ai`; `MCP_APPS_ENABLED=true`, `MCP_TOOL_FILTER=core-readonly`, `ALLOW_SEND=false`, read-only `MCP_CLIENT_PROFILES` scope ceilings, empty `ui.domain` allowlist, throwaway account. A preflight script fails closed on any mismatch. Owner: mctlhq/mctl-gitops plus the operator.
- [ ] B4. Operator session under #650's runbook (depends on B3), only when #650's activation is met or the owner explicitly scopes a portability-only session with no submission. Required: core hosts on `direct`, headless clients. Optional: `cf-portal` (only if #236 enabled it) and Grok Bot. Fill `observed` cells (with `server_served_sha256`) and evaluate gates at their table scope. Owner: a human operator.
- [ ] B5. mctl-api: read-only DevLoop Run Inspector App (depends on D1 = ADOPT_*, owner review, attached security fixture results, #261, and an observed live `admins-mctl-api` revision rather than the bootstrap template pin). No deployment before its own T7-T11-equivalent fixture results. Owner: mctlhq/mctl-api.
- [ ] B6. Later consumers (Glovo, SeerrSense, Alice), each with its own issue (depends on D2).

## Tests

Phase 0 (`mctlhq/.github`, unittest):

- [ ] T1. `matrix.py` rejects a matrix with: a `real_host_verified` or `failed` cell missing any evidence field; a `failed` or `blocked` cell without `cause`; a `documented` claim without URL and date; a `transport` or `fixture` status copied into `observed`.
- [ ] T2. Canonical digest across hosts and routes (P1-AP-R2-01):
  - T2a. Same (app, release), `direct` on two core hosts with different `bundle_sha256` marked `real_host_verified`: rejected.
  - T2b. Same (app, release), `cf-portal` digest differs, `server_served_sha256` equals the release digest, `observed: failed`, `cause: portal_limit`: accepted; `cf-portal` reported NO-GO and unsupported for the release; G1 stays GO.
  - T2c. Same as T2b but `cause` other than `portal_limit`, or the cell marked `real_host_verified`, or `server_served_sha256` differing: rejected, or G1 NO-GO with `server_defect`/`bundle_defect`.
  - T2d. Two `releases` entries for one (app, release), or two digests both on supported routes: rejected. Different digests across different releases are accepted. `grok-bot` never counts toward a gate.
- [ ] T3. `conformance.py` validates messages with `jsonschema.Draft202012Validator` against the vendored schema and passes the conformant log; it fails a log with `initialized` before the initialize result, a View-to-host `tools/list`, a `tool-result` carrying `name`, or an unknown method; it treats host-to-View `tools/list` (app tools) as legal and records it as a separate row.
- [ ] T4. `conformance.py` rejects any log tagged `static_hypothesis` as evidence, and fails (not skips) when `jsonschema` is unavailable or the vendored schema's SHA-256 does not match `SOURCE`.
- [ ] T5. The sanitisation scan fails artifacts containing `Bearer `, JWT-shaped strings, `code=`, an email address or a phone number. `bundle_scan.py` flags its patterns, but its result alone never changes a gate.
- [ ] T6. The SpikeDefinition validates with `proposed`, no `decision`, and the three outcomes.
- [ ] T15. Oracle corpus (P2-AP-R2-02): every valid corpus instance passes and every mutated instance fails under the oracle; where `lint.py` returns pass or fail it must equal the oracle on every instance, and any disagreement fails the test; an instance using a keyword `lint.py` does not implement makes lint abstain and the oracle decides.
- [ ] T16. Gate scope and D1 evaluator (P2-AP-R2-05): (a) all three core hosts G2/G3 GO on `direct`, G1/G4/G5/G6 GO, `cf-portal` `portal_limit` -> ADOPT_* computed and `cf-portal` listed unsupported; (b) B1 fixture pass with zero real hosts -> G5 UNMEASURED, no verdict; (c) one core host BLOCKED_BY_HOST -> DEFER with bounded partial result; (d) G6 per-instance GO but a missing per-host audit trace for a core host with G2 GO -> G6 UNMEASURED; (e) Grok Bot GO or NO-GO never changes the result.

Specified now, implemented in product repos (B1, B2, B3, B5):

- [ ] T7. Enumeration on the PoC instance with a raw MCP client: `tools/list` equals the `core-readonly` allowlist and `resources/list` equals `{ui://mctl-telegram/triage}`; fails on any extra tool whatever its `readOnlyHint`, including `draft_reply`, `get_media` and admin reads.
- [ ] T8. Raw `tools/call` for every tool in the full server registry outside the allowlist, and for unknown method names, is refused, both through the App path (fixture host) and directly.
- [ ] T9. Fail-closed configuration: startup or preflight refuses `MCP_TOOL_FILTER=readonly` (typo) and an unset filter; an unknown value reaching `toolPassesFilter` directly (unit test); `ALLOW_SEND=true`; a scope ceiling wider than read; an extra resource; a `ui.domain` entry missing doc URL, access date or measured-need reference.
- [ ] T10. Authorization: static resource refused without authentication and served with it, carrying no user data; user-data calls without read scope, cross-account (answered like not-found), stale or replayed, or after `revoke_session` are denied; each for model- and UI-originated calls; revocation latency asserted against the measured current bound.
- [ ] T11. Audit for the same read is identical for both origins apart from an untrusted origin annotation; a forged origin hint does not change the decision.
- [ ] T12. Browser fixture (B1) on the actual bundle bytes with SHA-256 asserted: handshake order; render on `{}`; refresh and filter re-call read tools; `host-context-changed` applies theme and dimensions; teardown and no-teardown leave no error; controls for unadvertised capabilities absent; DOM and screenshot assertions; the recorded log passes `conformance.py`.
- [ ] T13. Malformed, unknown-method, wrong-source and oversized messages, and script-like Telegram text, are inert: nothing rendered as HTML, no tool called; Telegram text never enters `ui/message` or `ui/update-model-context`.
- [ ] T14. Headless golden test: `content[].text` byte-equal with `MCP_APPS_ENABLED` on and off for every App-linked tool.
- [ ] T17. `ui.domain` selection (P2-AP-R2-03, B2): with the default empty allowlist no resource carries `ui.domain`; an unbound DCR client, a CIMD client whose host is in `OAUTH_CIMD_ALLOWED_HOSTS` but has no entry, a client matching two entries, and a forged `clientInfo.name` or user agent all yield no `ui.domain`; a reviewed entry for an exact bound client yields exactly its documented value for that route's server URL and nothing for the other route; the `resources/read` content bytes are identical in every case.

## Rollback

- Phase 0: revert the single PR in `mctlhq/.github`. No runtime, GitOps or tenant is touched. If the CI step is flaky, remove only its `workflow-tests.yml` entry.
- B1 and B2: revert the mctl-telegram PRs. With `MCP_APPS_ENABLED` unset the App surface is off (default false in `internal/config/config.go`); the new filter value is unused unless set; the `ui.domain` allowlist is empty by default.
- B3: revert the mctl-gitops PR, which removes the isolated deployment; clean up the throwaway account per the runbook.
- B5: the mctl-api feature flag defined in that issue.
- A DEFER or UNMEASURED outcome leaves the artifacts as the recorded measurement.
