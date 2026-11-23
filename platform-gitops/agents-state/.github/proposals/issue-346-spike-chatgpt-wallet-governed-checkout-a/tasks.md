# Tasks: issue-346-spike-chatgpt-wallet-governed-checkout-a

- [ ] 1. Pin evidence. Record the 40-hex `main` heads of mctlhq/.github, mctl-api, mctl-agents,
  mctl-telegram and mctl-gitops on the run date. Re-read the GitHub state of #173, #181, #308,
  mctl-api#546, #548, #549, #569, #570, #989, #1004 and #1012, and mctl-telegram#1002 and #1088.
  DoD: the pins table is in the report. Every issue has an observed state and date, or an explicit
  "not read" entry.
- [ ] 2. D1 baseline and dedup map (depends on 1). DoD: there is a table with one row per contract
  listed in design.md. Each row has a status (`implemented | feature-flagged | proposed |
  unavailable | unknown`) and a citation. A separate "covered by #549, not decided here" table
  exists, and no row scores rails. agents-state-only rows are marked proposal-reported.
- [ ] 3. D2 vendor facts matrix. DoD: every row from design.md has a URL, an access date and a tag
  (`documented | tested | proposed | unknown`). Pages that could not be fetched say `unknown`.
  "ChatGPT Wallet merchant compatibility" and "hypothetical MCTL wallet API" are separate rows.
- [ ] 4. D4 sequence diagram, field tables and state diagram (depends on 2). DoD: the Payment Intent,
  Consent and merchant-confirmation tables map each field to an existing ADR 020, `aar_` or WorkItem
  field, or mark it `DELTA`. Order state and finance state are separate. Browser completion is never
  a terminal success. No credential or token field exists.
- [ ] 5. D5 threat and failure matrix plus synthetic table-top traces (depends on 4). DoD: every
  case in the requirements has a row with signal, outcome and control. There are at least five
  traces. Every possibly-charged case reconciles and never retries. Unverifiable merchant state
  fails closed.
- [ ] 6. D3 option comparison and eligibility/compliance section (depends on 2, 3, 4, 5). DoD:
  options A to D are scored on the same eight criteria, each with failure reasons. PCI, SCA,
  region, category and retention cells are filled or `unsupported`.
- [ ] 7. D6 ownership map, smallest next step and falsifiable assertions (depends on 6). DoD: every
  `DELTA` has an existing owner repository. There is no new Wallet service. There is one next step
  or an explicit DEFER with a re-entry trigger. Every assertion names its refuting evidence. Exactly
  one proposed verdict is stated as not decided.
- [ ] 8. Add `roadmap/spikes/chatgpt-wallet-agentic-checkout.yaml` (`lifecycle: proposed`, issue
  #346, five outcomes, `execution.devloop: true`, `evidence.report`, no `decision`, no `spec.epic`)
  and one `AGENTS.md` "Spikes" bullet (depends on 7). DoD: the validator passes and the diff touches
  only these three files.
- [ ] 9. Open the research PR with `Refs mctlhq/.github#346` (no closing keyword) and an `Agent:`
  trailer on every commit, as AGENTS.md requires (depends on 8). DoD: the PR is open for owner
  review. Nothing is approved, merged or closed by the agent.

## Tests

- [ ] T1. `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes with the new manifest.
- [ ] T2. `python -m pytest roadmap/tests/test_validate_spike.py roadmap/tests/test_validate.py` passes.
- [ ] T3. `git diff --name-only origin/main` lists exactly the report, the manifest and `AGENTS.md`.
  `roadmap/epics/agent-commerce.yaml` is unchanged.
- [ ] T4. A grep of the report for a closing keyword next to `#346`, and for `decidedBy` or
  `lifecycle: decided` in the manifest, returns nothing.
- [ ] T5. Any card-like digit string in the report fails the Luhn check. No real-looking PAN, token
  or secret is present.
- [ ] T6. Manual check: every D2 row has a URL and an access date, and every D1 row has a citation
  and status tag.

## Rollback

The change is documentation and one manifest. Revert the research PR, or delete the three added or
changed lines and files, and re-run T1. No runtime, data, tenant or GitOps state is affected, so no
other rollback is needed. If the owner rejects the framing, set the manifest to `archived` or remove
it through a separately reviewed PR.
