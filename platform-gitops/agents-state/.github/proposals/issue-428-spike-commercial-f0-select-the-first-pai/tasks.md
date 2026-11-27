# Tasks: issue-428-spike-commercial-f0-select-the-first-pai

- [ ] 1. Record evidence pins (40-hex main heads) for .github, mctl-telegram, mctl-academy, mctl-api and mctl-gitops, and the gitops `[CONFIG]` reads for `services/labs/mctl-academy` and `services/labs/mctl-telegram`. DoD: D1 table filled, and any unread source marked `unknown (not observed)`.
- [ ] 2. Write D0 (non-claims, evidence tags, ladder) and D2 (inventory and readiness of the nine candidates, with gates #429, #1197, merchant of record and #616) (depends on 1). DoD: every candidate has an owner repo, a state and a blocker list.
- [ ] 3. Write D3, the competitor table for the eleven named alternatives, from primary sources with access dates or `unknown`. DoD: no fee or license is stated without a `[PRIMARY]` source and date, and basic checks are marked commoditized.
- [ ] 4. Write D4 (ranked matrix with explicit weights) and D5 (unit economics, contribution margin, cost ceiling) (depends on 2, 3). DoD: every cell is tagged, and the ranking can be reproduced from the stated weights.
- [ ] 5. Optional: add `docs/spikes/commercial-f0-first-offer/score.py` (stdlib only) plus a fixture and a test that recompute D4 and D5 (depends on 4). DoD: `python3 -I score.py fixture.json` reproduces the report's ranking.
- [ ] 6. Write D6, the conversation protocol for 5 voluntary owner-run conversations, with consent text and an anonymized template, all records `not-run`. DoD: no personal-data fields, and a statement that nothing is sent automatically.
- [ ] 7. Write D7 (ONE SKU, price hypothesis, scope, refund policy, cost ceiling, comparison against direct alternatives, measurable GO/PIVOT/STOP criteria) and D8 (proposed verdict, follow-ups) (depends on 4, 6). DoD: exactly one SKU, and every owner gate listed (pricing, outreach, charging, building).
- [ ] 8. Add `roadmap/spikes/commercial-f0-first-offer.yaml` (`SpikeDefinition`, `lifecycle: proposed`, issue mctlhq/.github#428, outcomes GO/PIVOT/STOP, `evidence.report`) and one `AGENTS.md` Spikes line (depends on 7). DoD: validation passes.

## Tests
- [ ] T1. `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes with the new manifest.
- [ ] T2. `python3 -m pytest roadmap/tests/test_validate_spike.py` still passes.
- [ ] T3. If task 5 is done: its unit test checks that the ranking order and margins match the D4 and D5 tables.
- [ ] T4. A grep of the report finds no email address, phone number or personal handle, and every conversation record is `not-run`.
- [ ] T5. The diff touches only `docs/spikes/commercial-f0-first-offer*`, `roadmap/spikes/commercial-f0-first-offer.yaml` and `AGENTS.md`.

## Rollback
Revert the PR. It is documentation and a manifest only, so nothing in production, gitops or billing changes, and no external party was contacted.
