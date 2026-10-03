# Design: issue-141-q21-html-pages-revalidate-on-every-visit

## Current state
- `nginx.conf` has seven `location` blocks plus a server-level `include /etc/nginx/security-headers.conf;`. The hashed locations `/_astro/`, `/assets/` and `/styles/` each carry `expires 1y;` and `add_header Cache-Control "public, immutable" always;`. `/assets/fonts/LICENSES/` carries `add_header Cache-Control "public, max-age=3600" always;`. The catch-all is:
  ```
      location / {
          include /etc/nginx/security-headers.conf;
          error_page 404 /404.html;
          try_files $uri $uri/index.html $uri.html =404;
      }
  ```
  It sends no `Cache-Control`; nginx's static handler sends `Last-Modified`, so browsers fall back to heuristic freshness.
- `security-headers.conf` defines the eight security headers with `add_header ... always`. Because a location-level `add_header` discards inherited ones, every location re-includes it; `location /` already does, so adding a `Cache-Control` `add_header` there does not drop the set.
- `error_page 404 /404.html` is an internal redirect that re-matches `location /`, so the new header (with `always`) is sent on the 404 response as well.
- `test/cache.test.ts` line 57: `test('nginx.conf location / carries neither expires nor add_header Cache-Control', ...)` uses the file's `locationBlock('/')` helper and asserts `doesNotMatch(/expires/)` and `doesNotMatch(/add_header Cache-Control/)`.
- `test/nginx.test.ts` line 124: `test('location / keeps error_page 404 and try_files, and carries neither expires nor add_header Cache-Control', ...)` extracts the block with `/location \/ \{([\s\S]*?)\n {4}\}/` and asserts `error_page`, `try_files`, and the absence of `expires` and `add_header Cache-Control`. Other tests in the file (eight includes total, one include per block, `/_astro/`/`/assets/`/`/styles/` immutable) are unaffected; the "none of the eight security headers directly" test counts only the eight named headers, not `Cache-Control`.
- `scripts/check-headers.mjs` `run()`: `discoverAstroAsset()` GETs `/` and returns `homePage = { html, headers }`; the `targets` loop HEADs each path through `probeAndCheck()` (which calls `checkHeaders()` for the eight headers) and stores responses in `results` keyed by path, including `/this-path-does-not-exist-check-headers` (expect 404). Around line 244 the home check is:
  ```js
  const homeCacheControl = homePage.headers.get('cache-control') ?? '';
  if (homeCacheControl.includes('max-age=31536000') || homeCacheControl.includes('immutable')) { ... }
  ```
  The comment above it says `/` "keeps its existing, un-hashed cache policy -- carries neither directive".
- `test/check-headers.test.ts` imports only `discoverHashedAssetPath()` / `discoverStylesPath()`; it does not touch the home cache check.
- `.github/workflows/build.yml` runs `node scripts/check-headers.mjs http://127.0.0.1:8080` against `docker run` of the built image.
- `docs/hardening-notes.md` sections: Response headers, Header set defined once, `style-src` and the inline script, Open Graph image, Lighthouse mobile, Reviewer-step results from #10. No section on cache policy.
- Journal: all 32 entries are `status: complete`, so a new `in_progress` entry satisfies the at-most-one rule (`docs/journal.md`). Schema in `src/content.config.ts` (`journalSchema`), cross-field rules in `src/lib/journal.ts` `statusEvidenceProblems()`: an `in_progress` entry must not carry `release`, `released_at` or `deployed_at`. Latest entry is `2026-10-03-q20-proven-open-source-catches-up-with-the-platform.md` (issue #137, `issue_opened_at: '2026-10-03T16:45:28Z'`); issue #141 was created at `2026-10-03T20:42:30Z`, so stamp order increases with issue number.

## Proposed solution
1. `nginx.conf`: insert `        add_header Cache-Control "no-cache" always;` as the first line of `location /` (exact block in requirements R1). No `expires`. `always` makes it apply to the 404 response too. Nothing else in the file changes.
2. `test/cache.test.ts`: replace the test at line 57 with, e.g.:
   ```ts
   test('nginx.conf location / sets Cache-Control "no-cache" exactly once, with no expires, immutable or max-age, and keeps include, error_page and try_files', () => {
     const block = locationBlock('/');
     const noCache = block.match(/add_header Cache-Control "no-cache" always;/g) ?? [];
     assert.equal(noCache.length, 1);
     assert.doesNotMatch(block, /expires/);
     assert.doesNotMatch(block, /immutable/);
     assert.doesNotMatch(block, /max-age/);
     assert.match(block, /include \/etc\/nginx\/security-headers\.conf;/);
     assert.match(block, /error_page 404 \/404\.html;/);
     assert.match(block, /try_files \$uri \$uri\/index\.html \$uri\.html =404;/);
   });
   ```
   Also update the file's header comment (line 3, "location / carries neither directive") to describe the new policy.
3. `test/nginx.test.ts`: replace the test at line 124 with the same assertions against `blockMatch![1]`, with a matching title.
4. `scripts/check-headers.mjs`: replace the home check with an exact-equality check, `homeCacheControl !== 'no-cache'` -> problem `${baseUrl}/: Cache-Control is "<value or (missing)>", expected "no-cache"`. After the targets loop, read `results.get('/this-path-does-not-exist-check-headers')` (hoist the path into a constant, e.g. `NOT_FOUND_PROBE_PATH`, used in both the targets list and the lookup) and apply the same equality check to its `cache-control`. Update the comments that describe `/` as carrying "neither directive". The hashed-asset check and the LICENSES check stay as they are. Exact equality (not `includes`) is used so a stray `max-age` or a duplicated header (nginx would join two into `no-cache, ...`) fails.
5. `docs/hardening-notes.md`: add a section `## HTML cache policy` (after "Header set defined once") with one paragraph, e.g.: "HTML pages, served by `location /` (including `/404.html` through `error_page`), carry `Cache-Control: no-cache`: the browser may keep a copy but must revalidate it before every use, because the content changes weekly through the snapshot (Snapshot numbers, `/work/` metrics, the `/colophon/` cycle table) and heuristic freshness left pages more than a day stale. Revalidation uses `Last-Modified` / `If-Modified-Since`, so an unchanged page costs a 304. Content-hashed assets under `/assets/`, `/styles/` and `/_astro/` keep `public, immutable` with a one-year lifetime, since a content change always changes their URL. `expires` is deliberately absent from `location /`, as it would emit a second, conflicting `Cache-Control`."
6. Journal entry `src/content/journal/2026-10-03-q21-html-pages-revalidate-on-every-visit.md` (see below).

### Journal entry
Frontmatter, exactly (no `pr`, `merged_at`, `release`, `released_at`, `deployed_at`; the closure workflow adds those):
```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/141
proposal_slug: issue-141-q21-html-pages-revalidate-on-every-visit
status: in_progress
visibility: public
indexing: noindex
title:
  en: "Q21: HTML pages revalidate on every visit"
  ru: "Q21: HTML-страницы перепроверяются при каждом заходе"
seoTitle: "HTML pages revalidate on every visit — Dmitrii Mashkov"
decided:
  en: "HTML pages now carry Cache-Control: no-cache, so the browser checks with the server before showing a stored copy, and an unchanged page costs only a short not-modified answer. Until now the pages sent no cache policy at all, and the browser guessed how long a copy stayed fresh; after the weekly snapshot landed, the owner's browser still showed a work page and a colophon more than a day old. Hashed stylesheets and fonts keep their year-long immutable caching, because any change to them changes their address."
  ru: "HTML-страницы теперь отдаются с Cache-Control: no-cache: браузер сверяется с сервером, прежде чем показать сохранённую копию, а неизменившаяся страница стоит лишь короткого ответа «не изменилась». До сих пор страницы вообще не сообщали политику кэширования, и браузер сам угадывал, сколько копия остаётся свежей; после еженедельного снимка браузер владельца ещё больше суток показывал устаревшие страницы работ и колофона. Хэшированные стили и шрифты сохраняют годовое неизменяемое кэширование: любое их изменение меняет адрес."
interventions: []
issue_opened_at: '2026-10-03T20:42:30Z'
---
```
`issue_opened_at` is the issue's GitHub `created_at`, copied to the second. The body, if any, follows the shape of previous entries (Q20 has frontmatter only, which is valid).

## Alternatives
- `Cache-Control: max-age=0, must-revalidate` or a short `max-age` / `stale-while-revalidate`: explicitly out of scope; a short `max-age` reintroduces a staleness window, and `no-cache` already expresses "store but revalidate".
- `expires -1` / `expires epoch` in `location /`: emits its own `Cache-Control` plus `Expires`; combining with `add_header` would duplicate the header, and the issue forbids `expires`.
- Server-level `add_header Cache-Control` or a shared snippet: a server-level `add_header` is discarded by every location that has its own `add_header` (all of them), so it would be dead config and confusing; adding it to `security-headers.conf` would collide with the hashed locations' policy.
- Cloudflare cache rules / `ETag` tuning: out of scope; Cloudflare already returns `DYNAMIC` for HTML, and `Last-Modified` suffices for 304s.

## Platform impact
- No migration; the change ships with the next release image through the normal release-please and `release-deploy` flow.
- Traffic: each page view becomes a conditional request; unchanged pages answer 304 with no body. Negligible for a static site.
- Backward compatibility: browsers holding a heuristically fresh copy keep it until that heuristic expires once; after that every load revalidates.
- Risk: an `add_header` placement that drops the security-header set. Mitigated: `location /` keeps its own `include`, `test/nginx.test.ts` asserts one include per block, and `scripts/check-headers.mjs` checks all eight headers on `/` and on the 404 in CI.
- Risk: nginx joining duplicate `Cache-Control` values. Mitigated by the exact-count static test and the exact-equality runtime check.
