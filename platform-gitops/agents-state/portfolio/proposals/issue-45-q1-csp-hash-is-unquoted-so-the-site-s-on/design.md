# Design: issue-45-q1-csp-hash-is-unquoted-so-the-site-s-on

## Current state

**The token is generated unquoted.** `scripts/csp-hash.mjs` walks every
`dist/**/*.html`, extracts each inline `<script>` body with
`/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g`, enforces "exactly one
distinct body, at most 400 bytes", and ends with:

```js
const hash = createHash('sha256').update(body, 'utf8').digest('base64');
process.stdout.write(`sha256-${hash}\n`);
```

There are no quotes anywhere in that write, and none anywhere else in the file.

**The template substitutes it verbatim.** `security-headers.conf` carries the one
CSP definition for the whole site:

```
add_header Content-Security-Policy "default-src 'self'; script-src 'self' __SCRIPT_SRC_HASHES__; style-src 'self'; ..." always;
```

and the `Dockerfile` runtime stage does:

```dockerfile
RUN HASHES="$(cat /tmp/csp-script-src.txt)" \
 && sed "s|__SCRIPT_SRC_HASHES__|${HASHES}|g" /tmp/security-headers.conf > /etc/nginx/security-headers.conf \
 && grep -q "sha256-" /etc/nginx/security-headers.conf \
 && ! grep -q "__SCRIPT_SRC_HASHES__" /etc/nginx/security-headers.conf \
 && rm ...
```

`grep -q "sha256-"` is true of the broken output. The `sed` delimiter is `|` and
the expression is double-quoted, so a token containing single quotes substitutes
cleanly — quoting the generator's output needs no change to this `sed` at all.

**The runtime checker tests a substring.** `scripts/check-headers.mjs`, run from
`.github/workflows/build.yml` against a container started from the built image,
HEADs `/`, `/healthz`, an `/_astro/` path and a deliberate 404, asserts the seven
fixed-value headers from `EXPECTED_HEADERS`, and for the CSP does only:

```js
if (!csp.includes('sha256-')) { problems.push(...); }
if (/https?:\/\//.test(csp)) { problems.push(...); }
```

Both assertions hold for `script-src 'self' sha256-5h2K…=`. The script already
performs one `GET /` in `discoverAstroAsset()` and reads the body as text, so the
bytes needed for an end-to-end hash comparison are already being fetched.

**The source-level test checks only the template.** `test/nginx.test.ts` asserts
the eight headers are defined exactly once in `security-headers.conf`, that
`nginx.conf` includes the file five times, and that the CSP line matches
`/__SCRIPT_SRC_HASHES__/` with no `'unsafe-inline'` and no `https?://`. It cannot
see the substituted value, and it must keep passing unchanged — which it does,
because this proposal leaves the template alone.

**The script being blocked.** `src/layouts/Base.astro` ships one `is:inline`
script in `<head>`: it applies `localStorage.lang` / `localStorage.theme` to
`document.documentElement.dataset`, then registers a delegated `click` listener
for `[data-set-lang],[data-set-theme]`, which is what `src/components/LangToggle.astro`
and `src/components/ThemeToggle.astro` render. No other client code exists —
`scripts/check-dist.mjs` fails the build on any `.js` file under `dist/` — so a
rejected hash means no client behaviour at all.

**Test and content conventions this change has to satisfy.**

- `package.json` `test` names each test file explicitly
  (`node --test test/journal.test.ts test/adr.test.ts …`); a new file must be added
  to that list or it never runs.
- `test/metrics-build.test.ts` imports helpers from `scripts/snapshot-metrics.mjs`
  and `scripts/check-no-metrics.mjs`; both scripts guard their entrypoint with
  `if (process.argv[1] === fileURLToPath(import.meta.url)) { await main(); }`.
- `scripts/snapshot-metrics.mjs` imports `metricProblems` from
  `../src/lib/metrics.ts`, and `test/adr.test.ts` imports `../src/lib/adr.ts`
  directly: plain `node --test` runs TypeScript in `src/lib/` with no build step,
  and a `.mjs` script can import it. `src/lib/adr.ts` documents the pattern —
  "Zero-import helper module … so `test/adr.test.ts` can exercise the real logic".
- ADRs are single bilingual files. `src/content.config.ts` globs
  `[0-9][0-9][0-9][0-9]-*.md` under `src/content/adr/` and post-processes the store
  with `checkAdrBodies` from `src/lib/adr.ts`, which requires the five sections in
  order, each heading carrying `<span class="l en">` and `<span class="l ru">`, each
  section body carrying a `class="l en"` and a `class="l ru"` block, and the
  frontmatter `id` matching the four-digit filename prefix.
  `src/pages/colophon/index.astro` renders the index from `getCollection('adr')`
  sorted by `byAdrId`; `src/pages/colophon/adr/[...slug].astro` generates one page
  per public entry; `scripts/check-dist.mjs` independently derives the expected page
  list from the filenames in `src/content/adr/` and asserts `.l.en` / `.l.ru` count
  parity per HTML file.

## Proposed solution

Five changes plus the ADR, structured so that the inline-script regex and the hash
computation exist in exactly one place and both the generator and the checker use
that one place.

### 1. New `src/lib/csp.ts` — the single source of truth

A small module in the established `src/lib/` idiom (importable by plain
`node --test`, no build step, only `node:crypto` as a dependency), exporting:

- `INLINE_SCRIPT_RE` / `extractInlineScripts(html): string[]` — the regex moved
  verbatim out of `scripts/csp-hash.mjs`, so "the same regex `csp-hash.mjs` uses"
  is enforced by identity rather than by copy.
- `sha256Base64(body): string` — `createHash('sha256').update(body, 'utf8').digest('base64')`.
- `hashToken(hash, algo = 'sha256'): string` — returns `'sha256-<base64>'`,
  **with** the surrounding single quotes. One function owns the quoting.
- `scriptSrcTokens(csp): string[] | null` — splits the header on `;`, trims each
  directive, finds the one whose first whitespace-delimited word is `script-src`,
  and returns its remaining tokens; `null` when there is no `script-src`.
- `HASH_TOKEN_RE = /sha(256|384|512)-/` — "names a hash algorithm anywhere in the
  token", as the issue specifies.
- `QUOTED_HASH_RE = /^'sha(256|384|512)-[A-Za-z0-9+/]+={0,2}'$/`.
- `scriptSrcHashProblems(csp, label): string[]` — for every token matching
  `HASH_TOKEN_RE`, requires a full match of `QUOTED_HASH_RE`, and returns one
  message per offence containing the offending token verbatim, e.g.
  `` `${label}: CSP script-src hash source is not a valid quoted source expression: sha256-5h2K…= (expected '<algo>-<base64>')` ``.
  Also returns a problem when `script-src` is absent, and when it contains no hash
  token at all (the old `includes('sha256-')` intent, kept as a parse rather than a
  substring).
- `staleHashProblems(csp, html, label): string[]` — extracts the inline scripts
  from `html`, hashes each, and requires `scriptSrcTokens(csp)` to contain
  `hashToken(hash)` exactly. The message names both: `expected '<sha256-X>' …
  found: '<sha256-Y>'`.

Both functions are pure string-in / string-array-out, which is what makes the
mutation test possible without a container.

### 2. `scripts/csp-hash.mjs` emits the quoted token

Replace the local `extractInlineScripts` and the final write with imports from
`../src/lib/csp.ts`:

```js
process.stdout.write(`${hashToken(sha256Base64(body))}\n`);
```

Every existing failure mode (no HTML, zero bodies, more than one distinct body,
over 400 bytes) and its message stay exactly as they are. The quoting lives here,
not in `security-headers.conf`: `__SCRIPT_SRC_HASHES__` is documented in that file
as "the build's inline-script SHA-256 hash(es)" — a space-separated list — and a
list needs each element quoted, which a pair of quotes around the placeholder
cannot do. `test/nginx.test.ts` keeps asserting the placeholder appears bare.

### 3. `scripts/check-headers.mjs` parses instead of matching

- `checkHeaders(url, headers, problems)` drops `csp.includes('sha256-')` and calls
  `scriptSrcHashProblems(csp, url)`, pushing whatever it returns. The `http(s)`
  origin test, the seven fixed-value header comparisons, the missing-CSP case and
  the per-path status checks are untouched.
- `discoverAstroAsset()` already does `GET /` and `await res.text()`. It is
  restructured to return the home page HTML and its response headers alongside the
  asset descriptor (one fetch, no extra request), and `main()` then runs
  `staleHashProblems(homeCsp, homeHtml, `${baseUrl}/`)` once. A correctly quoted
  but stale hash therefore fails, which is the check the issue asks for and the one
  no existing gate performs.
- The banner comment at the top of the file is updated to say what it now proves.

### 4. `Dockerfile` — the grep guard requires the quoted form

```dockerfile
 && grep -qE "script-src 'self' 'sha(256|384|512)-[A-Za-z0-9+/]+={0,2}'" /etc/nginx/security-headers.conf \
 && ! grep -qE "(^|[^'])sha(256|384|512)-" /etc/nginx/security-headers.conf \
 && ! grep -q "__SCRIPT_SRC_HASHES__" /etc/nginx/security-headers.conf \
```

The first line asserts the positive form; the second fails on any hash-shaped token
not immediately preceded by a single quote, so an extra unquoted token beside a
good one cannot slip through; the third is the existing placeholder check, kept.
`grep -E` is BusyBox grep in `nginx:1.30-alpine`, which supports `-qE` and this
syntax. Nothing else in the `RUN` chain changes.

### 5. `test/csp.test.ts` — mutation in both directions

A `node --test` file importing `src/lib/csp.ts`, added to the `test` script list in
`package.json`. It builds one realistic CSP string from the site's real header
shape and asserts:

- the correctly quoted form yields `[]` from `scriptSrcHashProblems`;
- the same string with the two single quotes stripped yields a non-empty array,
  **and** the message contains the offending token `sha256-…`;
- a mixed list (`'sha256-A' sha256-B`) reports exactly the unquoted token;
- `sha384-` and `sha512-` tokens are held to the same rule;
- `staleHashProblems` returns `[]` when the CSP carries `hashToken(sha256Base64(body))`
  for the inline script in a fixture HTML string, and a non-empty array whose
  message names both the expected and the found token when the CSP carries a
  correctly quoted hash of *different* bytes;
- `hashToken()` output starts and ends with `'`, so a future refactor of the
  generator that drops the quotes fails here too.

Assertions use `assert.match(problems.join('\n'), /…/)` on the messages, never bare
`assert.ok(problems.length > 0)`, so a check that silently stops running is caught.

### 6. `docs/hardening-notes.md`

One short paragraph appended to the "`style-src` and the inline script" section
(the file is the security contract, not a changelog), recording the exact served
string and why the gates were insufficient:

> **The hash source must be quoted (issue #45).** The header as served is
> `content-security-policy: default-src 'self'; script-src 'self' 'sha256-<base64>'; style-src 'self'; font-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.
> For one release the hash was emitted without its surrounding single quotes, so
> the browser discarded it as an invalid source and refused to run the inline
> language/theme script, while `grep -q "sha256-"` in the Dockerfile and
> `csp.includes('sha256-')` in `scripts/check-headers.mjs` both stayed green:
> they asserted the presence of a substring, not the validity of a source
> expression. Both now parse the `script-src` directive and require every
> hash-shaped token to be exactly `'<algo>-<base64>'`, and the runtime check also
> compares the token against the SHA-256 of the inline script actually served, so
> a quoted but stale hash fails as well.

### 7. ADR-0006, one bilingual file

`src/content/adr/0006-browser-verified-security-headers.md`, written exactly as
below (see Open question 1 in `requirements.md` for why this is one file, not the
`.en.md` / `.ru.md` pair the issue names; two single-language files fail
`checkAdrBodies`, collide on `id: 6` in the index, and break
`scripts/check-dist.mjs`'s derived page list). Prose is the issue's copy verbatim;
only the title had to be supplied.

````markdown
---
id: 6
title:
  en: "Browser-verified security headers"
  ru: "Заголовки безопасности, проверенные браузером"
status: accepted
date: '2026-09-11'
visibility: public
---

## <span class="l en">Context</span><span class="l ru">Контекст</span>

<div class="l en">

The site's security headers were verified only by `curl` and by substring assertions in CI. Both passed while the browser rejected the CSP and refused to run the site's only script, leaving the language and theme toggles dead in production. This is the second time a browser-only behaviour escaped every mechanical gate: Cloudflare's edge previously rewrote the HTML for browser requests only, invisible to `curl` and to the build.

</div>

<div class="l ru" lang="ru">

Заголовки безопасности сайта проверялись только `curl`'ом и подстрочными проверками в CI. Обе проверки были зелёными, пока браузер отвергал CSP и отказывался выполнять единственный скрипт сайта, из-за чего переключатели языка и темы не работали в проде. Это второй случай, когда поведение, видимое только браузеру, прошло мимо всех механических гейтов: до этого край Cloudflare переписывал HTML только для браузерных запросов, невидимо для `curl` и для сборки.

</div>

## <span class="l en">Decision</span><span class="l ru">Решение</span>

<div class="l en">

A header is considered verified only when a real browser engine has loaded the page and reported no CSP violation. The production contract gains a browser step; CI keeps the mechanical parse as the fast pre-filter, and every such guard must be proven by mutation in both directions.

</div>

<div class="l ru" lang="ru">

Заголовок считается проверенным только тогда, когда настоящий браузерный движок загрузил страницу и не сообщил о нарушении CSP. Production contract получает браузерный шаг; в CI остаётся быстрый механический разбор как предфильтр, и каждый такой гейт доказывается мутацией в обе стороны.

</div>

## <span class="l en">Consequences</span><span class="l ru">Последствия</span>

<div class="l en">

The contract can no longer be run entirely from a shell. A browser step is slower and needs a machine with a browser engine, so it runs at release and cutover points rather than on every commit. In exchange, a class of silent failures that has now cost two incidents becomes detectable.

</div>

<div class="l ru" lang="ru">

Контракт больше нельзя прогнать целиком из шелла. Браузерный шаг медленнее и требует машины с браузерным движком, поэтому он выполняется на релизах и переключениях, а не на каждом коммите. Взамен класс тихих отказов, стоивший уже двух инцидентов, становится обнаружимым.

</div>

## <span class="l en">Drivers</span><span class="l ru">Движущие факторы</span>

<div class="l en">

Two incidents of the same shape; a strict CSP whose failure mode is silent for the user and invisible to `curl`.

</div>

<div class="l ru" lang="ru">

Два инцидента одной формы; строгий CSP, отказ которого незаметен пользователю и невидим для `curl`.

</div>

## <span class="l en">Revisit criteria</span><span class="l ru">Критерии пересмотра</span>

<div class="l en">

Revisit if a headless browser check becomes cheap enough to run on every pull request, or if the site stops shipping inline script entirely, which would remove the hash from the CSP.

</div>

<div class="l ru" lang="ru">

Пересмотреть, если браузерная проверка станет достаточно дешёвой для каждого pull request, или если сайт вовсе перестанет отдавать inline-скрипт — тогда хэш исчезнет из CSP.

</div>
````

## Alternatives

**A. Quote the placeholder in `security-headers.conf`
(`script-src 'self' '__SCRIPT_SRC_HASHES__'`).** One character pair, no script
change. Dropped: the placeholder is documented and implemented as a
space-separated *list* of hash sources, so the moment a second inline script
exists the substitution produces `'sha256-A sha256-B'` — one invalid source
instead of two valid ones, i.e. the same bug with a longer fuse. The issue rules
it out explicitly, and it would also force a change to `test/nginx.test.ts`, whose
current assertions are correct.

**B. Keep the substring checks and merely tighten the regex to
`/'sha256-[A-Za-z0-9+/=]+'/.test(csp)`.** Cheapest possible diff. Dropped: a
substring test still passes when a valid quoted token sits next to an invalid
unquoted one, still passes on a stale hash, and still gives no per-token message.
The issue's point is that a presence test is not a validity test; replacing one
presence test with another repeats the mistake.

**C. Put the parse logic inside `scripts/check-headers.mjs` and export it with an
entrypoint guard,** as `scripts/check-no-metrics.mjs` does. Viable and precedented.
Dropped because `scripts/csp-hash.mjs` and `scripts/check-headers.mjs` must share
the inline-script regex and the hashing for the end-to-end check to mean anything;
making the generator import from the checker (or vice versa) inverts the
dependency, whereas `src/lib/metrics.ts` ← `scripts/snapshot-metrics.mjs` is the
existing shape for exactly this.

**D. Add a headless browser (Playwright) to `.github/workflows/build.yml` and
assert zero CSP violations.** This is what actually catches the class of bug.
Dropped: explicitly out of scope in the issue, it would add a heavyweight
dependency to a repository whose whole posture is zero runtime dependencies, and
ADR-0006 deliberately places the browser step in the operator's production
contract at release and cutover points instead.

## Platform impact

- **Migrations:** none. No data, no schema, no stored state. `src/data/metrics.json`
  is untouched.
- **Backward compatibility:** the CSP becomes *more* permissive in the only sense
  that matters — the inline script that was always intended to run now runs. No
  header is removed or loosened; `'unsafe-inline'` is still absent everywhere.
- **Delivery:** the header is baked into the image at build time, so the fix reaches
  production only through a new image: merge, release-please tag, then
  `mctl_deploy_service` by the operator (ADR-0001 forbids any other path). Nothing
  in the running cluster changes until that deploy.
- **Resource impact:** none. One extra `GET /` is avoided by reusing the existing
  home-page fetch in `check-headers.mjs`; the new test is pure string work.
- **Risk: the tightened `grep -E` misbehaves under BusyBox grep** and fails an
  otherwise good build. Mitigation: the expression uses only POSIX ERE constructs
  BusyBox supports; the CI `build` job builds the image on every PR, so a bad
  expression fails the PR, not production.
- **Risk: base64 padding.** A SHA-256 digest in base64 always ends in `=`; the
  regexes allow `={0,2}` and the character class includes `+` and `/`, so no valid
  digest is rejected. The mutation test pins this with a real digest.
- **Risk: the end-to-end check makes `check-headers.mjs` depend on the home page
  shipping exactly one inline script.** That is already an invariant enforced at
  build time by `scripts/csp-hash.mjs` ("expected exactly one distinct inline script
  body"), so the two agree by construction; `staleHashProblems` iterates over all
  extracted bodies rather than assuming one, so a future second script degrades to a
  clear message instead of a wrong one.
- **Risk: ADR numbering collision** if another cycle claims `0006` concurrently.
  `AGENTS.md` mandates one DevLoop cycle at a time in this repository, and
  `checkAdrBodies` fails loudly on an `id`/filename mismatch.
- **Rollback:** a single revert of the merge commit plus `mctl_rollback_service` to
  the previous image tag restores the prior (broken-but-shipping) state; see
  `tasks.md`.
