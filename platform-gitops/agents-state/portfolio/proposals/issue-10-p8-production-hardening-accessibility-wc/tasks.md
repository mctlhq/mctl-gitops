# Tasks: issue-10-p8-production-hardening-accessibility-wc

- [ ] 1. Narrow the absolute-URL guard in `scripts/check-dist.mjs` so a
      `<link rel="canonical">` / `rel="alternate"` is exempt while every other
      `<link>`, `<script>`, `<img>` and `<source>` is still rejected — DoD:
      the loop over `SUBRESOURCE_RE` parses `rel` and skips only those two
      values; a hand-made fixture with `<link rel="stylesheet" href="https://…">`
      still fails; `npm test` passes. Do this first: without it the build
      breaks the moment task 4 lands.

- [ ] 2. Add the `<style`-element and `style="`-attribute rejection to
      `scripts/check-dist.mjs` (depends on 1) — DoD: any `dist/**/*.html`
      containing `<style` or `style="` makes the script exit non-zero naming
      the file; a clean build still passes.

- [ ] 3. Add `@astrojs/sitemap` — DoD: it is in `devDependencies` of
      `package.json` at a version whose peer range accepts `astro@^7`;
      `package-lock.json` was regenerated with `npm install --package-lock-only`
      (never a plain `npm install`) and still lists every
      `<pkg>-binding-<platform>` entry it listed before; `astro.config.mjs`
      registers `sitemap()` in `integrations` with a `filter` dropping any path
      starting with `/404` or `/dev/`; `npm run build` emits
      `dist/sitemap-index.xml` and `dist/sitemap-0.xml`.

- [ ] 4. Add `checkSitemap()` to `scripts/check-dist.mjs` (depends on 1, 3) —
      DoD: it parses the `site` origin out of `astro.config.mjs`, follows every
      `<loc>` in `dist/sitemap-index.xml` to its child sitemap, unions their
      `<loc>` values, and compares against `/`, `/work/`, `/approach/`,
      `/colophon/` plus one URL per public journal and per public ADR id from
      `idsByVisibility()`; a missing URL, an extra URL, any private id and any
      `/404` or `/dev/` entry each fail with a message naming the URL.

- [ ] 5. Append `Sitemap: https://dmitriimashkov.com/sitemap-index.xml` to
      `public/robots.txt` (depends on 3) — DoD: the existing
      `User-agent: *` / `Disallow:` pair is unchanged and the new line is
      present; a container serving the image returns it at `/robots.txt`.

- [ ] 6. Add `src/lib/seo.ts` with `clampDescription(text, max = 160)` — DoD:
      it trims at a word boundary, appends a single `…` only when it actually
      truncated, returns the input untouched when it already fits, and never
      returns more than `max` characters; unit-tested in `test/seo.test.ts`.

- [ ] 7. Write `public/og.svg` (depends on nothing) — DoD:
      `viewBox="0 0 1200 630"`, text only, no `<image>`, no `data:`, no
      `xlink:href`, no raster file extension; carries exactly
      `Dmitrii Mashkov`, `Platform engineering with AI on proven open source`
      and `dmitriimashkov.com`; opens without error and is under 4 KB.

- [ ] 8. Extend `src/layouts/Base.astro` (depends on 6, 7) — DoD: `Props` is
      `{ title: string; description: string; noindex?: boolean }` with
      `description` required; `<head>` emits `<meta name="description">`,
      `<link rel="canonical">` (absolute, trailing slash, omitted when
      `noindex`), `<meta name="robots" content="noindex">` when `noindex`,
      `og:type`, `og:site_name`, `og:title`, `og:description`, `og:url`,
      `og:image`, `og:locale`, `twitter:card="summary_large_image"`,
      `twitter:title`, `twitter:description`, `twitter:image`; image URLs are
      `new URL('/og.svg', Astro.site)`; the inline bootstrap script is byte-for-byte
      unchanged so its CSP hash does not move.

- [ ] 9. Pass a description from every page (depends on 8) — DoD:
      `index.astro`, `work.astro`, `approach.astro` and `colophon/index.astro`
      pass the four literal strings fixed in requirements.md, character for
      character; `404.astro` passes its string plus `noindex`;
      `colophon/journal/[...slug].astro` passes
      `clampDescription(entry.data.decided.en)`;
      `colophon/adr/[...slug].astro` passes the clamped ADR template;
      `npm run check` passes with no missing-prop error.

- [ ] 10. Create `security-headers.conf` at the repository root — DoD: exactly
      eight `add_header ... always` lines — the six existing values verbatim
      plus `Cross-Origin-Opener-Policy "same-origin"` and
      `Cross-Origin-Resource-Policy "same-origin"` — with the CSP unchanged
      except for keeping `__SCRIPT_SRC_HASHES__`; no `'unsafe-inline'` and no
      external origin anywhere in the file.

- [ ] 11. Rewrite `nginx.conf` to include the snippet (depends on 10) — DoD:
      no `add_header` for any of the eight headers remains; exactly one
      `include /etc/nginx/security-headers.conf;` at server level and in each of
      `= /healthz`, `= /readyz`, `/_astro/` and `/`; `/_astro/` keeps its
      `expires` and `add_header Cache-Control`; `location /` keeps
      `error_page 404 /404.html` and its `try_files`;
      `grep -c "add_header Content-Security-Policy" nginx.conf security-headers.conf`
      totals 1.

- [ ] 12. Update the `Dockerfile` (depends on 10, 11) — DoD: it copies both
      `nginx.conf` and `security-headers.conf`; `nginx.conf` goes to
      `/etc/nginx/conf.d/default.conf` unmodified; the `sed` of
      `__SCRIPT_SRC_HASHES__` now targets `security-headers.conf`, written to
      `/etc/nginx/security-headers.conf` (not under `conf.d/`, which the stock
      image globs); the two existing `grep` assertions run against the rendered
      snippet; `nginx -t` runs and passes; the temp files are removed.

- [ ] 13. Add `test/nginx.test.ts` to `npm test` (depends on 10, 11) — DoD: it
      asserts zero `add_header` for the eight headers in `nginx.conf`, exactly
      one per header in `security-headers.conf`, five includes in the right
      blocks, and that the CSP string contains `__SCRIPT_SRC_HASHES__`, no
      `'unsafe-inline'` and no `http://`/`https://`; the file is added to the
      `test` script in `package.json`.

- [ ] 14. Add `scripts/check-headers.mjs <base-url>` (depends on 10) — DoD: it
      `HEAD`s `/`, `/healthz`, an `/_astro/` asset path passed in or discovered
      from the home page markup, and a path that does not exist; it exits
      non-zero unless every response carries all eight headers with the
      expected values, the missing path returns 404, and the CSP contains
      `sha256-` and no `http://`/`https://`; it prints one line per URL.

- [ ] 15. Wire the runtime header check into `.github/workflows/build.yml`
      (depends on 12, 14) — DoD: the `build` job builds with `load: true`, runs
      the container with a published port, waits for `/healthz` to answer, runs
      `node scripts/check-headers.mjs http://127.0.0.1:<port>`, and stops the
      container; a deliberately removed header makes the job fail. AGENTS.md
      permits editing this workflow only to make the gate stricter — this does.

- [ ] 16. Add `scripts/check-contrast.mjs` to `npm test` — DoD: it reads the
      hex tokens from `public/assets/mctl/mctl.css`, resolves the pairs used by
      `src/styles/site.css` for both `data-theme` values (`--surface-fg`,
      `--surface-fg-muted`, `--accent` over `--surface-bg` and
      `--surface-elevated`; `--accent-fg` over `--accent`), computes WCAG 2.x
      contrast ratios, prints each pair with its ratio, and exits non-zero
      below 4.5:1 for text or 3:1 for the focus ring; any exemption is a named
      entry in the script with a comment, never a lowered threshold.

- [ ] 17. Add `test/a11y.test.ts` to `npm test` — DoD: it asserts
      `src/styles/site.css` keeps a `:focus-visible` outline rule and a
      `min-block-size` of at least 24 px on `.site-nav a`,
      `.toggle-group button`, `.site-footer a`, `.cta` and `.block > summary`;
      that `site.css` declares no `animation` or `transition`; and that
      `src/i18n/Lang.astro` emits `lang="ru"` on the Russian span.

- [ ] 18. Write `docs/accessibility-checklist.md` (depends on 16, 17) — DoD:
      one row per issue item (keyboard operation of every `<details>`, focus
      visibility on links and buttons, contrast in both themes, `lang` on RU
      blocks, heading hierarchy, link purpose, SVG text alternatives, target
      size at least 24 px, no motion), each marked pass / fail / reviewer step
      with a note citing the file and the evidence; every failure carries a
      documented exception and the follow-up issue to open; the screen-reader
      sweep and the visual focus confirmation are labelled reviewer steps.

- [ ] 19. Write `docs/hardening-notes.md` (depends on 11, 12) — DoD: a table
      with one row per header (the six existing plus COOP and CORP) stating
      landed yes/no and why; a section recording that `style-src` already
      carried no `'unsafe-inline'` because `build.inlineStylesheets: 'never'`
      was already set in `astro.config.mjs`, and that the single inline script
      is allowed by SHA-256 rather than a keyword; a section on the SVG Open
      Graph card and its limited platform support; and an empty section headed
      "Lighthouse mobile (reviewer step, post-deployment)" for the four pages.

- [ ] 20. Add the journal entry for this cycle under `src/content/journal/`
      (depends on all of the above) — DoD: `YYYY-MM-DD-<slug>.md` with
      `service: portfolio`, the issue and PR URLs, `proposal_slug:
      issue-10-p8-production-hardening-accessibility-wc`,
      `visibility: public`, bilingual `title` and `decided`, the timestamps
      known at commit time and `interventions`; `npm test` and
      `scripts/check-dist.mjs` pass with the new colophon and sitemap entries.

## Tests

- [ ] T1. `npm test` passes, including the new `test/nginx.test.ts`,
      `test/a11y.test.ts`, `test/seo.test.ts`, `scripts/check-contrast.mjs` and
      the existing eleven suites.
- [ ] T2. `npm run build && node scripts/check-dist.mjs` passes: sitemap URL
      set exact, no private id anywhere, no absolute-URL subresource other than
      the exempt canonical, no `<style` element or `style="` attribute, and
      `dist/index.html` still under the 40 KB cap.
- [ ] T3. `npm run check` (`astro check`) reports no error — proves every page
      supplies the now-required `description` prop.
- [ ] T4. `node scripts/csp-hash.mjs` still prints exactly one `sha256-` token:
      the head metadata added no second inline script and did not change the
      bootstrap script's bytes.
- [ ] T5. `docker build .` succeeds, including the new `nginx -t` step; then
      `docker run` the image and `node scripts/check-headers.mjs
      http://127.0.0.1:<port>` passes on `/`, `/healthz`, an `/_astro/` asset
      and a missing path (the missing path answering 404 with the bilingual
      body).
- [ ] T6. Negative check, run once by hand during implementation and recorded
      in `docs/hardening-notes.md`: delete the `include` from one `location`
      block, rebuild, and confirm `scripts/check-headers.mjs` fails naming the
      missing headers. This is what proves the gate is real.
- [ ] T7. `grep -c "add_header Content-Security-Policy" nginx.conf security-headers.conf`
      totals 1, and `grep -c "add_header" nginx.conf` counts only the
      `/_astro/` `Cache-Control` line.
- [ ] T8. Reviewer steps, appended to `docs/hardening-notes.md` after
      deployment, not gating this cycle: Lighthouse mobile on the four pages; a
      HAR of every page showing same-origin requests only; the browser console
      free of CSP violations on every page in both themes and both languages;
      a keyboard-only pass over every `<details>` and toggle.

## Rollback

The change is static assets plus nginx configuration; there is no state to
undo.

1. **Deployed regression** (headers wrong, a page 500s, the CSP blocks
   something): `mctl_rollback_service` to the previous image tag. The previous
   image carries its own complete `/etc/nginx/conf.d/default.conf` with the
   headers inline, so the rollback is self-contained — no snippet file is
   expected by it.
2. **Broken before deployment**: the image build fails at `nginx -t` or at the
   `grep` assertions, or CI fails at `scripts/check-headers.mjs`, so nothing
   reaches production. Fix forward on the branch.
3. **Partial revert**: the seven pieces are independent except for the ordering
   in tasks 1/4/8. Reverting the sitemap means removing the integration from
   `astro.config.mjs`, the `Sitemap:` line from `public/robots.txt` and
   `checkSitemap()` from `scripts/check-dist.mjs`. Reverting the nginx
   extraction means restoring the repeated `add_header` blocks in `nginx.conf`,
   deleting `security-headers.conf` and pointing the Dockerfile's `sed` back at
   `nginx.conf`. Reverting the head metadata means dropping the new tags from
   `Base.astro` and the `description` prop from the seven pages — and, if the
   canonical link goes, the `check-dist.mjs` exemption from task 1 may stay; it
   only widens what is allowed for two `rel` values.
4. **COOP/CORP suspected of breaking a client**: remove those two lines from
   `security-headers.conf` and rebuild. Nothing else depends on them, and the
   other six headers are unaffected.
