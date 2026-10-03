# Tasks: issue-45-q1-csp-hash-is-unquoted-so-the-site-s-on

- [ ] 1. Add `src/lib/csp.ts`, a helper module in the `src/lib/adr.ts` idiom
      (importable by plain `node --test`, no build step, `node:crypto` its only
      import), exporting `INLINE_SCRIPT_RE`, `extractInlineScripts(html)`,
      `sha256Base64(body)`, `hashToken(hash, algo = 'sha256')`,
      `scriptSrcTokens(csp)`, `HASH_TOKEN_RE` (`/sha(256|384|512)-/`),
      `QUOTED_HASH_RE` (`/^'sha(256|384|512)-[A-Za-z0-9+/]+={0,2}'$/`),
      `scriptSrcHashProblems(csp, label)` and `staleHashProblems(csp, html, label)`.
      The regex in `extractInlineScripts` is moved verbatim from
      `scripts/csp-hash.mjs` — do not retype it.
      — DoD: `node --test` can import the module directly; every exported function
      is pure (string in, string/array out) and takes no filesystem or network
      dependency; `hashToken` is the only place a quote character is written.

- [ ] 2. Make `scripts/csp-hash.mjs` emit the quoted token (depends on 1): import
      `extractInlineScripts`, `sha256Base64` and `hashToken` from `../src/lib/csp.ts`,
      delete the now-duplicated local regex and helper, and write
      `` `${hashToken(sha256Base64(body))}\n` `` to stdout. Leave the 400-byte cap,
      the one-distinct-body rule, the empty-`dist/` guard and all existing messages
      untouched.
      — DoD: after `npm run build`, `node scripts/csp-hash.mjs` prints exactly one
      line of the form `'sha256-<base64>'`, leading and trailing single quote
      included; each existing failure path still exits non-zero with its current
      message.

- [ ] 3. Replace the CSP substring check in `scripts/check-headers.mjs` (depends on
      1): in `checkHeaders`, drop `csp.includes('sha256-')` and push everything
      `scriptSrcHashProblems(csp, url)` returns. Keep the missing-CSP branch, the
      `/https?:\/\//` origin branch, the seven `EXPECTED_HEADERS` comparisons and the
      per-path status assertions exactly as they are.
      — DoD: running the script against a container whose CSP carries an unquoted
      hash prints a message containing the offending token and exits non-zero;
      against the fixed image it prints the existing `check-headers: OK` line.

- [ ] 4. Add the end-to-end staleness check to `scripts/check-headers.mjs` (depends
      on 1, 3): restructure `discoverAstroAsset()` so the single existing `GET /`
      returns the home page HTML and its response headers alongside the asset
      descriptor, then call `staleHashProblems(homeCsp, homeHtml, ...)` once from
      `main()`. Do not add a second request. Update the file's banner comment to
      describe what it now proves.
      — DoD: a CSP whose quoted hash does not match the SHA-256 of the inline script
      in the served `/` fails with a message naming both the expected and the found
      token; the `/_astro/` discovery and its 404 fallback behave as before.

- [ ] 5. Tighten the `Dockerfile` guard (depends on 2): replace
      `grep -q "sha256-"` with
      `grep -qE "script-src 'self' 'sha(256|384|512)-[A-Za-z0-9+/]+={0,2}'"` and add
      `! grep -qE "(^|[^'])sha(256|384|512)-"`, both against
      `/etc/nginx/security-headers.conf`. Keep
      `! grep -q "__SCRIPT_SRC_HASHES__"`, the `sed` line, the `rm` and the rest of
      the `RUN` chain unchanged.
      — DoD: `docker build .` succeeds on the fixed generator; reverting task 2
      locally makes the same build fail at that `RUN` step.

- [ ] 6. Leave `security-headers.conf`, `nginx.conf` and `src/layouts/Base.astro`
      untouched — DoD: `git diff` shows no change to those three files, and
      `test/nginx.test.ts` passes unmodified (it still asserts the bare
      `__SCRIPT_SRC_HASHES__` placeholder, no `'unsafe-inline'`, no external origin).

- [ ] 7. Record the contract in `docs/hardening-notes.md` (depends on 2, 3, 4): append
      one short paragraph to the "`style-src` and the inline script" section carrying
      the exact CSP string as served, with the quoting, and stating that the previous
      checks asserted the presence of a substring rather than the validity of a
      source expression. Use the paragraph written out in `design.md` section 6.
      — DoD: the file contains the full quoted header string and the paragraph; no
      other section of the file is rewritten (it is the security contract, not a
      changelog).

- [ ] 8. Add `src/content/adr/0006-browser-verified-security-headers.md` — one
      bilingual file, content byte-for-byte as written in `design.md` section 7
      (`id: 6`, `status: accepted`, `visibility: public`, `date` = the day the change
      lands, five Nygard sections in order, each with an `.l.en` and an `.l.ru`
      block). Do not create `.en.md` / `.ru.md` files: the loader in
      `src/content.config.ts` and `checkAdrBodies` in `src/lib/adr.ts` reject them,
      and `scripts/check-dist.mjs` would expect pages that cannot exist.
      — DoD: `npm run check` and `npm run build` pass; `dist/colophon/index.html`
      lists an ADR-0006 row; `dist/colophon/adr/0006-browser-verified-security-headers/index.html`
      exists; `scripts/check-dist.mjs` reports equal `class="l en"` / `class="l ru"`
      counts on every page and no `.js` under `dist/`.

- [ ] 9. (Optional, operator-dependent) Add the cycle's journal entry under
      `src/content/journal/` per `AGENTS.md`. The issue does not list it, and the
      schema requires `issue_opened_at` plus the other cycle timestamps, which the
      proposal cannot supply. Skip unless the approving operator provides them.
      — DoD: either no journal file is added, or one is added whose frontmatter
      validates and whose `visibility: public` page appears in `dist/`.

## Tests

- [ ] T1. `test/csp.test.ts` — quoting, proven by mutation in both directions
      (depends on 1): from one realistic CSP string built with a real digest,
      assert `scriptSrcHashProblems` returns `[]` for the quoted form; returns a
      non-empty array for the same string with the two single quotes stripped, and
      `assert.match` the joined messages against the offending token
      `sha256-<base64>`; and, for the mixed list `'sha256-A' sha256-B`, reports
      `sha256-B` and not `'sha256-A'`.
      — DoD: flipping the implementation back to a substring test makes at least two
      assertions in this file fail.

- [ ] T2. `test/csp.test.ts` — all three algorithms and malformed shapes: `sha384-`
      and `sha512-` tokens unquoted are reported; a token quoted on one side only
      (`'sha256-X` / `sha256-X'`) is reported; `'self'`, `'none'` and a plain host
      token are not reported; a `script-src` with no hash token at all is reported;
      a header with no `script-src` directive is reported.
      — DoD: each case asserts on the message text, not only on array length.

- [ ] T3. `test/csp.test.ts` — end-to-end staleness (depends on 1): with a fixture
      HTML string containing one inline `<script>`, assert `staleHashProblems`
      returns `[]` when the CSP contains `hashToken(sha256Base64(body))`, and returns
      a message naming both the expected and the found token when the CSP carries a
      correctly quoted hash of different bytes.
      — DoD: the stale case asserts the expected token and the found token both
      appear in the message.

- [ ] T4. `test/csp.test.ts` — generator contract: `hashToken('abc')` starts and ends
      with `'`, and `extractInlineScripts` ignores `<script src=…>` while capturing an
      inline body, matching the behaviour `scripts/csp-hash.mjs` relied on before the
      move.
      — DoD: a change that drops the quotes from `hashToken` fails this test.

- [ ] T5. Wire the new file into the suite: add `test/csp.test.ts` to the explicit
      file list in the `test` script of `package.json` (it names every file; a new
      file is otherwise never run).
      — DoD: `npm test` output includes the new file's cases; `npm run build` still
      runs it through `prebuild`.

- [ ] T6. Regression sweep: `npm test` green with `test/nginx.test.ts`,
      `test/adr.test.ts`, `test/colophon.test.ts` and the rest unmodified, and
      `npm run build` green including `scripts/check-dist.mjs`.
      — DoD: no existing test file is edited except where task 8's new ADR changes a
      derived count, and no such edit is expected.

- [ ] T7. Image-level proof in CI: the `build` job of `.github/workflows/build.yml`
      builds the image, runs the container and executes
      `node scripts/check-headers.mjs http://127.0.0.1:8080`, which now parses the
      directive and compares against the served inline script.
      — DoD: the PR's `build` job passes; its log shows the `check-headers: OK` line
      for a header whose `script-src` carries the quoted hash. This is the committed,
      reproducible form of the issue's `curl -sI` evidence (see Open question 3 in
      `requirements.md`).

## Rollback

1. **Before merge:** nothing to undo — every change is confined to the branch, and
   the `test` and `build` jobs in `.github/workflows/build.yml` gate it.
2. **After merge, before deploy:** revert the merge commit on `main` via a pull
   request. Nothing in production has changed at that point: the CSP is baked into
   the image at build time, so `main` alone affects nothing that is running.
3. **After deploy, if the quoted hash turns out to break something:**
   `mctl_rollback_service` back to the previous image tag (`mctl_get_service_config`
   first to read the current tag). That restores the earlier image, i.e. the
   unquoted header and the dead toggles — a known state, not an unknown one. Only
   the operator can do this; ADR-0001 forbids `kubectl` and hand-edited gitops
   values.
4. **Partial rollback is safe and cheap.** The changes are independent: reverting
   the `Dockerfile` guard (task 5) leaves the fix in place with a weaker gate;
   reverting `test/csp.test.ts` (T1-T4) leaves the fix and the runtime check intact;
   the ADR and `docs/hardening-notes.md` are text and carry no runtime effect.
   Reverting task 2 alone reinstates the bug and must not be done without also
   reverting task 5, which would then fail the image build — the intended coupling.
