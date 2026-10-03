# Tasks: issue-129-q19-weekly-sunday-snapshot-and-org-drift

Precondition (operator, not a task): mctlhq/portfolio#116 (Q17 closure) is
merged, so `src/content/journal/2026-09-14-q17-issue-opened-at-from-a-recorded-source.md`
is no longer `in_progress`. Do not edit that entry. If it is still
`in_progress` on `main`, the build fails on two open entries; stop and report
rather than working around it.

- [ ] 1. Create `src/data/stack-evidence.json` with exactly the content in
  design.md section 3. — DoD: file parses; 13 items whose `item` strings equal
  `ui.detailsStackItems.en` in order; no change to `src/i18n/ui.ts`.
- [ ] 2. Create `scripts/org-drift.mjs` (depends on 1): constants, pure
  `computeDrift`, `isNoDrift`, `renderIssueBody`, `cardsFromMarkdown`,
  `classifyEvidence`; I/O helpers `ghRequest`, `listOrgRepos`,
  `listBootstrapFiles`, `syncDriftIssue` (all accepting `fetchImpl`); `main()`
  and the hybrid `isEntryPoint()` guard copied from
  `scripts/snapshot-metrics.mjs`. — DoD: matches design.md section 2,
  including the verbatim issue body; any failed read becomes an `unknown`
  entry and sets exit code 1; a later-page failure rejects the whole listing;
  `node scripts/org-drift.mjs` with no tokens exits 1 with a clear message.
- [ ] 3. Create `.github/workflows/weekly-refresh.yml` as in design.md
  section 1 (header comment linking `docs/weekly-refresh.md`; PR body
  verbatim). — DoD: only `contents: read` permission; two App-token steps
  with the `bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0` pin; guard
  step before the push step; `--auto --merge`; drift step condition
  `!cancelled() && steps.snapshot.outcome == 'success'`.
- [ ] 4. Create `test/org-drift.test.ts` (depends on 1, 2) with the cases in
  design.md section 4. — DoD: all pass; each mutated-fixture test asserts the
  whole drift object so removing the matching `computeDrift` branch fails it.
- [ ] 5. Create `test/weekly-refresh-workflow.test.ts` (depends on 3) with the
  assertions in design.md section 4. — DoD: all pass; covers AC1-AC5.
- [ ] 6. Append `test/org-drift.test.ts test/weekly-refresh-workflow.test.ts`
  to the `node --test` list in the `package.json` `test` script (depends on
  4, 5). No dependency changes, so `package-lock.json` is untouched. — DoD:
  `npm test` runs both files.
- [ ] 7. Write `docs/weekly-refresh.md` covering every topic in design.md
  section 5. — DoD: names the schedule, both tokens and why, PR and
  auto-merge path with the human-merged release PR, drift issue lifecycle,
  stack-evidence sync rule, manual run command, operator setup.
- [ ] 8. Add the journal entry from design.md section 6 under
  `src/content/journal/<YYYY-MM-DD>-q19-weekly-sunday-snapshot-and-org-drift-report.md`,
  copy verbatim. — DoD: entry validates (`status: in_progress`,
  `issue_opened_at: '2026-10-03T13:26:15Z'`, no pr/release fields).
- [ ] 9. Run `npm run build` (runs `npm run vendor && npm test` via
  `prebuild`) and `git diff --exit-code -- public/assets src/data/assets.json`.
  — DoD: both pass; `src/data/metrics.json` and `scripts/snapshot-metrics.mjs`
  are unchanged in the diff.

## Tests

- [ ] T1. Workflow: cron `'0 5 * * 0'` and `workflow_dispatch` present (AC1).
- [ ] T2. Workflow: single `permissions` grant `contents: read`; every
  App-token step pinned to `bcd2ba4...3eb1` (AC2).
- [ ] T3. Workflow: read-token step has `owner: mctlhq`, no `repositories`,
  only `permission-contents: read`; write-token step has
  `repositories: portfolio` and contents/pull-requests/issues write (AC3).
- [ ] T4. Workflow: guard step (`git status --porcelain`) precedes the
  `git push` step (AC4).
- [ ] T5. Workflow: `fix(metrics): weekly snapshot` title with UTC date,
  branch `fix/weekly-snapshot`, `--auto --merge`, no `--squash`/`--rebase`
  (AC5).
- [ ] T6. Evidence file equals section C and its items equal
  `ui.detailsStackItems.en` in order (AC6).
- [ ] T7. Converged fixture -> no drift; uncarded repo, archived carded repo,
  evidence 404 -> exactly one entry each (AC7).
- [ ] T8. One unknown evidence read -> `Unknown` entry, not "no drift"; failed
  org listing and failed bootstrap listing -> `Unknown` (AC8).
- [ ] T9. Injected fetch: page 2 of the org listing fails -> rejection, not
  page 1's repos (AC9).
- [ ] T10. `renderIssueBody` full-string snapshot; empty sections omitted;
  throws on no drift (AC10).
- [ ] T11. `syncDriftIssue`: create / update / comment+close / no-op paths,
  PRs ignored in the issue listing.
- [ ] T12. `test/entry-point.test.ts` picks up `scripts/org-drift.mjs`
  automatically and passes; `npm run build` passes (AC11).

Reviewer steps (not acceptance criteria): after merge and operator setup,
run `gh workflow run weekly-refresh.yml -R mctlhq/portfolio` once and check the
snapshot PR, its auto-merge state and the `weekly-drift` issue.

## Rollback

Revert the implementation PR (merge-commit revert) through a normal PR: this
removes the workflow, script, evidence file, tests and docs; nothing else
depends on them. To stop runs immediately without a revert, disable the
workflow (`gh workflow disable weekly-refresh.yml -R mctlhq/portfolio`). Close
any open `fix/weekly-snapshot` PR and delete the branch; close the
`weekly-drift` issue by hand. A bad snapshot already merged is corrected by a
new `npm run metrics` PR or by reverting that merge; the deploy itself only
happens when a human merges the release PR, and an already-deployed release
can be rolled back with `mctl_rollback_service`.
