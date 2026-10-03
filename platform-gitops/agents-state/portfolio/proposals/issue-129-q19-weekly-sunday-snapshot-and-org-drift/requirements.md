# Q19: weekly Sunday snapshot and org drift report

## Context

The home page Snapshot reads every number from `src/data/metrics.json`. That
file is produced by `scripts/snapshot-metrics.mjs` (`npm run metrics`), which
nothing runs on a schedule; the committed file was generated on
2026-09-26T12:39:12.541Z. Since then the `mctlhq` org has changed (repositories
archived, created and deleted) and nothing reports it. Two other lists on the
site are maintained by hand and drift the same way: the `/work/` project cards
(`src/content/projects/*.en.md`, field `repo`) and the "Proven open source"
list (`ui.detailsStackItems` in `src/i18n/ui.ts`, built from `RUN_ITEMS_EN` and
`STACK_EXTRA`).

This cycle adds one unattended GitHub Actions workflow,
`.github/workflows/weekly-refresh.yml`, that runs every Sunday at 05:00 UTC and
on manual dispatch. It (a) regenerates the snapshot and, when the file changed,
opens or updates one pull request containing only `src/data/metrics.json`,
titled so release-please cuts a patch release, with auto-merge enabled; and
(b) runs a new `scripts/org-drift.mjs` that compares the org and
`mctlhq/mctl-gitops` against the site's committed lists and keeps exactly one
open GitHub issue labelled `weekly-drift` describing the drift (or closes it
when there is none). A source that cannot be read fails the job and is
reported as unknown, never as "no drift". No visible site copy changes, apart
from the journal entry for this cycle.

## User stories

- AS the site owner I WANT the Snapshot numbers refreshed every week without
  anyone running `npm run metrics` SO THAT the home page never silently goes
  months stale.
- AS the site owner I WANT a single GitHub issue that lists where `/work/`
  cards and the "Proven open source" list no longer match the org and the
  platform SO THAT a later DevLoop cycle can act on concrete, current evidence.
- AS a reviewer I WANT a failed read to be reported as unknown and to fail the
  job SO THAT an outage is never mistaken for "everything matches".
- AS the release owner I WANT the snapshot PR to go through the normal `build`
  check, Claude review and release-please path SO THAT the deploy decision
  stays a human merge of the release PR.

## Acceptance criteria (EARS)

### Workflow `.github/workflows/weekly-refresh.yml`

- R1. THE SYSTEM SHALL trigger the workflow on `schedule` with cron
  `'0 5 * * 0'` and on `workflow_dispatch` with no inputs;
  `test/weekly-refresh-workflow.test.ts` SHALL assert both from the file text.
- R2. THE SYSTEM SHALL declare top-level `permissions:` with exactly one grant,
  `contents: read`, and no job-level `permissions:` block; every
  `actions/create-github-app-token` step SHALL be pinned to
  `bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0`; asserted by the
  workflow test.
- R3. THE SYSTEM SHALL declare
  `concurrency: { group: weekly-refresh-${{ github.repository }}, cancel-in-progress: false }`
  (written in block form like `journal-closure.yml`).
- R4. THE SYSTEM SHALL check out `main` (`persist-credentials: false`), run
  `actions/setup-node@v4` with `node-version: 24` (the major `build.yml`
  uses) and run `npm ci --no-audit --no-fund`.
- R5. THE SYSTEM SHALL mint a "read" token with `owner: mctlhq`, no
  `repositories:` key, `permission-contents: read` and no other
  `permission-*` key; asserted by the workflow test.
- R6. THE SYSTEM SHALL mint a "write" token with `owner: mctlhq`,
  `repositories: portfolio`, `permission-contents: write`,
  `permission-pull-requests: write`, `permission-issues: write`; asserted by
  the workflow test.
- R7. WHEN the snapshot step runs THE SYSTEM SHALL execute `npm run metrics`
  with `GH_TOKEN` set to the read token. IF it exits non-zero THEN the job
  SHALL fail and no commit, push, PR or drift step SHALL run; the workflow
  SHALL contain no fallback that writes `src/data/metrics.json` itself.
- R8. WHEN the snapshot step succeeds THE SYSTEM SHALL run a changed-files
  guard: IF `git status --porcelain` lists anything other than nothing or
  exactly ` M src/data/metrics.json` THEN the job SHALL fail before any
  `git push`. The workflow test SHALL assert the guard step precedes the push
  step.
- R9. IF `src/data/metrics.json` is unchanged THEN THE SYSTEM SHALL skip the
  commit, push, PR and auto-merge steps and emit a `::notice::` line.
- R10. WHEN `src/data/metrics.json` changed THE SYSTEM SHALL, with the write
  token, commit only that file on top of the checked-out `main` with message
  `fix(metrics): weekly snapshot YYYY-MM-DD` (UTC date of the run) and
  force-push it to the branch `fix/weekly-snapshot`.
- R11. WHEN no open PR exists with head `fix/weekly-snapshot` THE SYSTEM SHALL
  open one against `main` titled `fix(metrics): weekly snapshot YYYY-MM-DD`
  with the body given verbatim in design.md section "PR body"; WHEN one is
  already open THE SYSTEM SHALL leave it open (the force-push updates it).
- R12. THE SYSTEM SHALL enable auto-merge on that PR with
  `gh pr merge <N> --auto --merge`; the workflow SHALL contain neither
  `--squash` nor `--rebase`. R10-R12 (title format, branch, `--merge`) are
  asserted by the workflow test.
- R13. WHEN the snapshot step succeeded (whether or not the PR steps were
  skipped) THE SYSTEM SHALL run `node scripts/org-drift.mjs` with
  `GH_TOKEN` = read token and `GH_WRITE_TOKEN` = write token. IF the snapshot
  step failed THEN the drift step SHALL NOT run.

### Script `scripts/org-drift.mjs`

- R14. THE SYSTEM SHALL export pure functions `computeDrift({ orgRepos, cards,
  evidence, evidenceResults, bootstrapFiles })` and `renderIssueBody(drift,
  date)` and a `main()` doing all I/O, guarded by the same hybrid
  `isEntryPoint()` used in `scripts/snapshot-metrics.mjs` (so
  `test/entry-point.test.ts` covers it automatically).
- R15. THE SYSTEM SHALL report as "Repositories with no /work/ card" every
  non-archived org repository whose `https://github.com/mctlhq/<name>` is not
  the `repo` of any card and whose name is not in
  `IGNORED_REPOS = ['.github', 'portfolio', 'mctl-rule']`, annotated
  `(private)`, `(fork)` or `(private, fork)` when true.
- R16. THE SYSTEM SHALL report as "/work/ cards pointing at a repository that
  is archived or gone" every card whose repository is archived (`archived`)
  or absent from the org listing (`not found`).
- R17. THE SYSTEM SHALL report as "Stack evidence missing" every evidence
  entry whose result is `absent` (HTTP 404), with its stack item; and as
  "Platform components not on the 'Proven open source' list" every bootstrap
  basename that is in no item's `covers` and not in `ignored_components`.
- R18. IF the org listing (any page of it), any bootstrap directory listing or
  any evidence read is not definitively observed (network error, status other
  than 200/404 for evidence, any non-200 for listings, or a malformed body)
  THEN THE SYSTEM SHALL record it in an `Unknown` section naming the read and
  its error, SHALL NOT treat the result as "no drift", SHALL still post or
  update the drift issue, and `main()` SHALL exit 1.
- R19. IF page 2 (or later) of the org listing fails after earlier pages
  succeeded THEN THE SYSTEM SHALL treat the whole listing as a failed read,
  never as the earlier pages' repositories.
- R20. WHILE there is drift or any unknown read THE SYSTEM SHALL keep exactly
  one open issue labelled `weekly-drift` in `mctlhq/portfolio`: replace the
  body of the existing open one, otherwise create one titled
  `Weekly drift report` with label `weekly-drift`.
- R21. WHEN there is no drift and no unknown read THE SYSTEM SHALL, if an open
  `weekly-drift` issue exists, comment `No drift as of <YYYY-MM-DD>.` and
  close it with `state_reason: completed`; otherwise do nothing.
- R22. `renderIssueBody` SHALL produce exactly the structure in design.md
  section "Issue body", omitting sections with no entries; an all-empty
  report SHALL never be posted.
- R23. IF any write to the issue fails THEN `main()` SHALL exit 1.

### Data, tests, docs, journal

- R24. `src/data/stack-evidence.json` SHALL have exactly the content given in
  the issue (reproduced in design.md), and `test/org-drift.test.ts` SHALL
  assert it deep-equals that content and that its `items[].item` equals
  `ui.detailsStackItems.en` element for element, in order.
- R25. `test/org-drift.test.ts` SHALL show `computeDrift` returns no drift on a
  converged fixture and exactly one entry for each of three mutated fixtures
  (uncarded repository, archived carded repository, evidence path 404); SHALL
  show a fixture whose only defect is one `unknown` evidence result is not
  "no drift"; SHALL cover a failed org listing and a failed bootstrap listing
  producing `Unknown`; SHALL cover R19 with an injected fetch; and SHALL
  assert `renderIssueBody` output as a full-string snapshot.
- R26. Both new test files SHALL be appended to the `test` script in
  `package.json`, and `npm run build` SHALL pass.
- R27. `docs/weekly-refresh.md` SHALL describe the schedule, both tokens, the
  PR and auto-merge path (release PR still merged by a human), the drift
  issue lifecycle, keeping `stack-evidence.json` in sync with
  `detailsStackItems`, and the manual run
  `gh workflow run weekly-refresh.yml -R mctlhq/portfolio`.
- R28. A journal entry for this cycle SHALL exist under
  `src/content/journal/` with `status: in_progress`, title
  en `Q19: weekly Sunday snapshot and org drift report` /
  ru `Q19: еженедельный воскресный снимок и отчёт о расхождениях с организацией`,
  and the remaining copy given verbatim in design.md.

## Out of scope

- Any change to visible site copy, including `detailsStackItems` /
  `detailsRunItems` (`RUN_ITEMS_*`, `STACK_EXTRA` in `src/i18n/ui.ts`) and the
  `/work/` cards. Acting on the drift report is a later cycle.
- Auto-merging release-please pull requests, or any change to
  `release-please.yml`, `claude-review.yml` or `dependabot.yml`
  (human-reserved files).
- Changes to `scripts/snapshot-metrics.mjs` or what it counts.
- Repository settings: enabling auto-merge in the repository, creating the
  `weekly-drift` label, granting the App org-wide contents read — operator
  actions, not commits.
- Editing the existing Q17 journal entry or any other completed entry.
- Adding a YAML-parser dependency (the workflow test uses text/structure
  checks, matching `test/journal-workflow.test.ts`).

## Open questions

- **Precondition, Q17 still `in_progress`.**
  `src/content/journal/2026-09-14-q17-issue-opened-at-from-a-recorded-source.md`
  is `status: in_progress`; its closure PR mctlhq/portfolio#116
  (`fix(journal): close cycle 105`) is open and unmerged. The journal loader
  (`checkJournalCollection` in `src/lib/journal.ts`) allows at most one
  `in_progress` entry, so the Q19 entry would fail `npm run build` until
  #116 is merged. The release owner must merge #116 before this proposal is
  implemented. The implementer must not edit the Q17 entry to work around it.
- "Parsing the file" in AC1: no YAML parser is a dependency. Proceeding with
  text checks plus a small step splitter in the test (split the `steps:` list
  on lines matching `^      - `), as `test/journal-workflow.test.ts` does.
- `generated_at` changes on every successful snapshot run, so in practice the
  file always changes and a PR is opened or updated every week. Accepted as
  the issue states it.
- If more than one open `weekly-drift` issue exists (e.g. created by hand),
  the script updates or closes the lowest-numbered one and logs a
  `::warning::` naming the others; it does not close extras on its own.
- An unknown/failed read of the bootstrap directory listing returning 404 is
  treated as unknown (a listing the script expects to exist), not as "no
  components".
- The `decided` copy and `seoTitle` of the journal entry were not supplied by
  the issue (only the title was); this proposal supplies them verbatim in
  design.md. The reviewer should check that copy.
- Previously-open snapshot PR with an unchanged file this week: left as-is
  (no close); the next changed run force-updates it.
