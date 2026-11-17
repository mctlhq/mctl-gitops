# Tasks: issue-208-spike-should-mctl-docs-or-the-devloop-im

- [ ] 1. Write the duplicate map in `context/plans/migration-conflict-spike.md`, covering mctl-gitops#1044, mctl-agents#918, mctl-gitops#2506, `docs/guides/databases.md`, `docs/guides/scaffolding.md`, the base-service `dbInitJob`, and the migration patterns visible in gitops (advisory-locked migrate-on-start in mctl-support, `dbInitJob` in mctl-academy and mctl-telegram) — DoD: every entry is classified duplicate, adjacent, or unrelated with a reason, and unknown per-service migration tools are marked `unknown`.
- [ ] 2. Set up the scratch experiment repo (outside mctl-docs and never against shared CNPG) with a plain-SQL runner, base migration `0001`, and scenario branch pairs (a) duplicate version, (b) order-dependent DDL, (c) silent divergence (depends on 1) — DoD: each pair merges with no Git conflict.
- [ ] 3. Add the baseline per-branch apply job and the candidate PR-only merge-ref job (apply to `postgres:17`, duplicate-prefix check, `pg_dump --schema-only` diff against a committed `schema.sql`) (depends on 2) — DoD: both jobs run green on the base branch.
- [ ] 4. Run each scenario 5 times under baseline and candidate, and record success, latency, Actions minutes, and false positives and negatives in the spike report, with unmeasured values as `unknown` (depends on 3) — DoD: a complete results table plus the stale-merge-ref finding.
- [ ] 5. Record one recommendation from the Outcomes in the spike report, plus follow-up issue drafts (for example an mctl-agents check linked to #918) as text only (depends on 4) — DoD: exactly one recommendation, no code outside mctl-docs.
- [ ] 6. Only if task 4 shows at least one scenario that escapes the baseline and is caught by the candidate: add `## Schema migrations and parallel PRs` to `docs/guides/databases.md` (depends on 5) — DoD: the section covers the three failure shapes, states that mctl does not run or order tenant migrations, and links to the scaffolding snippet.
- [ ] 7. Under the same condition: add `## Pre-merge migration check (optional)` to `docs/guides/scaffolding.md` after "Pre-merge docker build (recommended)", with a PR-only job, a `postgres:17` service container, a tool-agnostic apply placeholder, and the `needs:` and up-to-date-branch caveats (depends on 6) — DoD: the snippet is valid YAML and the wording says it is opt-in tenant CI.
- [ ] 8. Run `bun run generate:llms` and `bun run build` (depends on 6, 7, or on 5 if no docs change) — DoD: the build passes and `docs/public/llms-full.txt` includes the new sections when they were added.

## Tests

- [ ] T1. `bun run build` passes (runs `bun run test`, `generate:llms`, `vitepress build docs`).
- [ ] T2. In the scratch repo, the candidate job fails on scenarios (a), (b), and (c) and passes on the base branch and on a non-conflicting pair. Results are recorded in the spike report.
- [ ] T3. Manual review: no new docs text claims that mctl, `deploy-service`, or DevLoop runs or enforces the migration check. A grep for "migration" in the changed pages is checked by hand.
- [ ] T4. The new section anchors render, and the link from `databases.md` to the scaffolding section resolves in `vitepress preview`.

## Rollback

All changes are additive Markdown in mctl-docs (`context/plans/migration-conflict-spike.md`, and conditionally new sections in `docs/guides/databases.md` and `docs/guides/scaffolding.md`, plus the regenerated `docs/public/llms-full.txt`). To roll back, revert the PR and tag a new patch release. The tag push redeploys the previous content through the normal CI/GitOps flow. The scratch experiment repo can be deleted without affecting any tenant or platform state.
