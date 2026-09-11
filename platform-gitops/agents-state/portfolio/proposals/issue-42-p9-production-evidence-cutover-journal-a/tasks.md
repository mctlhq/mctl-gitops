# Tasks: issue-42-p9-production-evidence-cutover-journal-a

All copy referenced below lives in `design.md` sections "Copy A" through
"Copy E" and must be reproduced character for character. Four files change:
two new content files, two edits. Nothing under `src/pages`, `src/components`,
`src/lib`, `src/layouts`, `scripts/`, `test/`, `astro.config.mjs`,
`package.json` or `package-lock.json` is touched.

- [ ] 1. Create `src/content/journal/2026-09-11-production-cutover.md` with the
      frontmatter from `design.md` "Copy A" and the body from "Copy B".
      Reproduce both verbatim, including the Russian `title.ru` and
      `decided.ru`; single-quote every timestamp; use double quotes for the
      `title`, `decided`, `what` and `why` strings as Copy A shows (several
      contain an apostrophe or a colon). Include exactly four `interventions`
      items and no `pr`, `release`, `merged_at`, `released_at` or `deployed_at`
      key. — DoD: the file exists; `grep -c '^\s*- what:'` returns 4;
      `grep -E '^(pr|release|merged_at|released_at|deployed_at):'` returns
      nothing; the body contains the twelve-row table and the closing line
      "Time from apex registration to a green contract: under three minutes."

- [ ] 2. Resolve the two `<<…>>` placeholders in that file (depends on 1).
      `issue_opened_at`: run
      `gh issue view 42 --repo mctlhq/portfolio --json createdAt` and use the
      returned instant, normalised to UTC with `Z` and no fractional seconds.
      `proposal_approved_at`: read `approval.approved_at` from this proposal's
      `.status.yaml` in `mctl-gitops`
      (`platform-gitops/agents-state/portfolio/proposals/issue-42-p9-production-evidence-cutover-journal-a/.status.yaml`)
      — the same field whose value `2026-09-11T12:49:46Z` appears as
      `proposal_approved_at` in
      `src/content/journal/2026-09-11-p8-production-hardening-accessibility-wc.md`.
      If either source is unreachable, fall back to the earliest defensible
      real instant you can evidence (for `issue_opened_at`, the issue's own
      creation as shown by `gh api repos/mctlhq/portfolio/issues/42`; for
      `proposal_approved_at`, the `.status.yaml` `updated_at` of the approval
      commit) and say which fallback was used in the commit body. Never invent a
      stamp and never leave a placeholder. — DoD: both values are
      single-quoted ISO 8601 strings matching
      `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$`; no
      `<<` or `>>` remains anywhere in `src/`;
      `proposal_approved_at` is later than `issue_opened_at`.

- [ ] 3. Create `src/content/adr/0003-custom-domain-via-mctl-registry.md` from
      `design.md` "Copy C": `id: 3`, bilingual `title`, `status: accepted`,
      `date: '2026-09-11'` (quoted), `visibility: public`, then the five Nygard
      sections in the order Context, Decision, Consequences, Drivers, Revisit
      criteria. Mirror the exact body structure of
      `src/content/adr/0004-no-analytics.md`: each heading as
      `## <span class="l en">EN</span><span class="l ru">RU</span>`, each
      section as a `<div class="l en">` block followed by a
      `<div class="l ru" lang="ru">` block, with a blank line after the opening
      tag and before the closing tag so markdown renders the prose as a
      paragraph. Do not copy the `>` blockquote markers `design.md` uses for
      quoting. — DoD: the file exists with `id: 3` matching the `0003`
      filename prefix; `grep -c 'class="l en"'` and `grep -c 'class="l ru"'`
      each return 10 (five headings plus five bodies); `npm run build`
      completes, i.e. `checkAdrBodies` reports no problem.

- [ ] 4. Edit `src/i18n/ui.ts`: append the two `design.md` "Copy D" items to
      `colophonChainItems.en` and the two matching items to
      `colophonChainItems.ru`, after the existing five in each, preserving the
      existing five verbatim and the file's single-quote style. Change no other
      `ui` key. — DoD: both arrays have exactly seven items; `git diff
      src/i18n/ui.ts` shows only additions inside `colophonChainItems`;
      `node --test test/ui.test.ts` passes.

- [ ] 5. Edit `docs/hardening-notes.md`: append the new section from
      `design.md` "Copy E" after the existing content, stating in order the HAR
      result, the CSP result, the two disabled Cloudflare edge rewrites, and
      that Lighthouse mobile has not been run and remains outstanding for a
      human. Leave the existing "Lighthouse mobile (reviewer step,
      post-deployment)" section, its `_Not yet run …_` line and its empty
      four-row score table untouched. — DoD: `git diff docs/hardening-notes.md`
      shows appended lines only, no deletions; the file contains both the
      pre-existing "Not yet run" line and the new statement that Lighthouse
      mobile has not been run; the two named Cloudflare features are
      "Web Analytics" and "Email Obfuscation".

- [ ] 6. Run the full local gate and commit (depends on 1-5). Conventional
      commit, no `feat!`/`BREAKING CHANGE` (pre-1.0.0), branch and PR — never a
      direct push to `main`. Suggested subject:
      `feat(journal): record the production cutover, ADR-0003 and the live hosts`.
      — DoD: `npm test` and `npm run build` both exit 0;
      `node scripts/check-dist.mjs` prints `check-dist: OK`; the PR is open
      against `main` from the implementer's fixed template.

## Tests

No new or modified test file. Every criterion is covered by a gate that already
exists; these are the runs that prove it.

- [ ] T1. `npm test` — runs `scripts/check-no-metrics.mjs`,
      `scripts/check-contrast.mjs` and all fourteen `node --test` suites. Must
      exit 0. In particular `test/colophon.test.ts` asserts that every public
      journal file has `service`, `issue`, `proposal_slug`, `visibility`,
      `title`, `decided` and `issue_opened_at`; that every
      `issue_opened_at` / `proposal_approved_at` / `merged_at` / `released_at` /
      `deployed_at` / `at` value is single-quoted and matches
      `ISO_WITH_OFFSET`; that the `what`, `why` and `at` counts are equal (4, 4,
      4 for the new entry); and that no file under `src/content/` contains
      `lead_time`, `leadTime`, `intervention_count` or `interventionCount`.
      `test/ui.test.ts` asserts the `colophonChainItems` `en`/`ru` arrays are
      the same length with no empty item. `scripts/check-no-metrics.mjs` must
      still print `OK` with no new `ALLOW` entry — the `301` in Copy D lives in
      `src/i18n/ui.ts`, which is outside its `src/pages`, `src/components`,
      `src/layouts` scan.
- [ ] T2. `grep -rn '<<\|>>' src/ docs/` returns nothing — no placeholder from
      Copy A survived task 2.
- [ ] T3. `npm run build` — must exit 0. This is where the `adr` collection's
      wrapped loader runs `checkAdrBodies`, checking ADR-0003's five sections,
      their order, the Russian heading spans, the per-section `.l.en` / `.l.ru`
      blocks, and that frontmatter `id: 3` matches the `0003` filename prefix.
      It is also where `@astrojs/sitemap` picks up the two new URLs.
- [ ] T4. `node scripts/check-dist.mjs` after the build — must print
      `check-dist: OK`. This is the criterion-5 check: `checkColophonPages()`
      re-scans `src/content/journal/` and `src/content/adr/` independently and
      fails unless `data-cycle-count`, `data-intervention-count` and the
      `data-cycle-row` count all match that scan. Expect the summary line to
      report **12 cycles and 21 interventions** (11 -> 12 public journal files,
      17 -> 21 `- what:` items) — not nine; see `requirements.md` Open
      question 1. It also verifies
      `dist/colophon/journal/2026-09-11-production-cutover/index.html` and
      `dist/colophon/adr/0003-custom-domain-via-mctl-registry/index.html` exist,
      that `class="l en"` and `class="l ru"` counts are equal in every HTML
      file, that `checkSitemap()` finds both new URLs and no unexpected one,
      and that no `<style>`, ` style="` or `.js` appeared under `dist/`.
- [ ] T5. Manual read of `dist/colophon/index.html`: ADR-0003 appears as a row
      in the `table.adr-index` with id `0003`, status `Accepted`, date
      `2026-09-11`, linking to
      `/colophon/adr/0003-custom-domain-via-mctl-registry/`; the new cycle
      appears as a `data-cycle-row` with an em dash in the lead-time and
      pull-request columns and `4` in the interventions column; and both chain
      lists (`ul.l.en` and `ul.l.ru`) show seven items ending with the two
      hostname items.
- [ ] T6. `docker build .` (optional, CI does the equivalent) — the Dockerfile
      runs `npm run build && node scripts/check-dist.mjs && node
      scripts/csp-hash.mjs`, so a green image build is the same evidence as
      T3+T4 in the environment that actually ships. `.github/workflows/build.yml`
      runs `npm test` and then the image build with
      `scripts/check-headers.mjs` against the running container.

## Rollback

This cycle is additive content plus two appends; nothing is deleted, renamed or
migrated, so rollback is a revert.

1. **Before merge** — close the pull request, or drop the offending file. The
   two new files are independent: deleting
   `src/content/adr/0003-custom-domain-via-mctl-registry.md` alone returns the
   decisions table, the sitemap and `check-dist`'s ADR page assertions to their
   current state; deleting
   `src/content/journal/2026-09-11-production-cutover.md` alone returns
   `data-cycle-count` to 11 and `data-intervention-count` to 17, since both are
   derived. The `src/i18n/ui.ts` and `docs/hardening-notes.md` edits are append-only
   and revert cleanly with `git checkout main -- src/i18n/ui.ts
   docs/hardening-notes.md`.
2. **After merge, before release** — `git revert` the merge commit. `npm test`,
   `npm run build` and `check-dist` all pass on the pre-change tree, because
   every count they check is derived rather than pinned.
3. **After a release is tagged and deployed** — the site is static and this
   change ships no runtime behaviour, so there is no operational failure mode to
   roll back from; a content correction is a normal follow-up cycle. If a
   rollback is nonetheless wanted, `mctl_rollback_service` to the previous image
   tag (`mctl_get_service_config` first to read the current one) is the only
   supported route per AGENTS.md, and the rollback itself then has to be
   recorded as a manual intervention in the next journal entry.
4. **Not a rollback path:** touching DNS, the Cloudflare zone, the ingress or
   the certificate. Nothing in this cycle changes any of them, so nothing in
   them needs undoing.
