# Tasks: issue-68-q8-backfill-the-five-missing-journal-ent

> **Operator amendment, applied before approval (2026-09-12).** The
> deliverable is **six** content files, not five: the five backfilled entries
> described throughout, plus **this cycle's own journal entry**, specified as
> Copy (normative) -> 6 in `requirements.md` and as task 6b in `tasks.md`.
> Every cycle writes its own entry; a backfill that repeats the omission it
> corrects has corrected nothing. Consequently the derived cycle counter is
> **20**, not 19, and `git status --porcelain` must list six added files.
> Propagated in full on 2026-09-12 after review: every derived-effect count in
> this file now reads six, and the remaining "five" mentions are the ones that
> genuinely mean the five backfilled entries (the backfill itself, the rejected
> alternatives, and the copy blocks). The scope remains content files only.

- [ ] 1. Read `src/content/journal/2026-09-11-p8-production-hardening-accessibility-wc.md`
      and the `journal` collection in `src/content.config.ts` to confirm the
      target shape before writing anything — DoD: the eight-key order
      (`service`, `issue`, `proposal_slug`, `visibility`, `title`, `decided`,
      `issue_opened_at`, `proposal_approved_at`), the frontmatter-only body,
      and the fact that `merged_at` / `released_at` / `deployed_at` are
      `.optional()` and `interventions` has `.default([])` are all confirmed
      in the checkout rather than assumed.

- [ ] 2. Create `src/content/journal/2026-09-11-csp-hash-quoting-and-browser-verified-headers.md`
      with the bytes given in `requirements.md` -> Copy (normative) -> 1
      (depends on 1) — DoD: file exists; eight keys present in the listed
      order; `service: portfolio`, `visibility: public`; both timestamps
      single-quoted exactly as given; EN and RU `title` and `decided` present
      character for character; nothing after the closing `---`.

- [ ] 3. Create `src/content/journal/2026-09-12-content-link-contrast-and-an-offline-link-check.md`
      from Copy (normative) -> 2 (depends on 1) — DoD: as task 2, with
      `issue` `.../issues/55` and `proposal_slug`
      `issue-55-q2-content-link-contrast-footer-and-colo`.

- [ ] 4. Create `src/content/journal/2026-09-12-repository-links-out-of-the-disclosure.md`
      from Copy (normative) -> 3 (depends on 1) — DoD: as task 2; the two
      inner double quotes around `Details` in `decided.en` are written as
      `\"` inside the double-quoted scalar, and the RU value keeps its
      guillemets unescaped.

- [ ] 5. Create `src/content/journal/2026-09-12-colophon-tables-and-computed-lead-time.md`
      from Copy (normative) -> 4 (depends on 1) — DoD: as task 2; the four
      inner double quotes around `not recorded` and `not implemented` in
      `decided.en` are written as `\"`.

- [ ] 6. Create `src/content/journal/2026-09-12-navigation-state-and-accessibility-affordances.md`
      from Copy (normative) -> 5 (depends on 1) — DoD: as task 2, with
      `issue` `.../issues/49` and `proposal_slug`
      `issue-49-q5-navigation-state-disclosure-defaults`.

- [ ] 6b. Create `src/content/journal/2026-09-12-backfilling-five-omitted-journal-entries.md`
      from Copy (normative) -> 6, this cycle's own entry (depends on 1) —
      DoD: file exists; same eight-key order as tasks 2-6; `issue`
      `.../issues/68` and `proposal_slug`
      `issue-68-q8-backfill-the-five-missing-journal-ent`;
      `issue_opened_at: '2026-09-12T12:27:57Z'`; `proposal_approved_at` is the
      `approval.approved_at` value read from `$PROPOSAL_DIR/.status.yaml` at
      implementation time, single-quoted and copied verbatim — NOT invented,
      NOT the current time, NOT left as the placeholder text; EN and RU
      `title` and `decided` present character for character.

- [ ] 7. Confirm nothing outside `src/content/journal/` changed (depends on
      2-6b) — DoD: `git status --porcelain` lists exactly six added files, all
      under `src/content/journal/`; no template, style, script, test,
      `package.json` or `package-lock.json` change; `src/content.config.ts`
      untouched.

## Tests

- [ ] T1. Run `npm run check` (`astro sync && astro check`) — DoD: exits
      zero, proving all six files parse as YAML and validate against the
      `z.strictObject` journal schema, including the `stamp` refinement that
      would reject any timestamp YAML coerced into a `Date` and the strict
      rejection of any unknown key.

- [ ] T2. Run `npm test` — DoD: exits zero. Specifically
      `test/colophon.test.ts` must pass its per-file frontmatter test on each
      of the six new files: the seven required keys present, every timestamp
      value single-quoted and matching `ISO_WITH_OFFSET`, and zero
      intervention `what` / `why` / `at` items each. `node scripts/check-no-metrics.mjs`
      (first command in the `test` script) must stay green, which it will —
      its `SCAN_DIRS` are `src/pages`, `src/components`, `src/layouts` only.

- [ ] T3. Diff the parsed strings against the normative copy (depends on
      T1) — DoD: for each of the six files, the `title.en`, `title.ru`,
      `decided.en` and `decided.ru` values as parsed (e.g. via a throwaway
      `node --input-type=module` snippet or `astro sync` output) are byte-identical
      to `requirements.md` -> Copy (normative), confirming the `\"` escapes
      resolved to plain `"` and no scalar was truncated. The throwaway script
      is not committed.

- [ ] T4. Run `npm run build` (depends on T2) — DoD: exits zero, and
      `dist/colophon/journal/<slug>/index.html` exists for all six new
      slugs, task 6b's included.

- [ ] T5. Run `node scripts/check-dist.mjs` (depends on T4) — DoD: exits
      zero. This is the criterion-5 gate: `checkColophonPages()` compares
      `data-cycle-count` and the `data-cycle-row` count in
      `dist/colophon/index.html` against its own independent `readdir()` of
      `src/content/journal`, so both must equal the number of public entries
      on disk — **20** with the fourteen already present plus the five
      backfilled here and this cycle's own entry from task 6b; neither the 18
      the issue's stale arithmetic names nor the 19 this proposal carried
      before the operator amendment (see the amendment header above and the
      first open question in `requirements.md`). It also confirms no
      `dist/**/*.js`, equal `class="l en"` / `class="l ru"` counts on each of
      the six new pages, the three-item breadcrumb on each, and the sitemap
      URL list including the six new routes.

- [ ] T6. Confirm the counter is derived, not typed (depends on T4) — DoD:
      the `data-cycle-count` value in `dist/colophon/index.html` equals
      `ls src/content/journal/*.md | wc -l` restricted to files carrying
      `visibility: public` (**20** as the tree stands after this change), and
      `grep -rnE '\b(1[89]|20)\b' src/pages src/components src/layouts src/i18n`
      shows no newly introduced literal count — neither 18 nor 19 nor 20 —
      proving the number comes from `journal.length` alone.
      **The pattern must include the current target value.** Before the
      operator amendment this check read `'\b1[89]\b'`, which would have
      passed a hard-coded `20` in silence: a guard that cannot see the value
      it exists to forbid. If a later change moves the counter again, move
      this pattern with it.

- [ ] T7. Run `node scripts/check-links.mjs` against the rebuilt tree
      (depends on T4) — DoD: exits zero; the six new GitHub issue URLs are
      reported as skipped off-origin (task 6b's entry links
      `.../issues/68`), and every internal link on the six new
      pages (`/`, `/colophon/`, the breadcrumb and the back link) resolves
      against a file under `dist/`. No network request is issued.

- [ ] T8. Confirm the intervention total is unchanged (depends on T4) — DoD:
      `data-intervention-count` in `dist/colophon/index.html` holds the same
      value it held before this change, since `interventions` is omitted from
      all six new files and defaults to `[]`.

## Rollback

Delete the six added files under `src/content/journal/` and rebuild; the
cycle counter returns to **14** — the count the tree already held before this
backfill, as `design.md` establishes; not 13, which was the issue's stale
figure written before `2026-09-12-q7-polish-wave-findings.md` landed — the six
pages and table rows disappear, and no other file was touched, so nothing else
has to be reverted. Before merge: close the pull request or drop the commit.
After merge: `git revert` the merge commit — the diff is six file additions and
the revert is a pure deletion with no schema, template or script change to
undo. Because every
downstream number is derived from the content directory rather than from a
literal, the removal is self-consistent the moment the files are gone; no
follow-up edit to `src/pages/colophon/index.astro`, `CycleTable.astro` or any
test is needed in either direction. No deployment or data migration is
involved, so a rollback costs one rebuild.
