# Tasks: issue-141-q21-html-pages-revalidate-on-every-visit

- [ ] 1. In `nginx.conf`, add `        add_header Cache-Control "no-cache" always;` as the first line of `location /` — DoD: the block matches requirements R1 character for character; `git diff nginx.conf` shows exactly one added line; no `expires` added.
- [ ] 2. (depends on 1) In `test/cache.test.ts`, replace `nginx.conf location / carries neither expires nor add_header Cache-Control` with the replacement test in design.md step 2, and update the header comment on line 3 — DoD: test asserts the `no-cache` line count is exactly 1, no `expires`/`immutable`/`max-age`, and presence of the include, `error_page` and `try_files` lines; all other tests in the file unmodified.
- [ ] 3. (depends on 1) In `test/nginx.test.ts`, replace `location / keeps error_page 404 and try_files, and carries neither expires nor add_header Cache-Control` with a test making the same assertions — DoD: as task 2; all other tests in the file unmodified.
- [ ] 4. (depends on 1) In `scripts/check-headers.mjs`, replace the home-page check with `Cache-Control === 'no-cache'`, hoist the missing path into a constant, and add the same equality check for that 404 response read from `results`; update the stale comments — DoD: hashed-asset and LICENSES checks byte-unchanged; problem messages name the URL, the actual value (or `(missing)`) and `"no-cache"`.
- [ ] 5. Add the `## HTML cache policy` paragraph to `docs/hardening-notes.md` (design.md step 5) — DoD: states no-cache because content changes weekly through the snapshot, hashed assets stay immutable, revalidation uses `Last-Modified`.
- [ ] 6. Create `src/content/journal/2026-10-03-q21-html-pages-revalidate-on-every-visit.md` with the frontmatter in design.md, "Journal entry", verbatim — DoD: title en/ru exact; `status: in_progress`; no `release`/`released_at`/`deployed_at`.
- [ ] 7. (depends on 1-6) Run `npm test` and `npm run build` — DoD: both pass.

## Tests
- [ ] T1. `npm test` passes, including the two replacement tests and the unchanged per-block tests in `test/cache.test.ts` and `test/nginx.test.ts`, `test/check-headers.test.ts`, and the journal tests.
- [ ] T2. Temporarily delete the `add_header Cache-Control "no-cache" always;` line from `nginx.conf` and run `node --test test/cache.test.ts test/nginx.test.ts`: both replacement tests fail; restore the line. (Local verification only, not committed.)
- [ ] T3. `npm run build` passes (journal schema accepts the new entry).
- [ ] T4. The `build` workflow's container step (`node scripts/check-headers.mjs http://127.0.0.1:8080`) passes: `/` and the 404 probe return `Cache-Control: no-cache` and all eight security headers; hashed asset still `max-age=31536000` + `immutable`; LICENSES probe unchanged.
- [ ] T5. Reviewer step (post-deploy, not an acceptance criterion): `curl -sI https://<site>/work/` shows `cache-control: no-cache`; a repeat with `If-Modified-Since` set to the returned `Last-Modified` answers 304.

## Rollback
Revert the merge commit (removes the `add_header` line and restores the previous tests and check), cut a release through release-please, and deploy via `mctl_deploy_service` or roll back to the previous image tag with `mctl_rollback_service`. No data or state migration is involved; browsers simply fall back to heuristic caching.
