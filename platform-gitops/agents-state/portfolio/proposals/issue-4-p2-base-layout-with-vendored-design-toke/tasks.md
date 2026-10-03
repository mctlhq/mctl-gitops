# Tasks: issue-4-p2-base-layout-with-vendored-design-toke

- [ ] 1. Upgrade `astro` from `^5.0.0` to `^7.0.0` in `package.json`, delete and
      regenerate `package-lock.json` with `npm install`, and work through the
      official 5 → 6 and 6 → 7 upgrade guides. Adapt `astro.config.mjs`
      (`output`, `site`, `trailingSlash`, `integrations` are all still valid
      options) and `tsconfig.json` (`astro/tsconfigs/strict`) to any breaking
      change; add `@astrojs/markdown-remark` as an explicit devDependency only
      if `astro check` demands it (it is a peer in v7, not a direct dep). Keep
      `@astrojs/check@^0.9.10` and `typescript@^5`. — DoD: `npm ls astro`
      reports 7.x; `npm run build` exits 0; `npm run check` exits 0 with zero
      errors; `find dist -name '*.js'` prints nothing. Land as its own commit
      so it is revertible independently of the rest.

- [ ] 2. Confirm the `Dockerfile` builder base still satisfies Astro 7's
      `engines.node >=22.12.0` (depends on 1) — `node:24-alpine` does. Leave the
      pinned tag+digest untouched unless a change is actually required; if it
      is, pin the new tag **and** digest per `AGENTS.md`. — DoD:
      `docker build .` succeeds locally and `.github/workflows/build.yml`
      passes on the PR.

- [ ] 3. Write `scripts/vendor-assets.mjs` (dependency-free Node ESM), add
      `"vendor": "node scripts/vendor-assets.mjs"` and
      `"prebuild": "npm run vendor"` to `package.json` (depends on 1). The
      script must: (a) fetch `mctl.css`, `global.css`, `prose.css` from
      `https://ui.mctl.ai/0.5.0/` into `public/assets/mctl/`, refusing to write
      anything if the first line of `mctl.css` does not contain `0.5.0`;
      (b) resolve Onest (300/400/500/600/700), Instrument Serif (400 normal and
      400 italic) and JetBrains Mono (400/500/600/700) from their
      `@fontsource` npm tarballs, extracting the `latin`, `latin-ext`,
      `cyrillic` and `cyrillic-ext` subset `woff2` files into
      `public/assets/fonts/`; (c) copy each package's `LICENSE` to
      `public/assets/fonts/LICENSES/<family>.txt`; (d) copy
      `src/styles/site.css` to `public/styles/site.css`; (e) exit non-zero if
      any licence file is missing or empty, if any requested weight/style
      resolves to no file, or if a family that offers a `cyrillic` subset ends
      up with none vendored; (f) when the network is unreachable, succeed
      silently if the existing vendored tree is present and passes the version
      check, and fail otherwise. — DoD: `npm run vendor` on a clean checkout
      populates the tree; a second run leaves `git status` clean; deleting
      `public/assets/fonts/LICENSES/onest.txt` makes it exit non-zero;
      `npm run build` with the network cut still succeeds.

- [ ] 4. Have `scripts/vendor-assets.mjs` generate
      `public/assets/fonts/fonts.css` (depends on 3): one `@font-face` per
      extracted file with `font-display: swap`, the correct `font-family`,
      `font-weight`, `font-style`, `src: url('/assets/fonts/<file>')
      format('woff2')`, and the `unicode-range` for that subset taken from the
      `@fontsource` package's own per-subset CSS. — DoD: `fonts.css` exists,
      every `url()` in it resolves to a file that is present on disk, every
      rule carries a `unicode-range`, and the file count matches the
      weight × subset matrix.

- [ ] 5. Commit every vendored artifact under `public/assets/mctl/`,
      `public/assets/fonts/` and `public/assets/fonts/LICENSES/` (depends on 4).
      Commit `public/styles/site.css` as a generated-but-tracked file rather
      than ignoring it: `.gitignore` is human-only territory per `AGENTS.md`
      and must not be touched by the implementer. Note in the PR body that
      `src/styles/site.css` is its source of truth and that `prebuild`
      regenerates it. — DoD: a fresh clone with
      no network builds successfully; `public/assets/fonts/LICENSES/` holds
      three non-empty OFL texts; the first line of
      `public/assets/mctl/mctl.css` names version 0.5.0.

- [ ] 6. Create `src/i18n/ui.ts` exporting a `const ui = { … } as const`
      dictionary of `{ key: { en, ru } }` for the four navigation labels, the
      language- and theme-toggle labels, and the footer strings, plus
      `export type UiKey = keyof typeof ui` (depends on 1). — DoD:
      `npm run check` passes; every key has a non-empty `en` and `ru`.

- [ ] 7. Create `src/i18n/Lang.astro` with `en` and `ru` props rendering
      `<span class="l en">{en}</span><span class="l ru" lang="ru">{ru}</span>`
      (depends on 6). — DoD: the component compiles under `astro check`; the
      Russian span carries `lang="ru"`.

- [ ] 8. Create `src/styles/site.css` (depends on 1) with:
      `:root[data-lang="en"] .l.ru { display: none }`;
      `:root[data-lang="ru"] .l.en { display: none }`; the analogous
      `:root[data-theme="dark"] .t.light` / `:root[data-theme="light"] .t.dark`
      pair for the toggle groups; a `:root:not([data-theme])`
      `prefers-color-scheme: light` fallback; a max content width; a
      `padding-inline` of at least 16px at every viewport; `overflow-wrap:
      anywhere` on long mono strings; and a `:focus-visible` ring built on the
      design system's `--focus-ring`. Use only `@mctlhq/css` semantic
      variables (`--surface-*`, `--accent*`, `--font-*`), never raw `--mctl-*`
      tokens. — DoD: no hard-coded hex colour in the file; the file is under
      3 KB.

- [ ] 9. Create `src/layouts/Base.astro` (depends on 4, 7, 8) with
      `<html lang="en" data-lang="en" data-theme="dark">` and a `<head>` in
      this exact order: charset meta, viewport meta, the single
      `<script is:inline>`, the five stylesheet `<link>`s
      (`/assets/mctl/mctl.css`, `/assets/mctl/global.css`,
      `/assets/mctl/prose.css`, `/assets/fonts/fonts.css`,
      `/styles/site.css`), `<title>` from a `title` prop, and
      `<link rel="icon" type="image/svg+xml" href="/favicon.svg" />`. Body
      renders `<Nav />`, `<slot />`, `<Footer />`. The `is:inline` directive is
      mandatory — without it Astro hoists the script into `_astro/*.js` and
      breaks three acceptance criteria at once. Use the 341-byte reference
      implementation from `design.md`. — DoD: `dist/index.html` contains exactly
      one `<script>`, it is inline, it precedes every `<link rel="stylesheet">`,
      and `wc -c` of its text content is ≤ 400.

- [ ] 10. Add `build: { inlineStylesheets: 'never' }` to `astro.config.mjs`
      (depends on 1) so that any component-scoped style becomes a
      `_astro/*.css` link rather than an inline `<style>` element, which the
      existing `style-src 'self'` header would block. — DoD:
      `grep -r '<style' dist/` returns nothing.

- [ ] 11. Create `src/components/Nav.astro` (Home / Work / Approach /
      Colophon, every label through `Lang`, inside a `<nav>` with a bilingual
      `aria-label`) and `src/components/Footer.astro` (link to
      `https://github.com/mctlhq`, link to `/colophon/` with the trailing
      slash that `trailingSlash: 'always'` requires, and a
      `<span data-release>` placeholder carrying the `package.json` version)
      (depends on 7). — DoD: both render through `Base`; every user-facing
      string in both has an EN and a RU form; no link 404s in the built site
      except `/colophon/`, which is out of scope and must be listed as a known
      pending route in the PR body.

- [ ] 12. Create `src/components/LangToggle.astro` and
      `src/components/ThemeToggle.astro` (depends on 8, 11) using the
      duplicated-group pattern from `design.md`: two wrapper elements per
      toggle (`.l.en` / `.l.ru` for language, `.t.dark` / `.t.light` for
      theme), each containing both `<button type="button">` options with
      *statically correct* `aria-pressed` values for that state, and
      `data-set-lang` / `data-set-theme` attributes carrying the target value.
      Button text labels go through `Lang`. — DoD: after a reload with
      `localStorage.lang = 'ru'`, the only `aria-pressed="true"` in the
      accessibility tree is on the RU button; same for theme; no JavaScript
      touches `aria-pressed`.

- [ ] 13. Write `scripts/csp-hash.mjs` (depends on 9): read every
      `dist/**/*.html`, extract the text content of each inline `<script>`,
      assert there is exactly one distinct body and that it is ≤ 400 bytes,
      and print `sha256-<base64>` tokens space-separated on stdout. Hash the
      built output, never the `.astro` source. — DoD:
      `node scripts/csp-hash.mjs` prints one `sha256-…` token; introducing a
      second distinct inline script makes it exit non-zero; padding the script
      past 400 bytes makes it exit non-zero.

- [ ] 14. Change `script-src 'self'` to `script-src 'self'
      __SCRIPT_SRC_HASHES__` in **all five** `Content-Security-Policy`
      `add_header` lines in `nginx.conf` (depends on 13). — DoD:
      `grep -c '__SCRIPT_SRC_HASHES__' nginx.conf` reports 5.

- [ ] 15. Add gzip to the `server` block of `nginx.conf` (depends on 14):
      `gzip on; gzip_comp_level 6; gzip_min_length 256; gzip_vary on;
      gzip_types text/css text/plain application/javascript image/svg+xml
      application/json;`. Do not list `text/html` (always compressed) or
      `font/woff2` (already compressed). Required to meet the 30 KB budget —
      the stock image ships `#gzip  on;`, i.e. off, and the three vendored
      stylesheets alone are 22,402 bytes uncompressed against 4,781 gzipped. —
      DoD: `curl -sI -H 'Accept-Encoding: gzip' http://localhost/assets/mctl/mctl.css`
      against the built image shows `Content-Encoding: gzip`.

- [ ] 16. Update `Dockerfile` (depends on 13, 14): builder runs
      `npm run build && node scripts/csp-hash.mjs > /app/csp-script-src.txt`;
      runtime stage copies `nginx.conf` to `/tmp/nginx.conf` and
      `csp-script-src.txt` from the builder, then a single `RUN` that
      `sed`s with a **global** flag (`s|…|…|g` — five occurrences, unlike
      `mctl-docs`' one), writes `/etc/nginx/conf.d/default.conf`, asserts
      `grep -q "sha256-"`, asserts `! grep -q "__SCRIPT_SRC_HASHES__"`, and
      removes the temporaries. — DoD: `docker build .` succeeds; deliberately
      emptying `csp-script-src.txt` makes the build fail at the `grep`.

- [ ] 17. Rewrite `src/pages/index.astro` and `src/pages/404.astro` to use
      `Base` with a `title` prop and bilingual body content, deleting their
      hand-written `<!doctype html>` / `<head>` blocks (depends on 9, 11, 12).
      — DoD: neither file contains `<!doctype`; both build; `/404.html` is
      produced and `nginx.conf`'s `error_page 404 /404.html` still resolves.

- [ ] 18. Update `README.md` only if `AGENTS.md` permits — it does not; leave
      documentation of the new scripts to the PR body and to a `scripts/`
      header comment instead. — DoD: no human-only file
      (`README.md`, `AGENTS.md`, `LICENSE`, `.gitignore`, `.github/**`,
      `release-please-config.json`, `.release-please-manifest.json`) is
      modified by this PR.

## Tests

- [ ] T1. `npm ls astro` reports 7.x; `npm run build` and `npm run check` both
      exit 0.
- [ ] T2. `find dist -name '*.js' | wc -l` is 0 and
      `grep -r '<style' dist/ | wc -l` is 0.
- [ ] T3. Exactly one `<script>` in `dist/index.html`; extract its text content
      and assert `wc -c` ≤ 400; assert it appears before the first
      `<link rel="stylesheet">` in the document.
- [ ] T4. `head -1 public/assets/mctl/mctl.css` contains `0.5.0`;
      `ls public/assets/fonts/LICENSES/` lists three non-empty files;
      every `url()` in `public/assets/fonts/fonts.css` resolves to an existing
      file and every `@font-face` carries `font-display: swap` and a
      `unicode-range`.
- [ ] T5. `npm run vendor` twice in a row leaves `git status --porcelain`
      empty (idempotence); `npm run build` with the network disabled succeeds.
- [ ] T6. Build and run the image; `curl -sI http://localhost/` shows a CSP
      whose `script-src` contains a `sha256-` token and no `'unsafe-inline'`;
      `curl -sI -H 'Accept-Encoding: gzip' http://localhost/assets/mctl/mctl.css`
      shows `Content-Encoding: gzip`; `/healthz` and `/readyz` still return 200.
- [ ] T7. Load `/` in Chrome with JavaScript disabled: English only, fully
      styled, Onest / Instrument Serif / JetBrains Mono actually applied
      (check via DevTools "Rendered Fonts", not just the declaration), all
      navigation and footer links usable.
- [ ] T8. Load `/` in Chrome with JavaScript enabled: click RU — every `.l.en`
      hides and every `.l.ru` shows, `document.documentElement` gets
      `data-lang="ru"` and `lang="ru"`, `localStorage.lang === 'ru'`; reload
      and Russian persists with no flash of English. Repeat for the theme
      toggle against `localStorage.theme`.
- [ ] T9. After the reload in T8, inspect the accessibility tree: exactly one
      `aria-pressed="true"` per toggle and it matches the restored state.
- [ ] T10. Record a HAR of `/` in Chrome: every request is to the page's own
      origin; assert zero entries for `ui.mctl.ai`, `fonts.googleapis.com`,
      `fonts.gstatic.com`.
- [ ] T11. From the same HAR, sum transfer size excluding `*.woff2` and assert
      it is under 30 KB.
- [ ] T12. Chrome console shows zero CSP violations on `/` and on `/404.html`.
- [ ] T13. Lighthouse mobile accessibility run on `/` in dark and again in
      light: no colour-contrast failure in either.
- [ ] T14. Render `/` at 360 px width: no horizontal scrollbar
      (`document.documentElement.scrollWidth <= clientWidth`), and computed
      page padding is at least 16 px on both sides.
- [ ] T15. Set `localStorage` to throw (Chrome, cookies-and-site-data blocked):
      `/` still renders the English dark default with no uncaught exception in
      the console.

## Rollback

Nothing is deployed by this change — `MCTL_ONBOARDED` is not set, so the
release workflow only tags and no image reaches the cluster. Rollback is
therefore purely in git.

- Before merge: close the `feat/agents-*` PR. Nothing else is affected.
- After merge, whole change: `git revert -m 1 <merge-commit>` on a branch and
  open a PR. This restores the P1 skeleton exactly — the two standalone
  pages, `astro@^5.0.0`, and the untransformed `nginx.conf` / `Dockerfile`.
  No data, no migration, no external consumer to reconcile.
- After merge, partial: because task 1 is a separate commit, the Astro 7
  upgrade can be reverted on its own (`git revert <upgrade-commit>`) while
  keeping the layout, or vice versa. If the layout is reverted but the
  upgrade kept, re-run `npm install` to restore the lockfile.
- If the problem appears only in the built image (bad CSP hash, blocked
  inline script, unstyled page): the previous image tag is still in
  `ghcr.io/mctlhq/portfolio`, so `mctl_rollback_service` with the prior semver
  is the fast path once the service is onboarded. Until then, a revert PR plus
  a fresh release-please tag is the only route, and it is fast because the
  image is rebuilt from scratch on every tag.
- The vendored files under `public/assets/` are inert on their own; if a
  revert leaves them behind, deleting the directory has no effect on the P1
  site, which references none of them.
