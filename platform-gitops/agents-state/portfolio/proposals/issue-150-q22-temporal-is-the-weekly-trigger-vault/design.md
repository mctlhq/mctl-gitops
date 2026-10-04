# Design: issue-150-q22-temporal-is-the-weekly-trigger-vault

## Current state
- `.github/workflows/weekly-refresh.yml` declares two triggers:
  ```yaml
  on:
    schedule:
      - cron: '0 8 * * 0'
    workflow_dispatch:
  ```
  followed by `permissions: contents: read`, a `weekly-refresh-${{ github.repository }}` concurrency group and one `refresh` job (snapshot, changed-files guard, push, auto-merge PR, `node scripts/org-drift.mjs`).
- `test/weekly-refresh-workflow.test.ts` is a text-level test (no YAML parser). Its first case, `triggers on the Sunday 08:00 UTC cron and on workflow_dispatch`, asserts `/schedule:\s*\n\s*- cron: '0 8 \* \* 0'/` and `/workflow_dispatch:\s*\n\s*\n?permissions:/`. It therefore requires the cron today.
- `docs/weekly-refresh.md` has a `## Schedule` section: "Every Sunday at 08:00 UTC (`cron: '0 8 * * 0'`) and on manual dispatch." The `## Manual run` section shows `gh workflow run weekly-refresh.yml -R mctlhq/portfolio`.
- `src/data/stack-evidence.json` item 3, `"HashiCorp Vault with External Secrets"`, has `covers: ["vault", "vault-auto-unseal", "vault-backup", "vault-netpol", "external-secrets"]`; `ignored_components` is `["image-prune", "local-path-provisioner", "academy-postgres-datasource", "eval-candidates", "eval-namespace", "forgejo", "zitadel", "reflector"]`.
- `test/org-drift.test.ts` holds an `EXPECTED` literal deep-equal to the JSON and to `ui.detailsStackItems.en` by item text. `LIVE_BOOTSTRAP` is the 2026-10-03 bootstrap listing; `liveFixture(ev = evidence)` combines it with `LIVE_ORG_2026_10_03` and the real project cards. The case `over the 2026-10-03 organisation the only drift is the one repository awaiting its rename` asserts `computeDrift(liveFixture())` equals `EMPTY` plus one uncarded repo. Loops check that removing `valkey`/`minio`/`otel-collector` from covers, or `forgejo`/`zitadel`/`reflector` from `ignored_components`, yields a candidate. `computeDrift` (in `scripts/org-drift.mjs`) reports any `bootstrapFiles` name that is in no item's `covers` and not in `ignored_components` as a candidate.
- Journal: `src/content.config.ts` `journalSchema` (strict) requires `service`, `issue`, `proposal_slug`, `status`, `visibility`, `title`/`decided` bilingual, `issue_opened_at`; `in_progress` forbids `release`/`released_at`/`deployed_at` (`src/lib/journal.ts`). The loader allows at most one `in_progress` entry and requires `issue_opened_at` to increase with issue number per repository (#141 Q21 is `2026-10-03T20:42:30Z`; #150 was opened `2026-10-04T10:17:16Z`). All current entries are `complete`. The Q19 entry `2026-10-03-q19-weekly-sunday-snapshot-and-org-drift-report.md` already records the 05:00 to 08:00 move. `docs/journal.md`: a cycle creates its own entry with `status: in_progress`; closure is done later by the journal-closure workflow.

## Proposed solution
1. Workflow trigger. In `weekly-refresh.yml` replace the `on:` block with
   ```yaml
   on:
     workflow_dispatch:
   ```
   and extend the top comment to: `# Weekly snapshot refresh and org drift report. Dispatched weekly by the mctl-agents Temporal Schedule; see docs/weekly-refresh.md.` The comment must not contain the text `schedule:` or `cron:`. Nothing else in the file changes. This file is not reserved under AGENTS.md (only `claude-review.yml`, `release-please.yml`, `dependabot.yml` are).

2. Workflow test. Replace the first case of `test/weekly-refresh-workflow.test.ts` with
   `test('workflow_dispatch is the only trigger; no schedule or cron', ...)` asserting:
   - `assert.match(workflow, /\non:\n  workflow_dispatch:\n\npermissions:/)` (the `on:` block holds exactly `workflow_dispatch`);
   - `assert.doesNotMatch(workflow, /^\s*schedule\s*:/m)`;
   - `assert.doesNotMatch(workflow, /^\s*-?\s*cron\s*:/m)`.
   All other cases stay unchanged.

3. Docs. Replace the `## Schedule` section body of `docs/weekly-refresh.md` with:

   > The mctl-agents Temporal Schedule `dispatch-mctlhq-portfolio-weekly-refresh-schedule` dispatches this workflow every Sunday at 10:01 UTC through `workflow_dispatch`, then checks that a run appeared. If the dispatch fails or no run appears, it opens an issue labelled `scheduled-dispatch-failed` in `mctlhq/portfolio`. The schedule lives in mctl-agents (mctl-agents#559 and #560, released in mctl-agents 1.65.0); changing the time is a change there, not here.
   >
   > The workflow has no GitHub Actions `schedule:` trigger. GitHub runs `schedule` on a best-effort basis and drops a slot without notice: on Sunday 2026-10-04 neither `0 5 * * 0` nor `0 8 * * 0` produced a run. A second, silent trigger would look like a backstop without being one, so `test/weekly-refresh-workflow.test.ts` fails if one is added back.
   >
   > A manual `workflow_dispatch` (see Manual run) still works at any time.

   The `## Operator setup` list stays as it is. How the dispatcher labels its failure issue is mctl-agents behaviour and out of scope here.

4. Stack evidence. In `src/data/stack-evidence.json` set the Vault item's `covers` to `["vault", "vault-auto-unseal", "vault-backup", "vault-netpol", "vault-human-auth-iac", "external-secrets"]`. Keep the one-item-per-line formatting. `ignored_components` unchanged. Mirror the same change in `EXPECTED` in `test/org-drift.test.ts`.

5. Drift unit cases in `test/org-drift.test.ts`:
   - Add `const LIVE_BOOTSTRAP_2026_10_04 = [...LIVE_BOOTSTRAP, 'vault-human-auth-iac'];` with a comment: `// The 2026-10-04 bootstrap listing: 2026-10-03 plus vault-human-auth-iac (Terraform for Vault's human auth).`
   - Give `liveFixture` an optional second parameter `bootstrap: string[] = LIVE_BOOTSTRAP` used for `bootstrapFiles`, so existing callers are unchanged.
   - `test('over the 2026-10-04 bootstrap listing vault-human-auth-iac is covered, not a candidate', ...)`: `assert.deepEqual(computeDrift(liveFixture(evidence, LIVE_BOOTSTRAP_2026_10_04)).candidateComponents, [])`.
   - `test('removing vault-human-auth-iac from the evidence covers makes it a candidate', ...)`: deep-clone evidence, filter it out of every `covers`, assert `candidateComponents` deep-equals `['vault-human-auth-iac']`.
   - Also assert in the first new case that `evidence.ignored_components` does not include `vault-human-auth-iac`.

6. Journal entry `src/content/journal/2026-10-04-q22-temporal-is-the-weekly-trigger.md` with exactly this frontmatter (and no body):
   ```yaml
   ---
   service: portfolio
   issue: https://github.com/mctlhq/portfolio/issues/150
   proposal_slug: issue-150-q22-temporal-is-the-weekly-trigger-vault
   status: in_progress
   visibility: public
   indexing: noindex
   title:
     en: "Q22: Temporal is the weekly trigger"
     ru: "Q22: еженедельный запуск переходит на Temporal"
   seoTitle: "Temporal is the weekly trigger — Dmitrii Mashkov"
   decided:
     en: "The weekly refresh no longer relies on GitHub's scheduler. On its first Sunday, GitHub dropped both scheduled slots without a word, so the trigger moved to a weekly schedule in the platform's Temporal control plane, which starts the workflow, checks that a run actually appeared and opens an issue in this repository when it did not. Its first run that same morning refreshed the snapshot as intended. The GitHub schedule is removed rather than kept as a backstop, because a trigger that can fail silently only looks like one, and a test now fails if it is added back. The same run's drift report found Terraform for Vault's human sign-in in the platform's GitOps repository; it is part of Vault, so it is now counted under the existing Vault line. No visible copy changed."
     ru: "Еженедельное обновление больше не зависит от планировщика GitHub. В первое же воскресенье GitHub молча пропустил оба запланированных слота, поэтому запуск перенесён в еженедельное расписание в Temporal — управляющем контуре платформы: оно запускает workflow, проверяет, что запуск действительно появился, и открывает issue в этом репозитории, если нет. Первый же запуск тем утром обновил снимок как положено. Расписание GitHub удалено, а не оставлено запасным вариантом: триггер, который может молча не сработать, лишь похож на запасной, а тест теперь падает, если его вернуть. Отчёт о расхождениях того же запуска нашёл в GitOps-репозитории платформы Terraform для входа людей в Vault; это часть Vault, поэтому теперь он учтён в существующей строке Vault. Видимые тексты не менялись."
   interventions:
     - what: "moved the weekly-refresh trigger from the GitHub Actions schedule to the mctl-agents Temporal Schedule dispatch-mctlhq-portfolio-weekly-refresh-schedule (Sunday 10:01 UTC), built in https://github.com/mctlhq/mctl-agents/issues/559 and https://github.com/mctlhq/mctl-agents/issues/560 and released in https://github.com/mctlhq/mctl-agents/releases/tag/1.65.0"
       why: "on 2026-10-04 the GitHub schedule fired in neither the 05:00 nor the 08:00 UTC slot; GitHub documents schedule as best-effort and silent when a slot is dropped. The schedule's first fire dispatched run 37193997890, which succeeded"
       at: '2026-10-04T10:01:00Z'
   issue_opened_at: '2026-10-04T10:17:16Z'
   ---
   ```
   `pr`, `merged_at`, `release`, `released_at` are filled later by the journal-closure workflow. The copy above is the contract; the implementer copies it character for character.

Why this way: the issue's goal is a single source of truth for the trigger, so deleting the cron (rather than disabling it) is the minimum change; the text-level test matches the existing style of the file; covering under the existing Vault item keeps `ui.detailsStackItems` and therefore the rendered site unchanged; extending `liveFixture` with a defaulted parameter avoids touching the existing 2026-10-03 assertion.

## Alternatives
- Keep the GitHub cron as a backstop alongside Temporal. Rejected by the issue: two sources of truth, and a trigger that fails silently looks like a backstop without being one; it could also double-run on a week where both fire (the concurrency group only serialises, it does not dedupe).
- Add `vault-human-auth-iac` to `ignored_components`. Rejected: it is part of Vault, not out of scope, and ignoring it would misdescribe the platform.
- Replace `LIVE_BOOTSTRAP` in place with the 2026-10-04 listing instead of adding a second constant. Workable, but it rewrites a dated snapshot; a separate dated constant keeps the 2026-10-03 evidence intact and makes the new case self-explanatory.
- Parse the workflow YAML in the test. Rejected: the test file deliberately uses text checks with no YAML dependency.

## Platform impact
- No migration. No runtime, nginx, Dockerfile or rendered-copy change; the built site differs only by the new journal entry (noindex) in journal listings.
- Backward compatibility: manual `gh workflow run weekly-refresh.yml` and the Temporal dispatcher both use `workflow_dispatch`, which is kept, so the dispatcher keeps working.
- Risk: if the Temporal Schedule stops, there is no GitHub fallback. Mitigation: the dispatcher opens a `scheduled-dispatch-failed` issue, documented in `docs/weekly-refresh.md`.
- Risk: the journal loader rejects a second `in_progress` entry or an out-of-order `issue_opened_at`. All current entries are complete and #150's stamp is later than #141's, so neither triggers.
- Risk: `EXPECTED` and the JSON drifting apart; the existing deep-equal test catches it.
