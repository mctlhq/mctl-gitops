# Tasks: issue-315-spike-evaluate-a-governed-product-intell

- [ ] 1. Pin the evidence. Record 40-hex commits for mctlhq/.github, mctl-telegram, mctl-agents, mctl-api and mctl-gitops, plus the deployed `labs/mctl-telegram` image tag (0.123.2 when this proposal was written). Read:
  - mctl-telegram `internal/digest/digest.go`, `internal/mcp/tools.go` (`get_acquisition_report`), `internal/connectfunnel/connectfunnel.go`, `docs/runbook.md` "Connect funnel" and `docs/product-updates/acquisition-report.yaml`;
  - the #902 and #1072 proposals under `agents-state/mctl-telegram/proposals/`;
  - the state of mctl-telegram#912;
  - `services/admins/umami/values.yaml`;
  - the scheduled-agent mechanisms in mctl-agents.

  — DoD: a pins table is in the report. Every unread source is `unknown (not observed)`.
- [ ] 2. Build the D1 capability/gap/dedup matrix (depends on 1). Cover #18, #20, #21, #22, #309, mctl-agents#242, mctl-telegram#902/#912/#1072, the daily digest, `get_acquisition_report`, Umami, the mentor digest and the agent CronWorkflows. Each row gets a status class, read path/scope, freshness, data class, owner and evidence tag. — DoD: no closed issue or merged proposal is classed as deployed without deployed evidence.
- [ ] 3. Write D2, the historical activation case (depends on 1). It must contain:
  - the #1072 figures with their denominator and snapshot date;
  - derived values labelled as derived;
  - a separate #902 table;
  - every explanation listed as `hypothesis, untested`;
  - the pre-capture source status checked against the capture epoch;
  - a verdict of reproduced or `unverifiable in this spike`.

  — DoD: no #902 count is combined with a #1072 count.
- [ ] 4. Write `docs/spikes/product-intelligence-loop/opportunity-card.schema.json` (JSON Schema 2020-12) with the required fields and enums from design.md. The status enum must not contain any approval value. — DoD: the schema compiles under `jsonschema==4.25.1` (`Draft202012Validator.check_schema`).
- [ ] 5. Write the synthetic fixtures under `docs/spikes/product-intelligence-loop/fixtures/` and a `README.md` (depends on 4):
  - `activation-snapshot.synthetic.json`;
  - `github-issue-snapshot.synthetic.json`, with #902/#912/#1072, decoys and one injected-instruction body;
  - `cases.json` with the six controls (true positive, #912 duplicate, false causality, missing source, privacy boundary, prompt injection) and the expected card for each.

  — DoD: each expected card validates against the schema. No real user ids, phone numbers, message text, tokens or secrets appear.
- [ ] 6. Write D3 (the example Opportunity Card for 12/32) and D4 (the architecture sketch and pipeline, with deterministic/model/human ownership and authority boundaries marked) (depends on 3, 4). — DoD: the example card has `status: duplicate` (or `insufficient_evidence`) and names #902/#912/#1072 as existing work. The sketch shows no Scout write path and no DevLoop trigger or approval by the Scout.
- [ ] 7. Write D5 (deterministic-first analysis) and D6 (privacy, tenant and authority model, with the trust-boundary map and the Product Scout versus Telegram Recruiter Assistant split) (depends on 2). — DoD: D6 states the minimum cell size, banned data classes, the no-cross-tenant rule, the absence of write credentials, budget/kill-switch carriers and injection defenses, each mapped to an existing control or an explicit gap with an owner repo.
- [ ] 8. Write D7 (the feedback contract via `wi_`/`aar_`/content digest, per the #306 report) and D8 (the baseline versus candidate scoring plan and the negative-control protocol) (depends on 5, 6). — DoD: every metric has a definition and a result or `not measured`.
- [ ] 9. Write D9: the options matrix, the bounded unit economics and exactly one proposed verdict from the four outcomes, with alternatives and owner repos for follow-ups (none filed) (depends on 2-8). If the verdict is `BOUNDED_PRODUCT_SCOUT_PILOT`, add the 14-day timebox, cost cap, data-access preflight, kill switch and success/failure criteria. — DoD: the verdict cites D1-D8 evidence. The decision rules in design.md are applied as written.
- [ ] 10. Assemble `docs/spikes/product-intelligence-loop.md` from tasks 1-9: non-claims, evidence tags, pins, D1-D9 (depends on 9). — DoD: the file exists, and every factual claim carries an evidence tag.
- [ ] 11. Add `roadmap/spikes/product-intelligence-loop.yaml` with:
  - owner `mctlhq/.github` and issue `mctlhq/.github#315`;
  - the four outcomes;
  - `lifecycle: proposed`, `execution.devloop: true`, `evidence.report: docs/spikes/product-intelligence-loop.md`;
  - no `decision` and no `epic`;
  - a header comment saying the owner records the decision and that no production data access is authorized.

  — DoD: `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes.
- [ ] 12. Add one bullet under `# Spikes` in `AGENTS.md` linking the report for mctlhq/.github#315, with the proposed verdict (depends on 10). — DoD: the link resolves.

## Tests

- [ ] T1. `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` exits 0, and `python3 -m pytest roadmap/tests/test_validate_spike.py` passes.
- [ ] T2. A schema check: run `python3 -I` with `jsonschema` to validate the schema itself (`check_schema`) and every expected card in `fixtures/cases.json` against it. An intentionally invalid card (`status: approved`) is rejected.
- [ ] T3. Six negative controls are present in `cases.json`, each with an expected status:
  - #912 duplicate gives `duplicate`;
  - missing source gives `insufficient_evidence` with `unknown_counts` populated;
  - false causality gives a hypothesis-only card with no uplift claim;
  - privacy gives a refusal of user-level rows;
  - injection gives inert text with no instruction followed;
  - true positive gives `for_owner_triage`.
- [ ] T4. A privacy grep over the new files finds no phone-number patterns, Telegram numeric user ids other than issue numbers, tokens (`ghp_`, `sk-`, `Bearer`) or message bodies.
- [ ] T5. A report review checklist confirms:
  - the #902 and #1072 populations are never merged;
  - 12/32 is labelled descriptive;
  - exactly one of the four outcomes is proposed;
  - no follow-up issue was opened;
  - no EpicDefinition was changed.

## Rollback

All changes are documentation, design artifacts and one `proposed` SpikeDefinition, and nothing is deployed. To roll back, revert the PR; that removes `docs/spikes/product-intelligence-loop.md`, `docs/spikes/product-intelligence-loop/`, `roadmap/spikes/product-intelligence-loop.yaml` and the `AGENTS.md` bullet. No runtime state, credential or flag needs reverting.
