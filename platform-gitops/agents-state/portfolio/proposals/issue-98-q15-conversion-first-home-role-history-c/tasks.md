# Tasks: issue-98-q15-conversion-first-home-role-history-c

Every user-facing string named below is in **requirements.md, Appendix A**.
Copy it from there character for character — do not retype, translate,
re-case or re-punctuate it.

- [ ] 1. Add the nine new keys to `src/i18n/ui.ts`: `heroEyebrow` (A.1),
      `ctaContact` (A.2), `aboutHeading` (A.3), `aboutParagraphs` (A.4, three
      strings per language), `capabilitiesHeading` (A.5), `capabilityItems`
      (A.6, three `{ term, body }` per language), `contactHeading` (A.7),
      `contactIntro` (A.8), `contactItems` (A.9, four `{ label, href, text }`
      per language). Keep `ctaColophon` and `detailsContactSummary` in the
      dictionary even though nothing renders them any more. — DoD: `npx astro
      check` is clean; every value matches Appendix A byte for byte; array
      lengths match across `en`/`ru`; no existing key's value changed.

- [ ] 2. Generalise the array branch of the parity walk in `test/ui.test.ts`
      (depends on 1): for an array pair keep the same-kind and same-length
      assertions, then per index accept either two non-empty strings (current
      rule) or two objects with identical key sets whose every value is a
      non-empty string; a string/object mismatch at the same index fails. —
      DoD: `node --test test/ui.test.ts` passes with the new object-valued
      keys, and a locally mutated fixture (an object item with a missing key,
      an empty string value, or a length mismatch) still fails.

- [ ] 3. Add an exact-value test to `test/ui.test.ts` (depends on 1, 2) that
      asserts all nine new keys' EN and RU values character for character,
      including every array element and every object field, in the style of the
      file's existing "carry their exact EN/RU values" tests. — DoD: the test
      fails if any single character of any new string is altered.

- [ ] 4. Restructure `src/pages/index.astro` (depends on 1). Final document
      order: `<span class="eyebrow">` (heroEyebrow) → existing
      `<h1 class="hero-name">` → `.thesis` → `.subline` → the existing
      `#ctas-label` span and `<nav class="ctas">` → `<section id="about">` →
      `<section id="capabilities">` → the existing `<section class="stats">` →
      the `detailsRunSummary` and `detailsWorkSummary` `<Details>` blocks
      (unchanged, both keeping `heading`) → `<section id="contact">`. The
      `.ctas` nav holds exactly two links: `<a class="cta cta-primary"
      href="#contact">` bound to `ui.ctaContact`, then `<a class="cta"
      href="/work/">` bound to `ui.ctaWork`. Delete the `ctaColophon` CTA and
      the whole `detailsContactSummary` `<Details>` block including its two
      hard-coded links. Render every new string through the existing `<Lang en
      ru />` component; map `ui.aboutParagraphs.en` / `.capabilityItems.en` /
      `.contactItems.en` with their index and pair each entry with the same
      index in `.ru`; take a contact item's `href` and visible `text` from the
      `en` entry and render only `label` as a `<Lang>` pair. `#about` and
      `#capabilities` each open with a visible `<h2>`; each capability entry is
      an `<h3>` (term) followed by one `<p>` (body); `#contact` is `<h2>` +
      `<p>` (contactIntro) + a list of the four links. — DoD: no `<details>`
      wraps any identity, capability or contact text; `heroName`, `heroThesis`,
      `heroSubline` and the four `<Stat>` tags are untouched; the template
      contains no digit once `<h1>`..`<h6>` tag names are stripped; the
      template contains no literal `Dmitrii Mashkov` / `Дмитрий Машков`
      outside the `description=` attribute; `npx astro check` is clean.

- [ ] 5. Add `homeJsonLd()` to `src/lib/seo.ts` (no new imports — the module is
      deliberately zero-import) returning
      `{ '@context': 'https://schema.org', '@graph': [Person, WebSite] }` with
      exactly the literals in Appendix A.11: `Person` carrying only `@type`,
      `name`, `url`, `jobTitle`, `email` and the three ordered `sameAs`
      entries; `WebSite` carrying only `@type`, `name`, `url`, `inLanguage`. No
      `worksFor`, `address`, `alumniOf`, `telephone` or `SearchAction`. — DoD:
      the function is pure, takes no argument, and returns a fresh object each
      call.

- [ ] 6. Wire the graph into `src/layouts/Base.astro` (depends on 5): import
      `homeJsonLd`, compute `const isHome = Astro.url.pathname === '/'`, and
      pass `jsonLd ?? (isHome ? homeJsonLd() : undefined)` into the **existing**
      `<script type="application/ld+json" set:html={…}>` block. Do not change
      that block's markup, its `.replace(/</g, '\\u003c')` escaping, its
      position in `<head>`, or the executable inline script above it. — DoD:
      `dist/index.html` gains exactly one `application/ld+json` block;
      `dist/colophon/journal/*/index.html` and `dist/colophon/adr/*/index.html`
      still carry their `BreadcrumbList` and only that; `dist/work/index.html`,
      `dist/approach/index.html`, `dist/colophon/index.html` and `dist/404.html`
      carry no JSON-LD.

- [ ] 7. Add unit tests for `homeJsonLd()` to `test/seo.test.ts` (depends on
      5): the `@graph` has exactly two nodes; the `Person` node's key set is
      exactly `['@type','name','url','jobTitle','email','sameAs']` with the
      Appendix A.11 values; `sameAs` deep-equals the three URLs in order; the
      `WebSite` node's key set is exactly `['@type','name','url','inLanguage']`;
      neither node carries `worksFor`, `address`, `alumniOf`, `telephone` or
      `potentialAction`. Leave the existing `breadcrumbJsonLd` and
      `clampDescription` tests untouched. — DoD: `node --test test/seo.test.ts`
      passes; adding a stray field to either node fails a test.

- [ ] 8. Style the new markup in `src/styles/site.css` (depends on 4):
      `.eyebrow` (block, display font, `--mctl-typography-font-size-sm`,
      `color: var(--surface-fg-muted)`, small block-end margin); `.cta-primary`
      (`background-color: var(--accent)`, `border-color: var(--accent)`,
      `color: var(--accent-fg)`) plus the pins `.cta-primary:hover` and
      `.cta-primary:visited:not(:hover)` keeping `color: var(--accent-fg)` on
      the accent background, hover additionally underlined, placed **after**
      the existing `.cta:visited:not(:hover)` pin; section spacing for
      `#about`, `#capabilities` and `#contact` consistent with `.block`;
      `.capability-list` (`h3` and `p` sizing from the display/body tokens);
      `.contact-list` and `.contact-list a` with `display: inline-flex;
      align-items: center; min-block-size: 44px`. Use only tokens already
      declared; introduce no new foreground/background colour pair. — DoD:
      `node scripts/check-contrast.mjs` passes with no change to its `PAIRS`
      list; `site.css` still declares no `animation` and no `transition`.

- [ ] 9. Add `'.contact-list a'` to `TARGET_SELECTORS` in `test/a11y.test.ts`
      (depends on 8). — DoD: `node --test test/a11y.test.ts` passes, and
      removing the `min-block-size` from `.contact-list a` makes it fail.

- [ ] 10. Update the source-level expectations in `test/home.test.ts` (depends
      on 4): exactly two `<Details` tags, both carrying `heading`, none
      carrying `open`; the `.ctas` nav holds exactly two `<a>` elements, the
      first `href="#contact"` with `class="cta cta-primary"`, the second
      `href="/work/"` with `class="cta"`; `ui.ctaColophon` and
      `ui.detailsContactSummary` appear nowhere in `index.astro`. Keep the
      metrics-import, four-`<Stat>`, no-digit, no-`id="work"`/`id="approach"`,
      hero-`<Lang>`, no-literal-name and `.hero-name` font-stack tests as they
      are. — DoD: `node --test test/home.test.ts` passes against the new page
      and fails against the old one.

- [ ] 11. Add build-backed assertions to `test/home.test.ts` (depends on 4, 6,
      13), following `test/project-card-private.test.ts`: copy `src/`,
      `astro.config.mjs`, `package.json`, `tsconfig.json` into a `mkdtemp`
      tree, symlink `node_modules` and `public`, run
      `node node_modules/astro/bin/astro.mjs build` there once (memoise the
      result for the whole file, clean up afterwards), then assert on
      `dist/index.html`: the eyebrow, each of the three `aboutParagraphs`, each
      of the three `capabilityItems` terms **and** bodies, `contactIntro`, and
      each of the four `contactItems` texts are present in both a
      `class="l en"` and a `class="l ru"` element; no `<details>` element
      contains any of those texts; exactly one `application/ld+json` block,
      `JSON.parse`d (not substring-matched) and asserted against Appendix
      A.11. Assert on `dist/work/index.html` that `https://rewards.mctl.ai` is
      present, and across every built page that `labs-mctl-loyalty.mctl.ai`
      appears nowhere. Decode HTML entities before comparing (Astro escapes the
      apostrophe in "the team's"). — DoD: `node --test test/home.test.ts`
      passes; deleting any one of the twelve new strings from `ui.ts` makes it
      fail.

- [ ] 12. Update `checkHomePage()` in `scripts/check-dist.mjs` (depends on 4,
      6): expect **zero** `<details open>` elements (was one) and **exactly
      two** `<summary><h2` openings (was three), and add a home-page JSON-LD
      check mirroring the existing `checkJsonLd()` — exactly one
      `application/ld+json` block, it parses, its `@graph` carries a `Person`
      with the five Appendix A.11 fields and the three ordered `sameAs`
      entries and a `WebSite` with its three fields. Leave the hero, title and
      Cyrillic checks alone, and leave `checkJsonLd()`'s journal/ADR path
      untouched. — DoD: `npm run build && node scripts/check-dist.mjs` exits 0
      locally, so `docker build` (which runs the same command) cannot fail on
      this gate.

- [ ] 13. Change the loyalty service link (Appendix A.10): `url:
      https://labs-mctl-loyalty.mctl.ai` → `url: https://rewards.mctl.ai` in
      both `src/content/projects/mctl-loyalty.en.md` and
      `src/content/projects/mctl-loyalty.ru.md`, and update the `mctl-loyalty`
      row in `test/projects.test.ts` to
      `{ slug: 'mctl-loyalty', url: 'https://rewards.mctl.ai', en: 'Service',
      ru: 'Сервис' }`. Change nothing else in those three files and nothing
      else on `/work/`. — DoD: `node --test test/projects.test.ts
      test/work.test.ts` passes; `grep -r labs-mctl-loyalty src test` returns
      nothing.

- [ ] 14. Add a `test/links.test.ts` case (depends on 4) proving the three new
      off-origin hrefs are reported rather than silently passed:
      `classifyHref('https://rewards.mctl.ai', ORIGIN)`,
      `classifyHref('https://www.linkedin.com/in/dmitriimashkov', ORIGIN)` and
      `classifyHref('https://t.me/dmitriimashkov', ORIGIN)` each return
      `{ kind: 'skipped', reason: 'off-origin' }`, and a fixture page carrying
      all three plus `mailto:hello@dmitriimashkov.com` puts each of them in
      `run()`'s `skipped` map with the right count and in none of `checked` or
      `problems`. Do not add any network call to the script — the no-network
      source test in the same file must keep passing. — DoD: `node --test
      test/links.test.ts` passes; `node scripts/check-links.mjs` after a real
      build prints the three URLs in its `skipped x<n>:` lines and exits 0.

- [ ] 15. Add a fixture case for the new home-page JSON-LD branch to
      `test/check-dist.test.ts` (depends on 12), in that file's existing
      spawn-the-real-script-against-a-temporary-tree style: a fixture
      `dist/index.html` with a well-formed graph passes, and one with a missing
      `sameAs` entry, a missing `jobTitle`, or two `ld+json` blocks fails with
      a message naming the defect. — DoD: `node --test
      test/check-dist.test.ts` passes.

- [ ] 16. Update the heading-hierarchy row of `docs/accessibility-checklist.md`
      (depends on 4, 12) to describe the new home-page outline — one `<h1>`;
      `<h2>` for `#about`, `#capabilities`, the two disclosure summaries and
      `#contact`; `<h3>` for the three capability terms — and the new
      `<summary><h2` count of two that `checkHomePage()` asserts. — DoD: the
      document no longer claims three `<summary><h2` openings on
      `dist/index.html`.

- [ ] 17. Write this cycle's journal entry at
      `src/content/journal/2026-09-13-q15-conversion-first-home.md` (depends on
      1-16): `service: portfolio`, `issue:
      https://github.com/mctlhq/portfolio/issues/98`, `proposal_slug:
      issue-98-q15-conversion-first-home-role-history-c`, `status:
      in_progress`, `visibility: public`, `indexing: noindex`, bilingual
      `title`, a `seoTitle` short enough that the computed `<title>` stays at or
      under 65 characters, bilingual `decided` describing what this cycle
      decided, `interventions: []`, and a single-quoted ISO-8601 `Z`
      `issue_opened_at` read from GitHub (`gh issue view 98 --repo
      mctlhq/portfolio --json createdAt`). Do not write `pr`, `merged_at`,
      `release`, `released_at` or `deployed_at`. — DoD: it is the only
      `in_progress` entry in `src/content/journal/`; `node --test
      test/colophon.test.ts test/journal-status.test.ts test/title.test.ts`
      passes; the entry renders on `/colophon/` with status "in progress".

## Tests

- [ ] T1. `node --test test/ui.test.ts` — the generalised parity walk accepts
      the object arrays, and the exact-value test pins all nine new keys in
      both languages.
- [ ] T2. `node --test test/home.test.ts` — source expectations (two
      `<Details`, none open, two CTAs at `#contact` and `/work/`, no
      `ctaColophon`) and the build-backed assertions: every new string present
      in both `.l en` and `.l ru`, no `<details>` around any of them, exactly
      one parsed JSON-LD block matching Appendix A.11, `rewards.mctl.ai`
      present and `labs-mctl-loyalty.mctl.ai` absent from `dist/`.
- [ ] T3. `node --test test/seo.test.ts` — `homeJsonLd()`'s two nodes, their
      exact key sets, and the ordered `sameAs` triple.
- [ ] T4. `node --test test/projects.test.ts test/work.test.ts` — the corrected
      loyalty URL and no other `/work/` change.
- [ ] T5. `node --test test/links.test.ts` — the three off-origin hrefs are
      classified and counted as skipped, and the script still contains no
      network identifier.
- [ ] T6. `node --test test/a11y.test.ts` — the 44px floor now covers
      `.contact-list a`.
- [ ] T7. `node --test test/check-dist.test.ts` — the new home-page JSON-LD
      branch of `checkHomePage()`, proved against a fixture tree.
- [ ] T8. `node --test test/nav.test.ts test/footer.test.ts test/csp.test.ts
      test/title.test.ts test/colophon.test.ts` — unchanged files still pass
      (the colophon stays linked from nav and footer; the CSP hash is
      untouched; the new journal entry fits the title budget).
- [ ] T9. `npm run vendor && npm test` green, then `npm run build`, then
      `node scripts/check-dist.mjs` and `node scripts/check-links.mjs` — the
      full local equivalent of the CI `test` job plus the Dockerfile's dist
      gate.
- [ ] T10. `docker build .` (or CI's build job) — proves
      `scripts/check-dist.mjs` and `scripts/csp-hash.mjs` still pass inside the
      image, and `node scripts/check-headers.mjs http://127.0.0.1:8080` against
      the running container proves the CSP script-src hash is unchanged by the
      new JSON-LD.

## Rollback

Every change in this cycle is additive source or a one-line content edit; there
is no migration, no schema change, no stored state and no deployed dependency.

1. **Before merge:** close the pull request. Nothing is deployed and no journal
   entry is published.
2. **After merge, before release:** revert the merge commit on a branch and
   merge the revert through the normal review gate. The home page returns to
   the hero/stats/CTA/three-disclosure layout, `/work/` returns to
   `labs-mctl-loyalty.mctl.ai`, and `dist/index.html` loses the JSON-LD block.
   The journal entry is removed with the revert, which restores the
   zero-`in_progress` state the collection is in today.
3. **After release and deployment:** `mctl_rollback_service` to the previous
   image tag for the `portfolio` service in tenant `labs` (the only supported
   deployment route per `AGENTS.md`), then land the source revert as in step 2
   so the repository and the running image agree again.
4. **Partial rollback of section E only:** revert the three files from task 13
   (`mctl-loyalty.en.md`, `mctl-loyalty.ru.md`, `test/projects.test.ts`). It is
   independent of the home-page work and can be reverted on its own.
