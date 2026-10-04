# Tasks: issue-150-q22-temporal-is-the-weekly-trigger-vault

- [ ] 1. Remove the `schedule:` block (and its `cron:` line) from `.github/workflows/weekly-refresh.yml`, leaving `on:\n  workflow_dispatch:` followed by a blank line and `permissions:`; update the top comment as in design.md without the strings `schedule:` or `cron:` — DoD: the file has no `schedule:` key and no `cron:` key; all jobs and steps byte-identical.
- [ ] 2. Replace the first case of `test/weekly-refresh-workflow.test.ts` with `workflow_dispatch is the only trigger; no schedule or cron` (depends on 1) — DoD: asserts the `on:` block is exactly `workflow_dispatch`, and `doesNotMatch` for `/^\s*schedule\s*:/m` and `/^\s*-?\s*cron\s*:/m`; other cases unchanged and passing.
- [ ] 3. Rewrite the `## Schedule` section of `docs/weekly-refresh.md` with the text in design.md — DoD: names `dispatch-mctlhq-portfolio-weekly-refresh-schedule`, Sunday 10:01 UTC, the `scheduled-dispatch-failed` issue in `mctlhq/portfolio`, that manual `workflow_dispatch` still works, and why the GitHub schedule was removed; no mention of 08:00 remains as the current schedule.
- [ ] 4. Add `vault-human-auth-iac` after `vault-netpol` in the Vault item's `covers` in `src/data/stack-evidence.json`, and the same in `EXPECTED` in `test/org-drift.test.ts` — DoD: deep-equal test passes; `ignored_components` unchanged; `src/i18n/ui.ts` untouched.
- [ ] 5. In `test/org-drift.test.ts` add `LIVE_BOOTSTRAP_2026_10_04`, give `liveFixture` a defaulted `bootstrap` parameter, and add the two new cases from design.md (depends on 4) — DoD: the covered case reports `candidateComponents` `[]`; the removal case reports `['vault-human-auth-iac']`; existing cases unchanged and passing.
- [ ] 6. Create `src/content/journal/2026-10-04-q22-temporal-is-the-weekly-trigger.md` with the frontmatter in design.md copied character for character — DoD: `status: in_progress`, no pr/release/merged/released/deployed fields, one intervention; `npm run build` passes the journal loader checks.
- [ ] 7. Run `npm test` and `npm run build` (depends on 1-6) — DoD: both pass.

## Tests
- [ ] T1. `test/weekly-refresh-workflow.test.ts`: the new trigger case passes on the edited workflow and fails if `schedule:\n    - cron: '0 8 * * 0'` is reinserted under `on:` (verify locally, do not commit the reinsertion).
- [ ] T2. `test/org-drift.test.ts`: `stack-evidence.json has the specified content...` passes with the new `covers` entry.
- [ ] T3. `test/org-drift.test.ts`: `over the 2026-10-04 bootstrap listing vault-human-auth-iac is covered, not a candidate` passes.
- [ ] T4. `test/org-drift.test.ts`: `removing vault-human-auth-iac from the evidence covers makes it a candidate` passes.
- [ ] T5. Existing case `over the 2026-10-03 organisation the only drift is the one repository awaiting its rename` still passes unchanged.
- [ ] T6. Journal tests and `npm run build` accept the new in_progress entry (single in_progress, issue stamp order).

## Rollback
Revert the merge commit of the implementation PR and release a patch. That restores the GitHub cron, the old test, docs and evidence. The Temporal Schedule in mctl-agents is unaffected either way and keeps dispatching through `workflow_dispatch`; if the revert is permanent, disable the Temporal Schedule in mctl-agents to avoid two triggers, and mark the journal entry `abandoned` through a normal proposal if the cycle is cancelled.
