# Tasks: issue-258-spike-agent-ui-evaluate-ag-ui-1-0-as-mct

- [ ] 1. Pin the sources. Shallow-clone mctl-api, mctl-agents, mctl-portal and
  mctl-gitops at their current `main`, and `ag-ui-protocol/ag-ui` at its 1.0 release
  tag. Record each 40-hex commit and the read date. DoD: an evidence-pin table exists
  in `docs/spikes/agent-ui-ag-ui.md`, with a "not observed" list for anything that
  could not be read.
- [ ] 2. D1 inventory (depends on 1). Read the mctl-api router and handlers for
  agents, dev-loop, executions, work-items, usage, human-input and action-approvals.
  Search for `text/event-stream` and `http.Flusher`. Read the `DevLoopWorkflow`
  signals, queries and phase fields in mctl-agents. Read the mctl-portal DevLoop and
  proposal views and their transport. DoD: one row per Q1 fact
  (`fact | source | surface | durable | user-authoritative | correlation id`), every
  row tagged `[CODE]`, `[DEPLOYED]`, `[DOC]` or `unknown (not observed)`, and no
  invented events.
- [ ] 3. D2 mapping matrix (depends on 1, 2). Map each MCTL concept to the pinned
  AG-UI 1.0 event types, marked exact, lossy or none, with where authority stays. Add
  a "does not fit" list. DoD: every row in the issue's minimum table is present, and
  each event name exists in the pinned schema.
- [ ] 4. D3 threat and governance boundary (depends on 2, 3). Draw the
  interrupt-to-resume sequence to `DecideActionApproval`, `ConsumeActionApproval` and
  the human-input API. Build a refusal table for stale, duplicate, wrong-actor,
  wrong-tenant, edited, reconnect-replay and injected-frontend-event cases, each
  naming the existing server check or the missing check. Add the frontend-tool
  classes (backend MCP, safe UI-only, consequential re-routed), the reasoning-event
  policy and prompt/tool-output injection handling. DoD: every Q3, Q4 and Q5
  requirement has a row with evidence.
- [ ] 5. D4 ownership (depends on 2, 4). Compare adapter-in-mctl-agents,
  adapter-in-mctl-api and library-only. Define auth, CORS/CSRF, SSE replay,
  retention, backpressure, correlation and scaling for the chosen shape. Name the
  owners of adapter, ingress, client and schema. DoD: no option introduces public
  ingress on the mctl-agents workers, and the comparison cites the worker values file
  with `ingress.enabled: false`.
- [ ] 6. Q7-Q9 (depends on 3). Frontend choice (plain AG-UI client vs CopilotKit,
  with mctl-portal, mctl-web and a test-client trade-off), the MCP Apps non-overlap
  scenario, and the versioning and `mctl.*` namespace policy. DoD: each question has
  a section with a decision.
- [ ] 7. D5 experiment design (depends on 4, 5, 6). Write the per-repository slices,
  fixture, ten proofs, negative tests and measurement list for the DevLoop Run
  Inspector. DoD: each proof names its test and pass condition. If the verdict is
  `REJECT_KEEP_CUSTOM`, this section only records why no experiment is built.
- [ ] 8. D6 verdict and D8 disposition (depends on 2-7). Select exactly one of each,
  with cited evidence and the conditions under which it would flip. DoD: one verdict
  token and one disposition token, and no new epic.
- [ ] 9. Add `roadmap/spikes/agent-ui-ag-ui.yaml`: `SpikeDefinition`, owner
  `mctlhq/.github`, `lifecycle: active`, `timebox.decisionBy: "2026-11-30"`, issue
  `mctlhq/.github#258`, the three outcomes, `execution.devloop: true`,
  `evidence.report: docs/spikes/agent-ui-ag-ui.md`, no `epic` or `decision`. DoD: the
  validator passes.
- [ ] 10. Add the `AGENTS.md` `# Spikes` bullet linking the report for
  mctlhq/.github#258. DoD: it matches the existing bullet style.

## Tests

- [ ] T1. `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes
  with the new manifest.
- [ ] T2. `python -m unittest discover -s roadmap/tests -p 'test_*.py'` passes.
- [ ] T3. Manual check: every AG-UI event name in the report appears in the pinned
  upstream 1.0 schema.
- [ ] T4. Manual check: every D1, D2 and D3 claim carries an evidence tag, and no
  payload bodies are quoted, only identifiers, digests and timestamps.
- [ ] T5. Manual check: the report contains exactly one D6 verdict and one D8
  disposition from the allowed sets, and the manifest's `outcomes` equal the D6 set.

## Rollback

The change touches documentation and the roadmap only. Revert the PR to remove
`docs/spikes/agent-ui-ag-ui.md`, `roadmap/spikes/agent-ui-ag-ui.yaml` and the
`AGENTS.md` line. No service, deployment or data is affected. If only the verdict is
wrong, amend the report in a follow-up PR. The owner records the final `decision`
separately.
