# docs: weekly-refresh.md describes when a release merges itself

## Context

The "Snapshot pull request" section of `docs/weekly-refresh.md` ends its
description of the weekly snapshot with: "release-please then opens a patch
release pull request, which a human still merges, so the deploy decision stays
manual." Pull request mctlhq/portfolio#173 (branch `ci/auto-release-snapshot`,
still open when this proposal was written) changes
`.github/workflows/release-please.yml` so that a snapshot-only release pull
request merges itself. Once #173 is on `main`, that sentence is false.

Issue #174 asks for that sentence to be rewritten so it says when a release
merges itself, when it keeps a human merge, and that a check which cannot be
read counts as manual. It must stay short and in the document's style, and must
not restate the workflow line by line. The cycle also adds the usual journal
entry. The workflow itself is out of scope: it is reserved wiring under
ADR-0001 and #173 already changes it.

## User stories

- AS an operator reading `docs/weekly-refresh.md` I WANT the document to say which releases merge and deploy without me SO THAT I know which release pull requests still need my merge.
- AS a reader of the journal I WANT this cycle recorded like every other one SO THAT lead time and interventions stay complete.

## Acceptance criteria (EARS)

Exact replacement text (AC1). In `docs/weekly-refresh.md`, the sentence
"release-please then opens a patch release pull request, which a human still
merges, so the deploy decision stays manual." is replaced by this paragraph
text, wrapped at about 78 columns like the rest of the file, staying inside the
same paragraph of the "Snapshot pull request" section, between the sentence
ending "a requested-changes review holds it." and the sentence "The pull
request is not a DevLoop cycle and adds no journal entry.":

```
release-please then opens a patch release pull request. If nothing has
changed since the last release except `src/data/metrics.json` and
`.github/**`, and the release pull request touches only `CHANGELOG.md`,
`.release-please-manifest.json`, `package.json` and `package-lock.json`,
`.github/workflows/release-please.yml` enables auto-merge on it with a merge
commit. It still waits for the `build` check and an approving review, and
merging it tags and deploys the release with no human step. Every other
release keeps a human merge, and the workflow revokes auto-merge on the open
release pull request before release-please updates it. A check that cannot
be read, or returns a malformed, empty or truncated answer, counts as not
snapshot-only, so that release stays manual.
```

- WHEN the change is applied THE SYSTEM SHALL contain the AC1 text in `docs/weekly-refresh.md` (ignoring line wrapping) and SHALL NOT contain the phrase "which a human still merges".
- WHEN the change is applied THE SYSTEM SHALL leave every other section and sentence of `docs/weekly-refresh.md` unchanged, including "The pull request is not a DevLoop cycle and adds no journal entry." and the sections Schedule, Tokens, Drift issue, Keeping `src/data/stack-evidence.json` in sync, Manual run and Operator setup.
- WHEN the change is applied THE SYSTEM SHALL contain exactly one new journal entry `src/content/journal/2026-10-25-q23-snapshot-releases-merge-themselves.md` with this frontmatter, character for character, and no body:

```
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/174
proposal_slug: issue-174-docs-weekly-refresh-md-says-a-human-merg
status: in_progress
visibility: public
indexing: noindex
title:
  en: "Q23: Snapshot releases merge themselves"
  ru: "Q23: релизы снимка сливаются сами"
seoTitle: "Snapshot releases merge themselves — Dmitrii Mashkov"
decided:
  en: "A release that carries nothing but the weekly metrics snapshot no longer waits for a human merge. When only the snapshot and the repository's own automation changed since the last release, and the release pull request touches only the release files, it merges itself once the build check and a review pass, and the site deploys without a manual step. Every other release still needs a human to merge it, and a check that cannot be read counts as one of those. The weekly refresh guide now says so. No visible copy changed."
  ru: "Релиз, в котором нет ничего, кроме еженедельного снимка метрик, больше не ждёт, пока его сольёт человек. Если с прошлого релиза изменились только снимок и автоматизация самого репозитория, а pull request релиза затрагивает только файлы релиза, он сливается сам после проверки сборки и ревью, и сайт выкатывается без ручного шага. Любой другой релиз по-прежнему сливает человек, и проверка, которую не удалось прочитать, тоже относит релиз к ним. Руководство по еженедельному обновлению теперь говорит об этом. Видимые тексты не менялись."
issue_opened_at: '2026-10-25T00:09:44Z'
interventions: []
---
```

- WHILE the new entry has `status: in_progress` THE SYSTEM SHALL carry no `release`, `released_at` or `deployed_at` field on it (rule in `statusEvidenceProblems`, `src/lib/journal.ts`), and no `pr` or `merged_at` field, because neither is known when the implementer commits.
- WHEN `npm test` and `npm run build` run THE SYSTEM SHALL pass, including the journal loader's at-most-one-`in_progress` check (`checkJournalCollection`) and the issue-stamp-order check (`checkIssueStampOrder`).
- IF the change set touches any path under `.github/` THEN THE SYSTEM SHALL be considered out of contract; the diff is limited to `docs/weekly-refresh.md` and the new journal file.

Reviewer step (not an acceptance criterion): before merging, a human confirms
that mctlhq/portfolio#173 has merged to `main`, so the document does not
describe behavior that is not live yet.

## Out of scope

- `.github/**`, including `.github/workflows/release-please.yml`: reserved wiring under ADR-0001, already changed in #173.
- Any change to `.github/workflows/weekly-refresh.yml` or to the mctl-agents Temporal Schedule `dispatch-mctlhq-portfolio-weekly-refresh-schedule`.
- Any other document, including `docs/journal.md` (closure-PR releases touch `src/content/journal/**`, so they are not snapshot-only and its "release owner merges" text stays true).
- Site copy, templates, `src/i18n/ui.ts`, `src/data/metrics.json`.

## Open questions

- #173 was still open (not merged) on 2026-10-25. This proposal assumes it merges with the classification the issue describes. If #173 lands with different rules, the AC1 text must be revised before this PR merges.
- Whether #173 itself is a manual intervention for this cycle's journal. It edits a human-reserved file (`release-please.yml`), which AGENTS.md permits, so the entry records `interventions: []`. A reviewer who sees it otherwise can add an intervention during closure.
