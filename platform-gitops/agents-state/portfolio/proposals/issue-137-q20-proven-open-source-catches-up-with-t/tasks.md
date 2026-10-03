# Tasks: issue-137-q20-proven-open-source-catches-up-with-t

Precondition: `src/content/journal/2026-10-03-q19-weekly-sunday-snapshot-and-org-drift-report.md` is `status: complete` on `main`. If any journal entry is still `in_progress`, the build fails on two open entries; stop and report rather than editing it.

- [ ] 1. In `src/i18n/ui.ts`, replace `RUN_ITEMS_EN[3]`, `RUN_ITEMS_EN[4]`, `RUN_ITEMS_RU[3]`, `RUN_ITEMS_RU[4]` with the strings in design.md section A. — DoD: `git diff src/i18n/ui.ts` shows exactly four changed lines; `STACK_EXTRA`, header comment and capabilities bodies untouched.
- [ ] 2. In `src/data/stack-evidence.json`, rewrite items 4 and 5 and `ignored_components` exactly as in design.md section B. — DoD: file parses; thirteen items; item names equal `ui.detailsStackItems.en`.
- [ ] 3. In `scripts/org-drift.mjs`, replace the `IGNORED_REPOS` line with the multi-line array from design.md section C, each new entry carrying its reason comment. — DoD: no other line of the file changed.
- [ ] 4. (depends on 2) Update `EXPECTED` in `test/org-drift.test.ts` for items 4, 5 and `ignored_components`, with a comment beside `ignored_components` giving the reasons for `forgejo`, `zitadel`, `reflector`. — DoD: the existing Q19 content test passes.
- [ ] 5. (depends on 3, 4) Re-run `gh repo list mctlhq --limit 200 --json name,isArchived,isPrivate,isFork` and the three bootstrap directory listings; if they differ from design.md "Current state" only by repositories that are archived, or by files already covered/ignored, use the live result; if a new non-archived uncarded repository or uncovered component appeared, stop and report. Add the fixture and tests T2-T5 to `test/org-drift.test.ts`. — DoD: tests pass.
- [ ] 6. (depends on 1) Add T1 to `test/ui.test.ts` and the index 3/4 assertions to the existing test in `test/approach.test.ts`. — DoD: tests pass.
- [ ] 7. Add the journal entry from design.md section E, copy verbatim, at `src/content/journal/<YYYY-MM-DD>-q20-proven-open-source-catches-up-with-the-platform.md` (implementation date). — DoD: entry validates (`status: in_progress`, `issue_opened_at: '2026-10-03T16:45:28Z'`, no pr/release fields); `test/title.test.ts` passes.
- [ ] 8. (depends on 1-7) Run `npm run build`. — DoD: build, `npm test` and `check-no-metrics` pass. No lockfile change is expected; if one appears, revert it.

## Tests

- [ ] T1. `test/ui.test.ts`: `ui.detailsRunItems.en/ru` have nine entries; `[3]`/`[4]` equal `CloudNativePG, Valkey and MinIO` / `VictoriaMetrics, Grafana, Loki and OpenTelemetry` (en) and `CloudNativePG, Valkey и MinIO` / `VictoriaMetrics, Grafana, Loki и OpenTelemetry` (ru); `ui.detailsStackItems.en/ru` have thirteen with the same strings at `[3]`/`[4]`.
- [ ] T2. `test/org-drift.test.ts`: `IGNORED_REPOS` deep-equals `['.github', 'portfolio', 'mctl-rule', 'mctl-web', 'mctl-docs', 'mctl-claude-remote', 'mctl-alice', 'projects-mcp', 'newton-mcp-gateway', 'mctl-pairdesk']`.
- [ ] T3. `computeDrift` over the dated live fixture (org listing, cards parsed from `src/content/projects/*.en.md`, all evidence `present`, live bootstrap stems) deep-equals `{ uncardedRepos: [{ name: 'mctl-agent', private: false, fork: false }], staleCards: [], missingEvidence: [], candidateComponents: [], unknown: [] }`.
- [ ] T4. For each of `mctl-web`, `mctl-docs`, `mctl-claude-remote`, `mctl-alice`, `projects-mcp`, `newton-mcp-gateway`, `mctl-pairdesk`: splice it out of `IGNORED_REPOS` (restore in `finally`), run T3's fixture, assert the name appears in `uncardedRepos`.
- [ ] T5. For each of `valkey`, `minio`, `otel-collector` (removed from a deep copy of the evidence `covers`) and `forgejo`, `zitadel`, `reflector` (removed from a copy of `ignored_components`): T3's fixture reports that name in `candidateComponents`.
- [ ] T6. Existing tests unchanged and passing: `test/approach.test.ts` prefix/length test, `test/ui.test.ts` capabilities body pins, the `converged()` drift tests.

## Rollback

Revert the merge commit on `main` (one PR touching `src/i18n/ui.ts`, `src/data/stack-evidence.json`, `scripts/org-drift.mjs`, three test files and one journal entry) and let release-please cut the next patch; redeploy through `mctl_deploy_service` per the normal release path, or `mctl_rollback_service` to the previous image tag if the release is already out. The next weekly drift report would then list the six components and eight repositories again, which is the pre-change state and harmless.
