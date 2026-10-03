# Q21: HTML pages revalidate on every visit

## Context
`nginx.conf`'s `location /` block, which serves every HTML page and, via `error_page 404 /404.html`, the 404 page, sends no `Cache-Control` header, only `Last-Modified`. Browsers therefore apply heuristic freshness (typically 10% of the time since the last modification) and reuse a cached page without asking the server. Since Q19 the site changes weekly (Snapshot numbers, `/work/` metrics, `/colophon/` cycle table). On 2026-10-03 the owner's browser showed a `/work/` and `/colophon/` more than a day stale while the server already served 0.1.37. Q6 (#50) deliberately left the HTML policy untouched, and its tests (`test/cache.test.ts`, `test/nginx.test.ts`, `scripts/check-headers.mjs`) pinned the absence of a `Cache-Control` header on `/` as a side effect.

This cycle sets the HTML policy explicitly: `Cache-Control: no-cache` on `location /`, so the browser may keep a copy but must revalidate before use (an unchanged page costs a 304 via `Last-Modified` / `If-Modified-Since`). Content-hashed assets under `/assets/`, `/styles/` and `/_astro/` keep their year-long immutable caching; `/assets/fonts/LICENSES/`, `/healthz` and `/readyz` are unchanged. Static tests and the runtime header check assert the new policy instead of its absence.

## User stories
- AS the site owner I WANT every HTML page to be revalidated on each visit SO THAT a weekly snapshot or release is visible on the next page load instead of up to days later.
- AS a visitor I WANT unchanged pages to cost only a 304 SO THAT revalidation stays cheap.
- AS a reviewer I WANT the static tests and the container header check to assert the policy SO THAT a regression to heuristic caching fails CI.

## Acceptance criteria (EARS)
- R1. THE SYSTEM SHALL have the `location /` block in `nginx.conf` read, character for character:
  ```
      location / {
          add_header Cache-Control "no-cache" always;
          include /etc/nginx/security-headers.conf;
          error_page 404 /404.html;
          try_files $uri $uri/index.html $uri.html =404;
      }
  ```
  and every other block of `nginx.conf` SHALL remain byte-identical (the existing per-block tests in `test/cache.test.ts` and `test/nginx.test.ts` still pass unmodified).
- R2. THE SYSTEM SHALL NOT add an `expires` directive to `location /` (it would emit a second, conflicting `Cache-Control`).
- R3. WHEN `npm test` runs THE SYSTEM SHALL, in `test/cache.test.ts`, replace the test `nginx.conf location / carries neither expires nor add_header Cache-Control` with a test asserting that the `location /` block: contains `add_header Cache-Control "no-cache" always;` exactly once; contains no `expires`, no `immutable` and no `max-age`; and still contains `include /etc/nginx/security-headers.conf;`, `error_page 404 /404.html;` and `try_files $uri $uri/index.html $uri.html =404;`.
- R4. WHEN `npm test` runs THE SYSTEM SHALL, in `test/nginx.test.ts`, replace the test `location / keeps error_page 404 and try_files, and carries neither expires nor add_header Cache-Control` with a test making the same assertions as R3.
- R5. IF the `add_header Cache-Control "no-cache" always;` line is removed from `nginx.conf` THEN each of the two replacement tests SHALL fail (each asserts the line's presence with an exact count of 1, so removal yields count 0).
- R6. WHEN `scripts/check-headers.mjs` runs against a live container THE SYSTEM SHALL require the `/` response's `Cache-Control` to equal exactly `no-cache`, replacing the current check that it carries neither `max-age=31536000` nor `immutable`.
- R7. WHEN `scripts/check-headers.mjs` probes `/this-path-does-not-exist-check-headers` (status 404, served from `/404.html`) THE SYSTEM SHALL require that response's `Cache-Control` to equal exactly `no-cache`.
- R8. WHILE the change is in place THE SYSTEM SHALL keep the hashed-asset runtime check (`max-age=31536000` and `immutable`) and the `/assets/fonts/LICENSES/` runtime check unchanged, and `test/check-headers.test.ts` SHALL still pass.
- R9. WHILE the change is in place THE SYSTEM SHALL still send all eight security headers on `/` and on the 404 response (verified by the existing `checkHeaders()` call in `scripts/check-headers.mjs`), and the `build` workflow's container step SHALL go green.
- R10. THE SYSTEM SHALL add one paragraph to `docs/hardening-notes.md` stating: HTML is `no-cache` because content changes weekly through the snapshot; hashed assets stay `immutable`; revalidation uses `Last-Modified`.
- R11. WHEN `npm run build` runs THE SYSTEM SHALL succeed.
- R12. THE SYSTEM SHALL contain a new journal entry `src/content/journal/2026-10-03-q21-html-pages-revalidate-on-every-visit.md` with `status: in_progress`, the frontmatter given in design.md, and title en `Q21: HTML pages revalidate on every visit`, ru `Q21: HTML-страницы перепроверяются при каждом заходе`.

## Out of scope
- Any change to `/assets/`, `/styles/`, `/_astro/`, `/assets/fonts/LICENSES/`, `/healthz` or `/readyz`.
- Cloudflare cache rules or page rules. The zone currently answers `cf-cache-status: DYNAMIC` for HTML and stays that way.
- `ETag` configuration, `max-age` or `stale-while-revalidate` variants, and service-worker or client-side cache busting.
- Any change to `src/` other than the one new journal entry required by `AGENTS.md` (the issue lists that entry under "Files expected to change").
- `security-headers.conf`, `Dockerfile`, `.github/workflows/build.yml`.

## Open questions
- The issue supplies only the journal title. The schema (`src/content.config.ts`) also requires a bilingual `decided` field; this proposal supplies that copy (design.md, section "Journal entry") so the implementer does not invent prose. The reviewer should check that copy before approval.
- `seoTitle` and `indexing: noindex` are copied from the pattern of the Q20 entry; they are not specified by the issue.
- "Out of scope: any change to `src/`" conflicts literally with the required journal entry under `src/content/journal/`; interpreted as "no site code or copy changes besides the journal entry".
