# Tasks: issue-195-improve-home-search-snippet-and-bilingua

All copy referenced below is the exact copy in requirements.md, "Exact copy
contract" and "Journal entry copy". Copy it character for character,
including the em dash `—` (U+2014) and `&`.

- [ ] 1. In `src/i18n/ui.ts`, set `homeTitle.en` and `homeTitle.ru` to `Dmitrii Mashkov — Platform Engineering & AI`. Add `homeDescription` with en `Platform engineering, Kubernetes, GitOps and AI delivery by Dmitrii Mashkov. Explore projects and engineering notes, or get in touch on Telegram.` and ru `Дмитрий Машков: платформенная инженерия, Kubernetes, GitOps и AI. Проекты, инженерные заметки и контакт в Telegram.` In `contactItems.en`, set the Telegram `text` to `Dmitrii Mashkov on Telegram — @dmitriimashkov`. In `contactItems.ru`, set it to `Дмитрий Машков в Telegram — @dmitriimashkov`. Leave `label`, `href` and the other three entries unchanged. Update the `homeTitle` and `contactItems` comments to match. — DoD: the dictionary holds exactly this copy; `astro check` is clean.
- [ ] 2. (depends on 1) In `src/pages/index.astro`, replace the literal `description="..."` with `description={ui.homeDescription.en}`. Change the contact anchor to `<Lang en={item.text} ru={ui.contactItems.ru[index].text} />`. — DoD: the template holds no description literal; no new link or element is added.
- [ ] 3. In `src/lib/seo.ts` `homeJsonLd()`, add `alternateName: 'Дмитрий Машков'` to the Person node directly after `name`, and update the JSDoc to list the seven Person entries and the reason (issue #195). Leave WebSite untouched. — DoD: the function stays pure and zero-import apart from `./adr.ts`.
- [ ] 4. (depends on 3) In `scripts/check-dist.mjs`, add `'alternateName'` to `HOME_PERSON_KEYS` and an exact-value check reporting `Person.alternateName is "<value>", expected "Дмитрий Машков"`. Update the `checkHomeJsonLd` docstring. — DoD: check-dist accepts the new build and rejects a graph missing or misvaluing `alternateName`.
- [ ] 5. Add `src/content/journal/2026-11-05-q24-home-snippet-in-both-scripts.md` with `service: portfolio`, `issue: https://github.com/mctlhq/portfolio/issues/195`, `proposal_slug: issue-195-improve-home-search-snippet-and-bilingua`, `status: in_progress`, `visibility: public`, `indexing: noindex`, the `title`, `seoTitle` and `decided` copy from requirements.md, `issue_opened_at: '2026-11-05T22:58:58Z'` and `interventions: []`. Omit `pr`, `merged_at`, `release`, `released_at`, `deployed_at` and `proposal_approved_at`. — DoD: the journal schema, `checkJournalCollection` and `test/indexing.test.ts` / `test/title.test.ts` pass; no timestamp is invented.
- [ ] 6. (depends on 1-5) Update the tests listed below. Run `npm test`, then `npm run build` (whose `prebuild` runs vendor and tests), then `node scripts/check-dist.mjs`. Confirm `git diff --stat` touches no `package.json`, `package-lock.json`, `AGENTS.md`, `.github/workflows/claude-review.yml`, `.github/workflows/release-please.yml`, `.github/dependabot.yml`, ADR-0004, `Dockerfile` or `nginx.conf`. — DoD: all three commands pass.

## Tests

- [ ] T1. `test/ui.test.ts`: replace the homeTitle test so it asserts both entries equal `Dmitrii Mashkov — Platform Engineering & AI`, are equal to each other, and contain no Cyrillic (`/[Ѐ-ӿ]/`).
- [ ] T2. `test/ui.test.ts`: add a test asserting `ui.homeDescription.en` and `.ru` equal the exact contract strings.
- [ ] T3. `test/ui.test.ts`: update the contactItems `deepEqual` to the new Telegram `text` values. Keep "href identical across languages" for all four entries. Keep "text identical across languages" for Email, LinkedIn and GitHub. For Telegram, assert the EN and RU `text` values exactly.
- [ ] T4. `test/home.test.ts`: in the hero-name test, remove the `description="..."` stripping (no literal remains). Assert the template contains `description={ui.homeDescription.en}` and contains no `description="` attribute. Update the comment.
- [ ] T5. `test/home.test.ts`: in the contactItems dist test, check the RU span against `ui.contactItems.ru[i].text`. Add an assertion that the built Telegram anchor contains both `<span class="l en">Dmitrii Mashkov on Telegram — @dmitriimashkov</span>` and `<span class="l ru" lang="ru">Дмитрий Машков в Telegram — @dmitriimashkov</span>`, and that `dist/index.html` has exactly one `href="https://t.me/dmitriimashkov"` anchor.
- [ ] T6. `test/home.test.ts`: new dist test. It asserts exactly one `<title>`, `meta[name="description"]`, `meta[property="og:title"]`, `meta[property="og:description"]`, `meta[name="twitter:title"]` and `meta[name="twitter:description"]` in `dist/index.html`. After decoding `&amp;` (and any other HTML entity Astro emits), the titles equal `ui.homeTitle.en` and the literal `Dmitrii Mashkov — Platform Engineering & AI`, and the descriptions equal `ui.homeDescription.en`.
- [ ] T7. `test/home.test.ts` (built JSON-LD test) and `test/seo.test.ts`: the Person key list becomes the seven keys including `alternateName`. Assert `person.alternateName === 'Дмитрий Машков'` and `person.name === 'Dmitrii Mashkov'`. Keep the sameAs order, the WebSite exact keys/values (assert WebSite has no `alternateName`), the forbidden-field test and the purity test unchanged in substance.
- [ ] T8. `test/check-dist.test.ts`: add `alternateName: 'Дмитрий Машков'` to the well-formed fixture Person. Add one test where the fixture lacks `alternateName` (expects `Person node keys are`), and one where it has a different value (expects `Person.alternateName is`).
- [ ] T9. Run `npm test`, `npm run build` and `node scripts/check-dist.mjs`. All pass, including `check-no-metrics`, csp, link and journal tests.

## Rollback

All changes are source-only and ship through the normal release. To roll
back, revert the implementation merge commit on a branch and merge it through
the usual PR gates. release-please then cuts a patch release and
the operator deploys the resulting tag with mctl MCP tools only. For an urgent rollback, use
`mctl_rollback_service(team_name=labs, component_name=portfolio,
target_tag=<previous tag>)`, per AGENTS.md (mctl tools only). No data,
schema or infrastructure state needs reverting. Mark the journal entry
`abandoned` (with a bilingual reason, through the proposal/PR process) only
if the cycle is explicitly cancelled before merge.

## Detector verification

The new `Person.alternateName` value check extends an existing build-output
detector. Prove it both ways: the valid built graph passes, and the deliberate
missing/wrong alias fixtures fail. Then temporarily revert only the new
alternateName value-check implementation and confirm the wrong-value detector
test fails. Restore the implementation and confirm the test passes. Do not
commit the temporary reversion. Keep zero-third-party and CSP checks intact.

## Deployment boundary

Release-please may create the release tag; deploy or roll back the personal site
only with mctl MCP tools, as AGENTS.md requires. No manual GitHub deployment
dispatch, kubectl mutation, DNS edit, or hand-edited GitOps values is part of
this cycle. Do not claim a deployment from a merged implementation PR alone.
