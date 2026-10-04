# Q22: Temporal is the weekly trigger; Vault covers its human-auth IaC

## Context
Q19 (#129) scheduled `.github/workflows/weekly-refresh.yml` with a GitHub Actions `schedule:` trigger. On Sunday 2026-10-04 neither the original `0 5 * * 0` slot nor the `0 8 * * 0` slot it was moved to (a recorded operator intervention in the Q19 journal entry) produced a run. GitHub documents `schedule` as best-effort and silent when a slot is dropped. The weekly trigger now lives in the mctl-agents Temporal control plane (mctl-agents#559, #560, released in mctl-agents 1.65.0): the Temporal Schedule `dispatch-mctlhq-portfolio-weekly-refresh-schedule` fires every Sunday at 10:01 UTC, dispatches this workflow through `workflow_dispatch`, verifies that a run appeared, and opens a `scheduled-dispatch-failed` issue in `mctlhq/portfolio` if it cannot. Its first fire on 2026-10-04 dispatched run 37193997890, which succeeded (snapshot PR #148, release 0.1.41).

The same run's drift report (#134) listed one new bootstrap component, `vault-human-auth-iac`: Terraform that configures Vault's human auth, added to mctl-gitops on 2026-10-04. It is part of Vault, not a separate product, so it belongs in the `covers` list of the "HashiCorp Vault with External Secrets" item of `src/data/stack-evidence.json`. This proposal removes the GitHub cron so there is exactly one source of truth for the weekly trigger, pins that in tests and docs, covers the new component under Vault, and records the trigger move as an operator intervention in this cycle's journal entry. No user-facing site copy changes apart from the new journal entry itself.

## User stories
- AS the site owner I WANT the weekly refresh to have exactly one trigger, the Temporal Schedule SO THAT a silently dropped GitHub cron slot cannot pass for a backstop.
- AS a maintainer I WANT a test that fails when a `schedule:` trigger is added back SO THAT a second source of truth cannot return unnoticed.
- AS an operator reading `docs/weekly-refresh.md` I WANT to learn what dispatches the run, when, and where failures surface SO THAT I know where to look when a Sunday run is missing.
- AS the owner reading the weekly drift issue I WANT `vault-human-auth-iac` accounted for under Vault SO THAT the report stops listing it as a candidate.
- AS a journal reader I WANT this cycle's entry to record that the trigger moved to Temporal SO THAT the manual intervention is on record with its evidence.

## Acceptance criteria (EARS)
- THE SYSTEM SHALL declare `workflow_dispatch:` as the only trigger under `on:` in `.github/workflows/weekly-refresh.yml`, with no `schedule:` key and no `cron:` entry anywhere in the file.
- WHEN `npm test` runs THE SYSTEM SHALL execute a case in `test/weekly-refresh-workflow.test.ts` that asserts `workflow_dispatch:` is present and that no line of the workflow matches `^\s*schedule\s*:` and no `cron:` key is present; IF a `schedule:` trigger is added back THEN that case SHALL fail.
- THE SYSTEM SHALL keep every other assertion in `test/weekly-refresh-workflow.test.ts` (permissions, concurrency, tokens, guard, snapshot branch, drift step) passing unchanged; no job or step of the workflow changes.
- THE SYSTEM SHALL replace the `## Schedule` section of `docs/weekly-refresh.md` with text stating that: the run is dispatched weekly by the mctl-agents Temporal Schedule `dispatch-mctlhq-portfolio-weekly-refresh-schedule` every Sunday at 10:01 UTC; the schedule verifies a run appeared and, if dispatch fails, opens a `scheduled-dispatch-failed` issue in `mctlhq/portfolio`; a manual `workflow_dispatch` still works; and the GitHub Actions `schedule:` trigger was removed because it is best-effort and dropped both Sunday slots on 2026-10-04 without notice.
- THE SYSTEM SHALL list `vault-human-auth-iac` in the `covers` array of the item `"HashiCorp Vault with External Secrets"` in `src/data/stack-evidence.json`, immediately after `vault-netpol`, giving `["vault", "vault-auto-unseal", "vault-backup", "vault-netpol", "vault-human-auth-iac", "external-secrets"]`; the item's `item` text and `evidence` paths SHALL be unchanged.
- THE SYSTEM SHALL NOT list `vault-human-auth-iac` in `ignored_components`, which SHALL stay exactly `["image-prune", "local-path-provisioner", "academy-postgres-datasource", "eval-candidates", "eval-namespace", "forgejo", "zitadel", "reflector"]`.
- THE SYSTEM SHALL keep `EXPECTED` in `test/org-drift.test.ts` equal to the committed `src/data/stack-evidence.json` (the existing deep-equal test), updated for the new `covers` entry.
- WHEN `computeDrift` runs over the live organisation fixture with a bootstrap listing that is the 2026-10-03 listing plus `vault-human-auth-iac` THE SYSTEM SHALL report `candidateComponents` equal to `[]` (a new unit case in `test/org-drift.test.ts`).
- IF `vault-human-auth-iac` is removed from every item's `covers` THEN `computeDrift` over that same listing SHALL report it in `candidateComponents` (a new unit case).
- THE SYSTEM SHALL leave `src/i18n/ui.ts` and every page template unchanged, so `ui.detailsStackItems` and all rendered site copy are identical before and after.
- THE SYSTEM SHALL add one journal entry `src/content/journal/2026-10-04-q22-temporal-is-the-weekly-trigger.md` with `status: in_progress`, `visibility: public`, `indexing: noindex`, `issue: https://github.com/mctlhq/portfolio/issues/150`, `proposal_slug: issue-150-q22-temporal-is-the-weekly-trigger-vault`, `issue_opened_at: '2026-10-04T10:17:16Z'`, no `pr`, `release`, `merged_at`, `released_at` or `deployed_at`, and the copy and intervention given verbatim in design.md.
- WHILE another journal entry is `in_progress` THE SYSTEM SHALL fail the build (existing loader rule); the new entry SHALL be the only `in_progress` entry.
- WHEN `npm test` and `npm run build` run THE SYSTEM SHALL pass.

## Out of scope
- Any change to the Temporal Schedule, mctl-agents, or mctl-gitops.
- Any change to the jobs or steps of `weekly-refresh.yml`, to `scripts/org-drift.mjs`, or to `scripts/snapshot-metrics.mjs`.
- Adding `vault-human-auth-iac` to `ignored_components`, adding new `evidence` paths, or adding a new item to the Proven open source list.
- Changing any site copy in `src/i18n/ui.ts` or any page; the only new user-facing text is the journal entry.
- Editing the completed Q19 journal entry; it already records the 05:00 to 08:00 move.
- The reserved files `.github/workflows/claude-review.yml`, `.github/workflows/release-please.yml`, `.github/dependabot.yml`.

## Open questions
- The issue does not supply journal copy (title, `decided` in EN and RU) although the issue contract requires it for user-facing text. This proposal supplies the copy in design.md; the reviewer should check it before approval.
- The issue does not give the exact time of the move to Temporal. The intervention `at` uses `2026-10-04T10:01:00Z`, the first fire of the Temporal Schedule. Adjust before approval if a more precise operator timestamp is known.
- The issue calls mctl-agents#559 and #560 by number without saying whether they are issues or pull requests; the entry links them as `https://github.com/mctlhq/mctl-agents/issues/559` and `.../issues/560`, which GitHub redirects to a pull request when the number is one.
