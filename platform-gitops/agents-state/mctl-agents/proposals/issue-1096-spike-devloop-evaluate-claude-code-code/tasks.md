# Tasks: issue-1096-spike-devloop-evaluate-claude-code-code

All tasks are read-only research and documentation. No Code Mode or CLI
experiment is run, and no settings, profiles, dependencies or gitops are
changed.

- [ ] 1. Pin sources: fetch the official Code Mode doc
  (code.claude.com/docs/en/code-mode), the Claude Code v2.1.323 release
  note, and the API Programmatic Tool Calling and Cloudflare Code Mode docs.
  Record URL, retrieval date, CLI version and the exact supported/unsupported
  surfaces. Label each claim `OFFICIAL`, `NEWS` or `VENDOR_CLAIM`. Note
  whether the CLI bundled with `claude-agent-sdk==0.2.174` reaches 2.1.323;
  unknown stays UNKNOWN. — DoD: a sources table exists in
  `docs/spikes/1096-claude-code-code-mode.md`, and every Code Mode statement
  in the report cites a row.
- [ ] 2. Inventory (depends on 1): document the SDK runners, the `PreToolUse`
  hooks in `orchestrator/options.py`, `policy_checkpoint`, `decision_records`,
  `execution_identity`, `capability_gateway`, `tracing`, `usage_ledger` and
  `redaction`. Cite paths and the pinned commit. Mark the interactive
  operator workflows UNKNOWN (no `.claude/` in the repo). — DoD: an
  inventory section exists, and every behavioural claim cites a path or says
  UNKNOWN.
- [ ] 3. Duplicate/ownership map: #597 (benchmark owner), #63 (PARK, M8
  FAIL, different executor, not reopened), #242/#517, #181/#151, #35/#165,
  #343. — DoD: a map section exists with one line per issue on what it owns
  and how #1096 differs.
- [ ] 4. Surface matrix (depends on 1, 2): write
  `docs/spikes/1096/surface-matrix.yaml` and the markdown table for the six
  surfaces. Dimensions: runtime, eligibility, hooks, limits, billing,
  audit, security and task fit, each with an `evidence_class` per cell.
  — DoD: the table and YAML agree, and the headless/SDK row states that it
  is not applicable unless officially supported.
- [ ] 5. Threat model and per-child governance (depends on 2, 4): one row per
  issue-listed threat, with existing control and status (`HOLDS_BY_DOC` /
  `UNKNOWN` / `GAP`). Then the per-child actor/tenant, args digest,
  action-time decision and durable record requirements, mapped to
  `execution_identity`, `policy_checkpoint.args_digest_of` and
  `decision_records`, with fail-closed treatment of unknowns. — DoD: every
  threat has a row, and every UNKNOWN feeds the recommendation's blocker
  list.
- [ ] 6. Benchmark protocol (depends on 4, 5): write
  `docs/spikes/1096/protocol.yaml` with pins, two modes, 3 tasks (A repo
  research, B CI-evidence fixture via read-only `gh` shim, C two fixture MCP
  sources), >=5 reps, independent oracles, failure cases, and metrics per
  the #597 / `tools/capability_bench.py` counting rules. — DoD: all results
  are `NOT_RUN`, and fixtures are synthetic/sanitized with digests recorded.
- [ ] 7. Negative matrix (depends on 5): write
  `docs/spikes/1096/negative-matrix.yaml` covering at least the 10 cases in
  design.md, modelled on the ADR 023 probe-harness fixture pattern. — DoD:
  each row has threat, fixture, expected, oracle and `status: NOT_RUN`.
- [ ] 8. Observability section (depends on 1, 5): list the checks on the
  `Ctrl+O` transcript, hook/tool-call visibility and OTel/`DISABLE_TELEMETRY`
  as `NOT_RUN`. Compare with the MCTL durable records. Propose redaction
  reusing `orchestrator/redaction.py`. — DoD: no telemetry support is
  asserted without a source.
- [ ] 9. Recommendation memo (depends on 3-8): give the provisional
  recommendation (`FURTHER_RESEARCH` for an operator CLI pilot, `REJECT` for
  headless/DevLoop transfer while unsupported). Name the gate, owner,
  expected cost (30 runs, price UNKNOWN until pinned), required evidence,
  permission review and hard blockers. Add cross-link notes for #597 and
  #181/#151. Set `STATUS: PENDING_EVIDENCE`. — DoD: the memo makes no CI or
  headless applicability claim, and the owner verdict is left blank.
- [ ] 10. Structural test (depends on 4, 6, 7): add
  `tests/test_spike_1096_protocol.py`. — DoD: it passes offline under
  `uv run pytest tests/test_spike_1096_protocol.py`.
- [ ] 11. Open the PR with `Refs mctlhq/mctl-agents#1096` (not `Closes`).
  — DoD: the issue stays open for the owner verdict.

## Tests

- [ ] T1. All three YAML files under `docs/spikes/1096/` parse with
  `yaml.safe_load`.
- [ ] T2. Every `result` / `status` value in `protocol.yaml` and
  `negative-matrix.yaml` equals `NOT_RUN`.
- [ ] T3. `protocol.yaml` has tasks A, B and C, each with an oracle and a
  non-empty `failure_cases`, and `reps >= 5`. Both modes reference the same
  `pins` block.
- [ ] T4. Each negative-matrix row has the non-empty keys `threat`,
  `fixture`, `expected` and `oracle`, and the row count is >= 10.
- [ ] T5. Each surface-matrix cell's `evidence_class` is in {`OFFICIAL`,
  `VENDOR_CLAIM`, `OBSERVED`, `UNKNOWN`}. No cell for the headless SDK
  surface claims Code Mode support with a class other than `OFFICIAL`.
- [ ] T6. No file under `docs/spikes/1096*` matches
  `orchestrator.redaction.contains_credential`.
- [ ] T7. The existing suite (`uv run pytest`) stays green. No runtime module
  changed.

## Rollback

Revert the single docs PR. Nothing is deployed, and no settings, profiles,
dependencies or gitops change, so a revert fully restores the prior state.
