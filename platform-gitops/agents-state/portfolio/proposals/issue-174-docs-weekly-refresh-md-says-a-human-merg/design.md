# Design: issue-174-docs-weekly-refresh-md-says-a-human-merg

## Current state

- `docs/weekly-refresh.md`, section "Snapshot pull request", is one paragraph.
  It describes `npm run metrics`, the guard step, the `fix/weekly-snapshot`
  branch, auto-merge of the snapshot pull request, and then says
  "release-please then opens a patch release pull request, which a human still
  merges, so the deploy decision stays manual. The pull request is not a
  DevLoop cycle and adds no journal entry." Nothing in `test/` or `scripts/`
  asserts on this sentence (`grep` for "human still merges" / "deploy decision"
  hits only the doc; `scripts/org-drift.mjs` only links the file).
- `.github/workflows/release-please.yml` on `main` (commit `75d6dd5`) runs
  `googleapis/release-please-action@v5` with an App token, then dispatches
  mctl-gitops `release-deploy.yaml` when `release_created` and
  `vars.MCTL_ONBOARDED == 'true'`. It has no auto-merge step yet. PR #173
  (`ci/auto-release-snapshot`, open, touches only that file) adds the
  snapshot-only classification the issue describes.
- Journal: `src/content/journal/` holds 34 entries, all `status: complete`;
  the latest is `2026-10-04-q22-temporal-is-the-weekly-trigger.md` (issue
  #150, `indexing: noindex`, a `seoTitle` of the form "<title> — Dmitrii
  Mashkov"). Schema in `src/content.config.ts` (`journalSchema`), cross-field
  rules in `src/lib/journal.ts` (`statusEvidenceProblems`: `in_progress`
  forbids `release`/`released_at`/`deployed_at`; `checkJournalCollection`: at
  most one `in_progress`; `checkIssueStampOrder`: `issue_opened_at`
  nondecreasing in issue number). `docs/journal.md` says a cycle creates its
  own entry as `in_progress` and journal-closure completes it after release.
  `test/title.test.ts` caps titles at 65 characters (warning) / 75 (failure).
- Issue #174 `createdAt` (via `gh issue view`): `2026-10-25T00:09:44Z`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/portfolio/values.yaml`: exists, image tag
  `0.1.46`; service is onboarded in tenant `labs`, consistent with the
  `release-deploy` dispatch in `release-please.yml`. Not otherwise relevant:
  this change is documentation and a journal entry only.
- `gh pr view 173 -R mctlhq/portfolio`: open, unmerged, files
  `.github/workflows/release-please.yml` only.
- mctl MCP tools were not called; nothing about runtime configuration changes.

## Proposed solution

1. Replace the single release sentence in `docs/weekly-refresh.md` with the
   paragraph text fixed in requirements.md (AC1). It names the two conditions
   (changes since the last release limited to `src/data/metrics.json` and
   `.github/**`; release PR limited to the four release files), the auto-merge
   with a merge commit and its remaining gates, the no-human-step deploy, the
   human merge plus auto-merge revocation for every other release, and the
   fail-closed rule. It deliberately omits rename handling, serialization and
   the SHA pin: those are workflow internals the issue says not to restate.
   The sentence "The pull request is not a DevLoop cycle and adds no journal
   entry." stays and still refers to the snapshot pull request.
2. Add `src/content/journal/2026-10-25-q23-snapshot-releases-merge-themselves.md`
   with the exact frontmatter in requirements.md, `status: in_progress`,
   numbered Q23 after Q22, following the Q22 entry's shape. journal-closure
   completes it after release.

## Alternatives

- Rewrite the whole "Snapshot pull request" section or add a new "Release"
  section: rejected, the issue asks for the sentence to be rewritten, short.
- Restate the workflow's full classification (renames, compare status,
  serialization, SHA pin): rejected by the issue ("do not restate the workflow
  line by line"); the workflow file is the source of truth.
- Fold this doc change into #173: not possible, `docs/` is implementer-owned
  under ADR-0001 while `release-please.yml` is human-reserved.

## Platform impact

- No migration, no runtime or resource impact; `docs/` is not part of the
  built site. The journal entry is public but `noindex`, matching recent
  entries.
- Risk: merging before #173 makes the doc describe behavior that is not live.
  Mitigation: reviewer step to confirm #173 has merged first.
- Risk: the release for this PR touches `docs/` and `src/content/journal/`, so
  under #173 it is not snapshot-only and needs a human merge. That is expected.
- Risk: a second `in_progress` entry would fail the build; there are none
  today.
