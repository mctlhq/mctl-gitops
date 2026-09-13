# Tasks: issue-98-q15-conversion-first-home-role-history-c

- [ ] 1. Add the new copy to `src/i18n/ui.ts`: `heroEyebrow`, `ctaContact`,
      `aboutHeading`, `aboutParagraphs`, `capabilitiesHeading`,
      `capabilityItems`, `contactHeading`, `contactIntro`, `contactItems` —
      every value character for character as written in `requirements.md`
      sections A-D, EN and RU. Remove `detailsContactSummary`. Keep
      `heroName`, `heroThesis`, `heroSubline`, `ctaWork`, `ctaColophon` and
      `ctasLabel` unchanged. — DoD: `npx astro check` (or `npm run check`) is
      clean; every new key exists with both languages; no other `ui` key is
      touched; no version number appears in any new string except `OAuth 2.1`.

- [ ] 2. Widen the array branch of `test/ui.test.ts` (depends on 1) so an item
      that is a plain object is checked as such: the `en` and `ru` objects at
      the same index must have the same key set and a non-empty string at every
      leaf; strings and string arrays keep their current checks. — DoD:
      `node --test test/ui.test.ts` passes with `capabilityItems` and
      `contactItems` present, and still fails if an object leaf is emptied or a
      key is dropped from one language (verify by temporary mutation, then
      revert).

- [ ] 3. Add exact-value assertions to `test/ui.test.ts` (depends on 1) for
      `heroEyebrow`, `ctaContact`, `aboutHeading`, `capabilitiesHeading`,
      `contactHeading`, `contactIntro`, the three `aboutParagraphs` entries,
      the three `capabilityItems` terms and the four `contactItems`
      `{ href, text }` pairs, plus an assertion that
      `contactItems.en[i].href === contactItems.ru[i].href` and the same for
      `text`. — DoD: the test fails if any one character of the contracted copy
      changes.

- [ ] 4. Restructure `src/pages/index.astro` (depends on 1) to the order in
      `design.md` section 2: eyebrow `<p class="eyebrow">`, unchanged
      `<h1 class="hero-name">` / thesis / subline, the `#ctas-label` span and
      `<nav class="ctas">` moved up with exactly two links
      (`cta cta-primary` → `#contact` bound to `ctaContact`, then `cta` →
      `/work/` bound to `ctaWork`), `<section id="about">`,
      `<section id="capabilities">`, the unchanged `<section class="stats">`,
      the two remaining `<Details>` blocks, and `<section id="contact">`.
      No `<details>` may wrap the new copy. — DoD: `npm run build` succeeds;
      the rendered template still contains no digit once `h1`-`h6` tag names
      are stripped; `ctaColophon` no longer appears on the page;
      `src/components/Nav.astro` and the footer are untouched.

- [ ] 5. Update `test/home.test.ts` (depends on 4): expect exactly two
      `<Details` tags, both carrying `heading` and neither carrying `open`
      (the `ui.detailsContactSummary` assertion goes with the key); replace the
      `href="/colophon/"` CTA assertion with `href="#contact"` and
      `href="/work/"` in that order; keep the hero `<h1>`, no-digit and
      `.hero-name` font assertions passing. — DoD:
      `node --test test/home.test.ts` passes and no assertion still names
      `detailsContactSummary`.

- [ ] 6. Add `homeJsonLd(site)` to `src/lib/seo.ts` (zero-import, as the rest
      of that module) returning one `@graph` with the `Person`
      (`name`, `url`, `jobTitle`, `email`, `sameAs` in the contracted order)
      and the `WebSite` (`name`, `url`, `inLanguage`) exactly as specified in
      `requirements.md` section F, with the URL derived via
      `new URL('/', site).href`. No `worksFor`, `address`, `alumniOf`,
      `telephone` or `SearchAction`. — DoD: the function is pure and importable
      by `node --test`.

- [ ] 7. Emit it from `src/layouts/Base.astro` (depends on 6): compute
      `const isHome = Astro.url.pathname === '/'` and feed the existing
      `application/ld+json` element from `isHome ? homeJsonLd(Astro.site!.href) : jsonLd`.
      Do not touch the `set:html` escaping or the CSP mechanism. — DoD:
      `dist/index.html` has exactly one `application/ld+json` block;
      `dist/colophon/journal/*/index.html` still carries its `BreadcrumbList`;
      `dist/work/index.html` and `dist/approach/index.html` carry no block at
      all.

- [ ] 8. Add `test/seo.test.ts` assertions for `homeJsonLd` (depends on 6):
      the `Person`'s five fields, the three `sameAs` entries in order, the
      `WebSite`'s three fields, and the absence of `worksFor`, `address`,
      `alumniOf`, `telephone` and `SearchAction`. — DoD:
      `node --test test/seo.test.ts` passes and the existing
      `breadcrumbJsonLd` / `clampDescription` tests are untouched.

- [ ] 9. Add the styles to `src/styles/site.css` (depends on 4): `.eyebrow`;
      `.cta-primary` (accent background, `--accent-fg` text, accent border)
      with `.cta-primary:hover` and `.cta-primary:visited:not(:hover)` pinned
      to `--accent-fg` so the existing `.cta:hover` and
      `.cta:visited:not(:hover)` rules cannot win; the identity and capability
      typography; and `.contact-list` / `.contact-list a` with
      `display: inline-flex` and `min-block-size: 24px`. Tokens only, no colour
      literal, no `transition`, no `animation`. — DoD:
      `node scripts/check-contrast.mjs` passes; `node --test test/a11y.test.ts`
      passes; `node --test test/link-cascade.test.ts` passes.

- [ ] 10. Add `.contact-list a` to `TARGET_SELECTORS` in `test/a11y.test.ts`
      (depends on 9). — DoD: the hit-area floor is enforced for the new links,
      and the test fails if the rule is deleted.

- [ ] 11. Update `scripts/check-dist.mjs`'s `checkHomePage()` (depends on 4,
      7): expect zero `<details open>` and two `<summary><h2` on
      `dist/index.html`, and add a home-page JSON-LD check that finds exactly
      one `application/ld+json` block, parses it, and asserts the `Person`'s
      five fields plus its three ordered `sameAs` entries and the `WebSite`'s
      three fields. Leave `checkJsonLd()`'s journal/ADR scoping alone. — DoD:
      `npm run build && node scripts/check-dist.mjs` exits 0 and prints the
      `dist/index.html` byte count; a deliberate removal of the JSON-LD makes
      it exit non-zero (verify, then revert).

- [ ] 12. Correct the loyalty link: in
      `src/content/projects/mctl-loyalty.en.md` and
      `src/content/projects/mctl-loyalty.ru.md` change
      `    url: https://labs-mctl-loyalty.mctl.ai` to
      `    url: https://rewards.mctl.ai`, and update the `mctl-loyalty` row in
      `test/projects.test.ts` (wherever `EXPECTED_LINKS` lives) to
      `  { slug: 'mctl-loyalty', url: 'https://rewards.mctl.ai', en: 'Service', ru: 'Сервис' },`.
      Change nothing else on `/work/`. — DoD:
      `node --test test/projects.test.ts test/work.test.ts` passes; after
      `npm run build`, `grep -r labs-mctl-loyalty dist/` finds nothing and
      `dist/work/index.html` contains `https://rewards.mctl.ai`.

- [ ] 13. Write the journal entry (depends on 4-12):
      `src/content/journal/<merge-date>-q15-conversion-first-home.md` with
      `status: in_progress`, `service: portfolio`,
      `issue: https://github.com/mctlhq/portfolio/issues/98`,
      `proposal_slug: issue-98-q15-conversion-first-home-role-history-c`,
      `visibility: public`, bilingual `title` and `decided`, `issue_opened_at`,
      `interventions: []`, and none of `pr`, `merged_at`, `release`,
      `released_at`, `deployed_at`. Add `seoTitle` (and `indexing`) so the
      computed title stays inside the 65/75-character budget. — DoD:
      `node --test test/journal.test.ts test/journal-status.test.ts test/journal-build.test.ts test/title.test.ts`
      passes and exactly one entry in `src/content/journal/` is `in_progress`.

- [ ] 14. Full gate run (depends on all above): `npm run vendor && npm test`,
      `npm run build`, `node scripts/check-dist.mjs`,
      `node scripts/check-links.mjs`. — DoD: all four exit 0;
      `check-links` lists `https://rewards.mctl.ai`,
      `https://www.linkedin.com/in/dmitriimashkov`,
      `https://t.me/dmitriimashkov` and `mailto:hello@dmitriimashkov.com`
      among the skipped off-origin/other-scheme hrefs by name, so none of them
      is silently dropped; `dist/index.html` is under 40960 bytes.

## Tests

- [ ] T1. `test/ui.test.ts`: every new key present in both languages, exact
      values (tasks 2-3), object-array parity, and `href`/`text` identical
      across languages for `contactItems`.
- [ ] T2. `test/home.test.ts`: two `<Details>` tags with `heading` and none
      with `open`; the `.ctas` nav has exactly two links, first `#contact`
      then `/work/`; `ctaColophon` absent from the page; the eyebrow renders
      through `<Lang>` bound to `ui.heroEyebrow`.
- [ ] T3. Built-page assertions over `dist/index.html` (in `test/home.test.ts`
      against a built tree, or in `scripts/check-dist.mjs`): each of the three
      `aboutParagraphs` and each of the three `capabilityItems` terms appears
      in both languages (`.l.en` and `.l.ru`), and the four contact hrefs each
      appear exactly once.
- [ ] T4. No-disclosure proof: a test asserts that no `<details>` element in
      `dist/index.html` contains the text of any `aboutParagraphs`,
      `capabilityItems` or `contactItems` entry.
- [ ] T5. `test/seo.test.ts`: `homeJsonLd` field-by-field (task 8), parsed as
      JSON, never matched as a substring.
- [ ] T6. `dist/index.html` contains exactly one `application/ld+json` block
      and `dist/colophon/journal/*/index.html` still contains its
      `BreadcrumbList` (task 11).
- [ ] T7. `test/csp.test.ts` and `node scripts/check-headers.mjs` pass
      unchanged — no new executable inline script, inline-script hash
      unchanged.
- [ ] T8. `test/projects.test.ts` carries the `rewards.mctl.ai` row and
      `dist/` contains no `labs-mctl-loyalty.mctl.ai` (task 12).
- [ ] T9. `test/a11y.test.ts` with `.contact-list a` in `TARGET_SELECTORS`,
      and `node scripts/check-contrast.mjs`.
- [ ] T10. `test/nav.test.ts`, `test/footer.test.ts` and `test/title.test.ts`
      pass unchanged.

## Rollback

Every change in this cycle is a source edit in one pull request; nothing is
stateful.

- Before merge: close the pull request. No platform state has changed.
- After merge, before release: revert the merge commit on a branch and merge
  the revert through the normal gates. The home page returns to its
  `249feed` structure, `mctl-loyalty` returns to
  `https://labs-mctl-loyalty.mctl.ai`, and the `in_progress` journal entry
  disappears with it (leaving zero `in_progress` entries, which is valid).
- After release and deployment: `mctl_rollback_service` with the previous
  image tag (`0.1.27` at the time of writing; confirm with
  `mctl_get_service_config` for team `labs`, service `portfolio`) restores the
  running site immediately; the source revert then follows through the normal
  DevLoop. No DNS, ingress or domain change is involved, so no Cloudflare or
  `mctl_add_custom_domain` action is part of a rollback.
- Partial rollback is available and independent: the `mctl-loyalty` link
  correction (task 12) and the JSON-LD (tasks 6-8, 11) can each be reverted on
  their own without touching the page copy.
