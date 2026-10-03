# Tasks: issue-65-q6-share-image-asset-hashing-cache-lifet

- [ ] 1. Cut a fresh branch from `main` and fetch the reference tree.
  Branch off current `main` (do not branch from, reuse, or push to
  `feat/agents-issue-50-q6-share-image-font-shift-cache-lifetime`). Fetch the
  reference: `git fetch origin
  'refs/heads/feat/agents-issue-50-q6-share-image-font-shift-cache-lifetime'`
  makes `2a37d4b` resolvable. — DoD: `git rev-parse 2a37d4b` succeeds; the new
  branch's tip is `main`; the reference branch on the remote is unchanged.

- [ ] 2. Reproduce `2a37d4b`'s tree onto the new branch (depends on 1).
  Read `git diff main..2a37d4b` in full — it is authoritative, the issue's
  bullet list is not — then bring the tree over wholesale, e.g.
  `git checkout 2a37d4b -- .`. The 69 changed paths are: `.gitignore`,
  `nginx.conf`, `package.json`, `package-lock.json`, all of
  `public/assets/fonts/` and `public/assets/mctl/` (renames to hashed names
  plus 12 deletions), `scripts/check-contrast.mjs`, `scripts/check-dist.mjs`,
  `scripts/check-headers.mjs`, `scripts/check-no-metrics.mjs`,
  `scripts/fonts/onest-latin-{400,700}-normal.ttf` (new, committed binaries),
  `scripts/render-og.mjs` (new), `scripts/vendor-assets.mjs`,
  `src/components/CycleDiagram.astro`, `src/content/journal/2026-09-12-share-image-font-preload-cache-lifetime.md`
  (new), `src/data/assets.json` (new), `src/i18n/ui.ts`,
  `src/layouts/Base.astro`, `src/pages/approach.astro`, `src/styles/site.css`,
  `test/cache.test.ts` (new), `test/check-contrast.test.ts`,
  `test/cycle-diagram.test.ts` (new), `test/fonts.test.ts` (new),
  `test/home.test.ts`, `test/nginx.test.ts`. — DoD:
  `git diff 2a37d4b -- . ':!src/content/journal'` is empty; the two
  `scripts/fonts/*.ttf` files are tracked and non-empty; `.gitignore` carries
  both the `/public/styles/` entry and the paragraph recording why
  `scripts/fonts/` is deliberately not ignored.

- [ ] 3. Do not touch any #52 item while reproducing (depends on 2).
  Leave exactly as `2a37d4b` has them: the unhashed
  `public/assets/fonts/LICENSES/*.txt`; `docs/hardening-notes.md` and
  `docs/accessibility-checklist.md` (both still describe `og.svg` as the
  share image); the `9.6` divisor in `.hero-name`'s `min(...)`;
  `discoverHashedAssetPath()` in `scripts/check-headers.mjs` throwing rather
  than accumulating; `test/home.test.ts:132` resolving `--font-display`
  against the shadowed `mctl.css`; and the stale `public/styles/site.css`
  (unhashed) mention in `src/styles/site.css`'s header comment. — DoD:
  `git diff main..HEAD -- docs/` is empty; none of the five code sites above
  differs from `2a37d4b`.

- [ ] 4. Delta 2a — add the CI drift gate (depends on 2). In
  `.github/workflows/build.yml`'s `test` job, after `- run: npm run build`
  and before `- run: node scripts/check-links.mjs`, insert verbatim:
  ```yaml
      - name: Vendored tree matches the commit
        run: git diff --exit-code -- public/assets public/styles src/data/assets.json
  ```
  Placement is load-bearing: `npm run build` runs `prebuild`, which runs
  `npm run vendor` with network, so the step compares a freshly regenerated
  tree against the commit. — DoD: the step is present, named exactly
  `Vendored tree matches the commit`, positioned between those two steps, and
  is the only change to any file under `.github/`.

- [ ] 5. Delta 2b — record the four-preload reasoning in code (depends on 2).
  Insert this Astro comment immediately above the four
  `<link rel="preload" ...>` elements in `src/layouts/Base.astro`, character
  for character:
  ```
    {/* Four preloads, not two. The `is:inline` script below applies
        `localStorage.lang` before the body paints, so a returning Russian
        reader paints Cyrillic on the first frame -- for that reader the
        cyrillic faces are the needed pair and latin is the wasted one.
        Which two are wasted is a property of the reader, not of the build.
        Preloading latin only would move the font swap this cycle exists to
        eliminate onto every Russian reader, half the audience of a
        deliberately bilingual site. Reviewed and rejected on #64; do not
        re-litigate without changing that script. */}
  ```
  Keep all four elements and keep them before the `is:inline` script. — DoD:
  the comment is present above the four preloads; `npm run build` succeeds;
  `dist/index.html` contains no trace of the comment text; the four
  `<link rel="preload">` elements are unchanged.

- [ ] 6. Delta 3a — add the offline test seam to
  `scripts/vendor-assets.mjs` (depends on 2). As the first statement inside
  `main()`'s existing `try` block:
  ```js
    if (process.env.VENDOR_FORCE_OFFLINE === '1') {
      throw new Error('VENDOR_FORCE_OFFLINE=1 -- skipping the network step (test seam)');
    }
  ```
  Add a short comment naming it a test seam for `test/vendor-assets.test.ts`
  and noting that a plain `Error` (not a `ValidationError`) is deliberate, so
  it lands in the existing network-failure branch and routes to
  `verifyExistingTree()`. — DoD: `VENDOR_FORCE_OFFLINE=1 npm run vendor`
  prints `vendor: network step failed` followed by `vendor: existing tree ...
  is complete and valid; continuing offline.` and exits 0; plain
  `npm run vendor` behaves exactly as on `2a37d4b`.

- [ ] 7. Delta 3b — write `test/vendor-assets.test.ts` (depends on 6). It
  must mutate a tree on disk, not a string in memory. Structure:
  a helper that `mkdtemp`s a directory and `fs.cp`s `scripts/`, `public/`,
  `src/data/assets.json` and `src/styles/site.css` into it (recursive);
  a control test that `spawnSync`s `node <tmp>/scripts/vendor-assets.mjs`
  with `VENDOR_FORCE_OFFLINE: '1'` in the env and asserts `status === 0`;
  and a mutation test that, on a second copy, locates `fonts.css` through the
  copied `src/data/assets.json`'s `styles[3]`, deletes exactly one
  `@font-face { ... }` block from it, runs the same command, and asserts
  `status === 1` with `vendor: no valid existing tree` on stderr. Add a
  header comment explaining that `ROOT` in `vendor-assets.mjs` derives from
  `import.meta.url`, so running the copied script scopes every path to the
  copy and the real tree is never written. Clean up each temp directory.
  — DoD: both tests pass with no network reachable; neither leaves a temp
  directory behind; neither modifies any file under the repository.

- [ ] 8. Register the new test file (depends on 7). Append
  `test/vendor-assets.test.ts` to the `node --test` list in `package.json`'s
  `test` script, after `test/cache.test.ts`. — DoD: `npm test` runs and
  passes all of `test/fonts.test.ts`, `test/cycle-diagram.test.ts`,
  `test/cache.test.ts` and `test/vendor-assets.test.ts`.

- [ ] 9. Retarget the journal entry (depends on 2). In
  `src/content/journal/2026-09-12-share-image-font-preload-cache-lifetime.md`
  (filename unchanged), set `issue:
  https://github.com/mctlhq/portfolio/issues/65`, set `proposal_slug:
  issue-65-q6-share-image-asset-hashing-cache-lifet`, set `issue_opened_at`
  to the `createdAt` of issue #65 (`gh issue view 65 --repo mctlhq/portfolio
  --json createdAt`), and set `proposal_approved_at` to this proposal's
  approval timestamp. Both must be quoted ISO 8601 strings with a timezone,
  so YAML does not parse them into a `Date`. Leave `service`,
  `visibility: public`, and the `title` and `decided` EN/RU copy exactly as
  reproduced — they are the approved copy, carried in `requirements.md`. Add
  no `pr`, `release`, `merged_at`, `released_at`, `deployed_at` or
  `interventions`. — DoD: `npm test` passes `test/journal.test.ts`;
  `npm run build` renders the entry; the front matter names issue 65 and the
  new slug and carries exactly two timestamps.

- [ ] 10. Regenerate the lockfile if it needs it (depends on 2).
  `package-lock.json` comes over from `2a37d4b` already carrying
  `@resvg/resvg-wasm`. If any regeneration is needed, use
  `npm install --package-lock-only` only — never a plain `npm install`, which
  prunes every platform's optional native bindings but linux/x64 and makes
  `npm ci` in the Dockerfile refuse the tree (`AGENTS.md`). — DoD: `npm ci
  --no-audit --no-fund` succeeds from a clean `node_modules`; the lockfile
  still lists non-linux/x64 bindings for `@astrojs/compiler`, rollup and
  esbuild.

- [ ] 11. Verify the whole pipeline end to end (depends on 4, 5, 8, 9, 10).
  Run `npm ci`, `npm run build`, `node scripts/check-dist.mjs`,
  `node scripts/csp-hash.mjs`, then build the Docker image and run
  `nginx -t` (the Dockerfile already does) and
  `node scripts/check-headers.mjs` against the running container. — DoD: all
  green; `dist/og.png` is exactly 1200x630; `dist/` contains no `.js` file.

## Tests

- [ ] T1. `test/nginx.test.ts` (reproduced): total
  `security-headers.conf` include count in `nginx.conf` is exactly 7; each of
  `= /healthz`, `= /readyz`, `/_astro/`, `/assets/`, `/styles/`, `/` carries
  exactly one; `/_astro/`, `/assets/` and `/styles/` each keep their
  `add_header Cache-Control "public, immutable" always;` and
  `try_files $uri =404;`; `location /` carries neither `expires` nor
  `add_header Cache-Control`. Covers acceptance criterion 4.

- [ ] T2. `test/cache.test.ts` (reproduced): `location /assets/` and
  `location /styles/` each set `expires 1y;` and the `immutable`
  `add_header`, and each include the security headers exactly once; every
  `src/data/assets.json` `styles` href (exactly five) and `preload` href
  (exactly four) carries an 8-hex hash and resolves to an existing file under
  `public/`; `styles` is ordered mctl, global, prose, fonts, site. Covers
  criterion 3 at the manifest level.

- [ ] T3. `test/fonts.test.ts` (reproduced): `fonts.css` declares exactly the
  three families and exactly 28 `@font-face` rules; every reachable
  `font-weight` has a matching face, guarded by
  `assert.ok(reachableWeights.size > 0)` so an empty scan fails;
  `public/assets/fonts/` holds exactly 28 `.woff2` files with Onest 300 and
  JetBrains Mono 600/700 absent; `Base.astro` renders exactly four
  `rel="preload"` links each with `as="font"`, `type="font/woff2"`,
  `crossorigin` and an `href={assets.preload.` binding;
  `src/data/assets.json`'s `preload` has exactly the four expected keys;
  `site.css` declares `Onest Fallback` with all four metric overrides and
  orders `--font-display` as Onest, Onest Fallback, generic. Covers criteria
  6 and 8.

- [ ] T4. `test/vendor-assets.test.ts` (new, delta 3): the control run of the
  copied script under `VENDOR_FORCE_OFFLINE=1` exits 0; the run against a
  copy whose `fonts.css` is missing one `@font-face` block exits 1 with
  `vendor: no valid existing tree` on stderr. Covers criterion 7.

- [ ] T5. `test/cycle-diagram.test.ts` (reproduced): wide and narrow
  `viewBox` geometry, and the estimated-advance-width label-fits-in-box
  arithmetic for both variants in both languages, read from the component and
  stylesheet sources; plus the `ui.cycleLegend` legend rendered once per
  language inside `<figure class="cycle">`.

- [ ] T6. `scripts/check-dist.mjs` (reproduced, run from the Dockerfile after
  `npm run build`): `og:image` and `twitter:image` are present, identical, a
  valid absolute URL, and resolve under `dist/`; `dist/og.png`'s IHDR reads
  exactly 1200x630; no `/assets/` or `/styles/` reference on any built page
  lacks an 8-hex hash; plus the pre-existing `.l.en` / `.l.ru` parity and
  no-`.js` checks. Covers criteria 1, 3 and 10.

- [ ] T7. `scripts/check-headers.mjs` (reproduced, run against the live
  container in the `build` job): a hashed `/assets/` URL answers with a
  `Cache-Control` containing both `max-age=31536000` and `immutable`, and `/`
  answers with neither. Runtime proof that `test/cache.test.ts`'s source-text
  assertions actually hold.

- [ ] T8. `.github/workflows/build.yml`'s `Vendored tree matches the commit`
  step (new, delta 2a): the job fails when the committed tree differs from
  the regenerated one. Verify by local dry run before pushing — touch one
  byte of `src/styles/site.css`, run `npm run vendor`, and confirm
  `git diff --exit-code -- public/assets public/styles src/data/assets.json`
  exits non-zero (the change surfaces through `src/data/assets.json`'s
  `site.<hash>.css` entry, since `/public/styles/` is gitignored); then
  revert. Covers criterion 5.

- [ ] T9. Offline build (criterion 2): from a fresh clone with no network,
  `npm ci` from a warm cache then `npm run build` succeeds, using the
  committed `public/assets/`, `src/data/assets.json` and `scripts/fonts/`
  TTFs, and emits `dist/og.png`. `vendor` must log the
  `continuing offline` line, not a failure.

- [ ] T10. Reviewer steps, not acceptance criteria, per `AGENTS.md`:
  Lighthouse mobile on `/work/` reporting CLS below 0.1, and a HAR of `/`,
  `/work/` and `/colophon/` showing no third-party host. These need a browser
  and must not be turned into commit-checkable criteria.

## Rollback

The change is static-site content plus build tooling; nothing is stateful and
no data migrates.

- **Before merge.** Close the pull request. Nothing has shipped. Keep the
  branch, as `feat/agents-issue-50-...` was kept, so the tree stays
  recoverable.
- **After merge, before deploy.** `git revert -m 1 <merge-commit>` on `main`.
  The revert restores the unhashed asset filenames, the four-location
  `nginx.conf`, the `/og.svg` `og:image`, the 40-face `fonts.css`, and drops
  `scripts/render-og.mjs`, `src/data/assets.json` and the four new test
  files. Because `prebuild` re-runs `npm run vendor`, the reverted tree
  regenerates consistently on the next build; confirm with `npm test &&
  npm run build`.
- **After deploy.** `mctl_rollback_service(team_name, component_name=portfolio,
  target_tag=<previous image tag>)` — find the current tag with
  `mctl_get_service_config` first. The rollback is clean because the new
  `/assets/` and `/styles/` URLs only ever existed alongside their
  `immutable` cache headers; the previous image's unhashed URLs were served
  with the HTML cache policy, so no client holds a long-lived cache entry
  that a rollback would strand. HTML itself is never `immutable`, so a rolled
  back page is refetched normally.
- **Partial rollback of delta 2a alone.** If the drift gate turns out to be
  flaky (for example an upstream `@mctlhq/css` republish changing a hash
  mid-run), delete only the `Vendored tree matches the commit` step. Per
  `AGENTS.md` this is a loosening of the pre-merge gate, so it shows up in
  the diff and gets reviewed like code; it must not be done silently.
- **Journal.** Any manual intervention taken during rollback is recorded as
  an `interventions: [{what, why, at}]` entry in the *next* cycle's journal
  entry, per `AGENTS.md` — not retrofitted into this cycle's.
