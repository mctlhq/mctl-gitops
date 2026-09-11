# P9: Production evidence — cutover journal, ADR-0003 and the live hosts

## Context

The portfolio site exists to be a verifiable artifact of the DevLoop: every
number on `/colophon/` is derived from `src/content/journal/` at build time, and
every decision that shaped the site has an ADR. Between the P8 cycle and now,
the site actually went to production — a rehearsal custom domain, a deliberate
rollback drill at `0.1.4 -> 0.1.3 -> 0.1.4`, two Cloudflare edge rewrites
disabled because they violated ADR-0004 and the no-JavaScript promise, and
finally the apex `dmitriimashkov.com` registered through the platform's
custom-domain registry and answering a green production contract under three
minutes after registration. None of that is written down in the repository yet.
The site currently claims a record it does not carry.

This cycle writes the record. It adds one journal entry for the cutover with its
four manual interventions and the operational timeline, ADR-0003 for the
custom-domain decision (`0003` is the one unused id between the existing 0001,
0002, 0004 and 0005), the two live hostnames in the colophon's build-and-deploy
chain, and the P8 reviewer-step results in `docs/hardening-notes.md` — including
the fact that Lighthouse mobile still has not been run. Everything described
already happened: this cycle is documentation, not operation. No DNS record, no
Cloudflare setting, no `mctl_*` call is made by the implementer.

## User stories

- AS a reader of `/colophon/` I WANT the cutover cycle listed among the others,
  with its interventions counted into the totals, SO THAT the production history
  of the site is as auditable as its build history.
- AS a reader following the decisions table I WANT ADR-0003 to explain how the
  custom domain, the proxied apex and the DNS-01 certificate were decided SO
  THAT the choice is reviewable rather than folklore.
- AS a reader of `/colophon/` I WANT the live hostnames named in the build and
  deploy chain SO THAT I can verify for myself where the site is served from.
- AS a reviewer of this repository I WANT `docs/hardening-notes.md` to state
  which P8 reviewer steps were completed and which are still outstanding SO THAT
  an unrun Lighthouse pass is recorded as an open human step, never as silently
  passed.
- AS the maintainer I WANT the four DNS and edge interventions recorded with
  `what`, `why` and `at` SO THAT ADR-0001's rule — wiring outside the DevLoop is
  a manual intervention and gets journalled — is honoured.

## Acceptance criteria (EARS)

Content and copy

- WHEN the implementer creates
  `src/content/journal/2026-09-11-production-cutover.md` THE SYSTEM SHALL carry
  the frontmatter given verbatim in `design.md` section "Copy A", with
  `service: portfolio`,
  `issue: https://github.com/mctlhq/portfolio/issues/42`,
  `proposal_slug: issue-42-p9-production-evidence-cutover-journal-a`,
  `visibility: public`, a bilingual `title`, a bilingual `decided`, and exactly
  four `interventions` items each with `what`, `why` and `at`.
- WHILE that journal entry exists THE SYSTEM SHALL contain no `pr`, `release`,
  `merged_at`, `released_at` or `deployed_at` key in it — those are filled in by
  the next cycle's backfill, the way issue #9 backfilled four earlier entries.
- WHEN the implementer writes that entry's markdown body THE SYSTEM SHALL
  reproduce the twelve-row operational record table and its closing line from
  `design.md` section "Copy B", in that order, with those timestamps.
- WHEN the implementer creates
  `src/content/adr/0003-custom-domain-via-mctl-registry.md` THE SYSTEM SHALL set
  `id: 3`, `status: accepted`, `date: '2026-09-11'`, `visibility: public` and the
  bilingual `title` from `design.md` section "Copy C".
- WHILE ADR-0003 exists THE SYSTEM SHALL present the five Nygard sections —
  Context, Decision, Consequences, Drivers, Revisit criteria — in that order,
  each heading carrying both a `<span class="l en">` and a `<span class="l ru">`
  label, and each section body carrying one `<div class="l en">` block and one
  `<div class="l ru" lang="ru">` block, with the prose from `design.md`
  section "Copy C".
- WHEN the implementer edits `src/i18n/ui.ts` THE SYSTEM SHALL append exactly
  two items to `colophonChainItems.en` and the two matching items to
  `colophonChainItems.ru`, worded verbatim as in `design.md` section "Copy D",
  leaving the existing five items in both arrays unchanged and the two arrays
  equal in length.
- WHEN the implementer edits `docs/hardening-notes.md` THE SYSTEM SHALL append a
  new section reporting, in this order: the HAR check result, the CSP check
  result, the two Cloudflare edge rewrites that had to be disabled first, and
  the outstanding Lighthouse mobile step — with the content of `design.md`
  section "Copy E".
- WHILE `docs/hardening-notes.md` exists THE SYSTEM SHALL state that Lighthouse
  mobile has not been run and remains outstanding for a human, and SHALL NOT
  delete or weaken the existing "Lighthouse mobile (reviewer step,
  post-deployment)" section and its empty score table.

Derivation and rendering

- WHILE `/colophon/` renders THE SYSTEM SHALL keep the cycle count and the
  intervention total derived from the `journal` collection at build time —
  `journal.length` and `totalInterventions(...)` in
  `src/pages/colophon/index.astro` — with no integer literal typed for either
  number anywhere under `src/`.
- WHEN `npm run build` runs THE SYSTEM SHALL emit
  `dist/colophon/journal/2026-09-11-production-cutover/index.html` and
  `dist/colophon/adr/0003-custom-domain-via-mctl-registry/index.html`, and SHALL
  list ADR-0003 as a row in the decisions table on `dist/colophon/index.html`
  linking to `/colophon/adr/0003-custom-domain-via-mctl-registry/`.
- WHEN `@astrojs/sitemap` runs THE SYSTEM SHALL include both new URLs in the
  sitemap, since `checkSitemap()` in `scripts/check-dist.mjs` derives the
  expected URL set independently from `src/content/journal/` and
  `src/content/adr/`.
- WHILE `/colophon/` renders THE SYSTEM SHALL show the two new live-host items
  in both the `.l.en` and the `.l.ru` chain list.

Gates

- WHEN `npm test` runs THE SYSTEM SHALL pass every existing check:
  `scripts/check-no-metrics.mjs`, `scripts/check-contrast.mjs` and all fourteen
  `node --test` suites, including `test/colophon.test.ts`'s assertion that every
  timestamp value in a public journal file is single-quoted and matches
  `ISO_WITH_OFFSET`, and that the `what`, `why` and `at` counts agree.
- WHEN `npm run build` runs THE SYSTEM SHALL complete, meaning the `adrLoader`
  wrapper's `checkAdrBodies` pass accepts ADR-0003's section shape and confirms
  its frontmatter `id: 3` matches the `0003` filename prefix.
- WHEN `node scripts/check-dist.mjs` runs after the build THE SYSTEM SHALL
  report `check-dist: OK`, with the colophon cycle count equal to the number of
  `visibility: public` files in `src/content/journal/` and the intervention total
  equal to the number of `- what:` items across those files.
- IF the `class="l en"` and `class="l ru"` occurrence counts in any
  `dist/**/*.html` diverge THEN THE SYSTEM SHALL fail `scripts/check-dist.mjs`,
  so the new ADR page and the two new chain items must stay bilingually paired.
- IF `astro build` were to emit a `<style>` element, a `style="..."` attribute
  or any `.js` file under `dist/` THEN THE SYSTEM SHALL fail
  `scripts/check-dist.mjs`; the new content is markdown and must introduce none
  of the three.

## Out of scope

- Removing `preview.dmitriimashkov.com`. It stays until the apex has been
  observed for five working days, and the colophon copy says so.
- Running Lighthouse mobile, or filling in any row of the existing score table
  in `docs/hardening-notes.md`. The implementer has no browser; this is named as
  an outstanding human step, never as an acceptance criterion (AGENTS.md, "Issue
  contract").
- Any DNS, Cloudflare, ingress, certificate or `mctl_*` operation. All of it has
  already happened; this cycle only records it.
- Backfilling `pr`, `release`, `merged_at`, `released_at` or `deployed_at` on
  this entry or on any earlier entry. That is the next cycle's job.
- Rendering the journal markdown body on `/colophon/journal/<id>/`.
  `src/pages/colophon/journal/[...slug].astro` renders frontmatter only and has
  no `<Content />`; no journal entry has ever had a body. See Open questions 2.
- New or renamed test files, and any change to
  `src/pages/colophon/index.astro`, `src/components/CycleTable.astro`,
  `src/lib/journal.ts`, `src/lib/adr.ts`, `src/content.config.ts`,
  `scripts/check-dist.mjs`, `astro.config.mjs` or `nginx.conf`. The four files in
  the issue's change list are sufficient; every gate this cycle must satisfy
  already exists.
- Changing `colophonTotalCycles` / `colophonTotalInterventions` wording, or any
  other `ui` key than `colophonChainItems`.

## Open questions

1. **The issue says "nine public cycles"; the repository will render twelve.**
   `src/content/journal/` currently holds eleven files, all `visibility: public`
   (nine of them `service: portfolio`, one `mctl-api`, one `mctl-agents`).
   Adding this cycle's entry makes twelve public cycles and, with four new
   interventions on top of the seventeen `- what:` items already present,
   twenty-one interventions in total. "Nine" appears to be a stale count — it
   matches the number of `service: portfolio` entries *before* this entry is
   added. Resolution taken: the number stays derived, exactly as the same
   criterion demands, so `/colophon/` will render whatever the build computes
   (12 and 21) and `scripts/check-dist.mjs` will confirm it against an
   independent scan. Deleting or privatising entries to reach nine is not done —
   it would falsify the record this cycle exists to publish. A reviewer who
   actually wants nine must say which three entries to hide, in a new issue.
2. **The entry body has nowhere to render.**
   `src/pages/colophon/journal/[...slug].astro` renders `data.decided`, the
   timeline and the interventions; it never calls `render(entry)` and emits no
   `<Content />`. All eleven existing journal files have an empty body. The
   operational record therefore lands as committed repository evidence,
   reachable in git and in the raw file, but not on the published page.
   Resolution taken: write the body as the issue specifies and leave the route
   untouched, because the issue's own change list names four files and does not
   include the route, and because rendering an English-only operational table on
   a page whose every other string is bilingual is a design decision, not a
   mechanical one. Recommended follow-up: a separate issue that adds
   `<Content />` to the journal route inside a `div class="mctl-prose"` wrapper
   (mirroring `src/pages/colophon/adr/[...slug].astro`) together with a
   bilingual lead-in note, in the spirit of the existing
   `ui.journalInterventionsNote` — "quoted verbatim in English, the language it
   was written in".
3. **Two frontmatter timestamps cannot be known at proposal time.**
   `issue_opened_at` is a property of GitHub issue #42 and
   `proposal_approved_at` is written when a human approves this proposal, after
   this document is finished. `design.md` section "Copy A" therefore marks both
   with an explicit placeholder and `tasks.md` task 2 gives the exact command
   to resolve each: `gh issue view 42 --repo mctlhq/portfolio --json createdAt`
   for the first, and the `approval.approved_at` field of this proposal's
   `.status.yaml` in `mctl-gitops` for the second — which is how the P8 entry's
   `proposal_approved_at: '2026-09-11T12:49:46Z'` matches that proposal's
   `.status.yaml` exactly. Both must end up single-quoted and matching
   `ISO_WITH_OFFSET`, or `test/colophon.test.ts` fails.
4. **A public entry that names Cloudflare and Let's Encrypt.**
   AGENTS.md says nothing naming "third parties" goes into a `public` entry, and
   the copy this issue supplies names Cloudflare, `static.cloudflareinsights.com`
   and Let's Encrypt throughout — in a `visibility: public` journal entry and a
   `visibility: public` ADR. Resolution taken: the issue's copy is used
   unchanged. The rule reads as protection against leaking private or internal
   detail, not against naming the public infrastructure the site demonstrably
   runs on, and a custom-domain ADR that cannot name the proxy or the CA would
   say nothing. Flagged so a reviewer can overrule before approval rather than
   after.
5. The issue's own body reproduces `issue: .../issues/<this issue>` and
   `proposal_slug: <this proposal's slug>` as placeholders; both are resolved
   literally in `design.md` section "Copy A" (issue 42, slug
   `issue-42-p9-production-evidence-cutover-journal-a`). No other placeholder
   remains in the copy.
