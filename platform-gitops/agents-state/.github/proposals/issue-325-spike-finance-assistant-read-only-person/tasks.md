# Tasks: issue-325-spike-finance-assistant-read-only-person

- [ ] 1. Pin evidence: record the 40-hex `main` heads of mctlhq/.github, mctl-telegram, mctl-api and mctl-gitops in the report's pin table — DoD: the table exists in `docs/spikes/finance-assistant.md` and every later `[CODE]`/`[CONFIG]` claim refers to one of these pins.
- [ ] 2. External primary sources (depends on 1): read the claude.com introduction article and the support.claude.com Personal Finance article. Read the Plaid, Open Banking UK and EEA PSD2/AISP sources, kept separate for Montenegro, the EEA and the UK — DoD: report section D1 quotes the sources with access dates. Every country/provider cell is `[PRIMARY]`-cited or `unknown`.
- [ ] 3. Current-state and dedup map (depends on 1): read the mctl-telegram files `internal/assistant/catalog.go` and `assistants/schemas/assistant-install.schema.json`, plus the observe-profile and audience-scope code and `docs/adr/0008-managed-runtime.md`. Read the mctl-api assistant catalog, the #1048 threat model, #1046, the #309 report if present, #181, #322 (`roadmap/epics/automation-control-plane.yaml`) and `roadmap/epics/telegram-managed-runtime.yaml` — DoD: the D2 table marks each capability implemented / flagged / proposed / missing / unknown with evidence. It explicitly answers whether owner-only, no-auto-reply, private-destination delivery is expressible today.
- [ ] 4. Product-surface (A/B/C) and data-source decision matrices (depends on 2, 3) — DoD: D3 and D4 are filled in. Personal vs family scope and DM vs group are evaluated. The report states that MCTL never collects bank passwords and never scrapes.
- [ ] 5. Identity, consent and data-flow diagrams, threat model and connector gating plan (depends on 3) — DoD: D5 has mermaid diagrams with explicit deny edges (group, peer, other tenant, shared memory, auto-reply) and the model-provider data flow. D6 has the threat table mapped to tests T7-T12 and to the #1048 gates.
- [ ] 6. Synthetic fixture `docs/spikes/finance-assistant/fixtures/` — DoD: the fixture contains the required cases (listed under Tests T1-T7) and a hand-computed `oracle.json` stored as Decimal strings. It contains no real data.
- [ ] 7. Reference model `docs/spikes/finance-assistant/model.py` (depends on 6) — DoD:
  - stdlib only, no network and no model calls, and it runs under `python3 -I`;
  - it implements normalize, dedupe, transfers, refunds, category spend, FX with provenance, duplicate-charge and recurring detection, `rules_digest`, the authorization grant model, the fenced job and the deny-by-default tool dispatch;
  - it fails closed with explicit uncertainty or error results.
- [ ] 8. Tests `docs/spikes/finance-assistant/tests/test_finance.py` (depends on 7) — DoD: T1-T12 pass locally with `python3 -I -m unittest discover -s docs/spikes/finance-assistant/tests -v`.
- [ ] 9. Baseline-vs-assistant comparison protocol (depends on 7) — DoD: the rules-only digest output is committed. The assistant prompt and rubric (grounded claims, ungrounded claims, numeric mismatches against the oracle, confirmation burden, latency, cost) are committed. The LLM run is reported `not-run` with its reason.
- [ ] 9a. Evidence ladder / safety assurance scope (depends on 3, 5, 8) — DoD: D0, D6 and D8 explicitly distinguish L0 pinned source inspection, L1 abstract offline `[MODEL]` results, L2 real application integration, L3 isolated preview and L4 production evidence. Show source/owner/gates for every `not-run` L2-L4 check, including tenant-owner principal binding, Telegram peer/group delivery, in-flight revocation, persistent delete/backup/logging, model-provider egress and bank-provider authorization. Never claim runtime isolation from a synthetic Grant test.
- [ ] 9b. Neutral verdict verification (depends on 2-9a and 10) — DoD: no option is labeled preferred in the report before D1-D10 evidence; D11 compares all four outcome rules and states contradicting evidence, missing facts and why the proposed verdict is warranted. A passed fixture alone cannot mean production or integration gates passed.
- [ ] 10. Cost, privacy, retention, revocation and incident matrix plus proactivity section (depends on 3, 5) — DoD: D9 has observed and estimated values in separate columns, using the #1088 caps as the budget frame. D10 is limited to the #322 control plane, on-demand first.
- [ ] 11. Decision record D11 (depends on 2-10 and 9a/9b) — DoD:
  - exactly one proposed outcome, chosen by the decision rules in design.md;
  - rejected alternatives with reasons;
  - the smallest follow-up, described but not created;
  - the responsible repository;
  - kill/exit criteria;
  - "owner decision required".
- [ ] 12. Manifest `roadmap/spikes/finance-assistant.yaml` — DoD: `lifecycle: proposed`, no `decision`, `epic` or `timebox`, and `evidence.report` points to the report. `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes.
- [ ] 13. Wiring (depends on 8, 12): add the `AGENTS.md` `## Spikes` entry. In `.github/workflows/workflow-tests.yml`, add the path to both `paths:` lists and the unittest step — DoD: the workflow file stays valid YAML and the new step runs green on the PR.
- [ ] 14. Open the PR to mctlhq/.github referencing #325 (refs only, not closing). Every commit carries an `Agent:` trailer — DoD: the PR is open, CI is green, and it is labelled for independent review. Nothing is approved or merged by the investigator.

## Tests

- [ ] T1. Month spend by category on posted, deduplicated rows equals `oracle.json` exactly (Decimal equality). Results are quantized to the currency minor unit.
- [ ] T2. Overlapping re-import: the same `(source, account, external id/hash)` is counted once, and is not flagged as a duplicate charge.
- [ ] T3. Two distinct same-merchant, same-amount charges on the same day are flagged `possible_duplicate_charge`, with a confidence and a reason.
- [ ] T4. FX: the USD card total is converted to EUR with the pinned rate, and the output carries `{rate, source, as_of}`. A missing rate gives an `uncertain` or error result. A stale rate (older than its allowed age) is refused. No float ever appears; this is checked by type.
- [ ] T5. A transfer between the owner's own EUR and USD accounts is excluded from spend. A refund nets against its original category. A pending payment is excluded from posted totals and listed separately.
- [ ] T6. The recurring subscription is detected by cadence and amount tolerance. The conflicting merchant category resolves to the owner correction, with the confidence recorded.
- [ ] T7. Adversarial merchant or memo text (an instruction to call `transfer_funds` or to change policy) is carried as inert data. It never reaches `dispatch` as a tool name, and it does not change the policy or the allowlist.
- [ ] T8. Authorization: the owner reads and receives their results. All of these are denied: a second user in the same tenant, a user in another tenant, an unauthorized Telegram peer, a group chat destination, and the auto-reply path.
- [ ] T9. Revoking or deleting a source while a job is in flight fences the job. Its delivery and its persist both fail with `fenced`, and no derived row survives.
- [ ] T10. `dispatch` denies every non-allowlisted tool by default (payment, transfer, trade, credit, outbound share, credential read). The allowlist is immutable at runtime.
- [ ] T11. Negative control: mutation-style checks. Removing the dedupe step, or switching to float arithmetic, makes T1/T2 fail. This proves that the oracle discriminates.
- [ ] T12. Fixture hygiene: no IBAN in the fixtures passes the ISO 13616 mod-97 check, and every merchant is from the synthetic list.
- [ ] T13. `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes with the new manifest.
- [ ] T14. Evidence-boundary negative control: prove the report marks real integration paths (`Telegram owner identity`, `group delivery`, `tenant DB isolation`, `backup/log deletion`, `provider egress`) as L2–L4 `not-run`, regardless of whether T1–T12 pass. The synthetic grant fixture must never be cited as proof of actual production enforcement.

## Rollback

All changes are additive documentation, fixtures, a test step and a manifest in mctlhq/.github.
To roll back:
- revert the PR, or delete `docs/spikes/finance-assistant*` and `roadmap/spikes/finance-assistant.yaml`;
- remove the `AGENTS.md` entry and the `workflow-tests.yml` path and step.

There is no runtime, data or flag state to undo. If the owner rejects the spike, set the manifest
to `archived` instead of deleting it, so the history stays readable.
