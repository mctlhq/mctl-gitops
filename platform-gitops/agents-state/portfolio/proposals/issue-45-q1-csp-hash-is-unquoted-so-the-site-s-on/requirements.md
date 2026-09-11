# Quote the CSP script hash and replace the guards that stayed green

## Context

`scripts/csp-hash.mjs` prints the inline script's digest as the bare token
`sha256-<base64>`. The Dockerfile substitutes that token verbatim into
`__SCRIPT_SRC_HASHES__` in `security-headers.conf`, so production serves
`script-src 'self' sha256-5h2KCETahwWiKerzZRW7TuE5HcPkPu28Enkl9PaJMpg=`. A CSP
hash source is only valid when wrapped in single quotes, so Chrome discards the
token as an invalid source, falls back to `script-src 'self'`, and refuses to
execute the single inline `<script>` in `src/layouts/Base.astro`. That script is
the whole of the site's client behaviour: it applies a stored `lang`/`theme`
preference from `localStorage` and registers the click listener behind every
`[data-set-lang]` / `[data-set-theme]` control. With it blocked, the EN/RU and
Dark/Light toggles are inert on every public page and a stored preference is
never applied.

The bug matters less than the reason it shipped. Four separate gates were green
while the header was broken: `scripts/csp-hash.mjs` emits the token, the
Dockerfile asserts only `grep -q "sha256-"`, `scripts/check-headers.mjs` asserts
only `csp.includes('sha256-')`, and `test/nginx.test.ts` checks only that the
placeholder is present in the template. Every one of those assertions is true of
the broken header, so each is a guard that cannot fail. This proposal quotes the
token in the generator and replaces the substring assertions with a real parse of
the `script-src` directive plus an end-to-end comparison against the bytes
actually served — and proves the new check by mutation in both directions, so a
guard that stops guarding is itself caught. ADR-0006 records the rule the two
incidents of this shape have now bought: a header counts as verified only when a
real browser engine has loaded the page and reported no CSP violation.

## User stories

- AS a reader of the site I WANT the language and theme toggles to respond to a
  click, and my stored preference to be applied on the next visit, SO THAT the
  site works as it presents itself.
- AS the operator of the production contract I WANT the CSP hash to be emitted in
  the exact form a browser accepts SO THAT a strict policy protects the page
  instead of silently disabling it.
- AS a reviewer of a future cycle I WANT `scripts/check-headers.mjs` to reject an
  unquoted hash, a stale hash, and any hash-shaped token that is not a valid
  source expression SO THAT this regression cannot ship green a second time.
- AS a maintainer of the test suite I WANT the new assertion proven by mutation in
  both directions, with assertions on the failure messages, SO THAT a refactor
  that stops running the check fails the suite instead of passing it.
- AS a future implementer I WANT ADR-0006 to state that a header is verified only
  by a browser engine SO THAT the boundary between the CI pre-filter and the
  operator's browser step is written down rather than rediscovered.

## Acceptance criteria (EARS)

### Generator

- WHEN `node scripts/csp-hash.mjs` runs against a valid `dist/`, THE SYSTEM SHALL
  write exactly one token of the form `'sha256-<base64>'` — including the leading
  and trailing single quote — to stdout, followed by a newline.
- WHILE more than one hash source is emitted, THE SYSTEM SHALL quote each token
  individually and separate them with a single space, because
  `__SCRIPT_SRC_HASHES__` is documented as a space-separated list of sources.
- IF `security-headers.conf` is edited to wrap `__SCRIPT_SRC_HASHES__` in quotes,
  THEN THE SYSTEM SHALL be considered non-compliant: the quoting belongs to each
  token, not to the template, and `test/nginx.test.ts` continues to assert the
  placeholder appears unchanged.
- WHILE the generator changes, THE SYSTEM SHALL keep its existing failure modes
  unchanged: zero HTML files, zero inline script bodies, more than one distinct
  body, and a body over the 400-byte cap each still fail with the current message.

### Image build

- WHEN `docker build` substitutes the token into
  `/etc/nginx/security-headers.conf`, THE SYSTEM SHALL assert the result contains
  a hash source in the quoted form `'sha256-<base64>'`.
- IF the substituted file contains a hash-shaped token (`sha256-`, `sha384-` or
  `sha512-`) that is not immediately preceded by a single quote, THEN THE SYSTEM
  SHALL fail the image build.
- WHILE the grep guard is tightened, THE SYSTEM SHALL keep the existing
  `! grep -q "__SCRIPT_SRC_HASHES__"` placeholder assertion and the surrounding
  `RUN` chain semantics unchanged.
- WHEN the built image serves any response, THE SYSTEM SHALL send
  `content-security-policy: default-src 'self'; script-src 'self' 'sha256-<base64>'; style-src 'self'; font-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.

### Runtime checker

- WHEN `node scripts/check-headers.mjs <base-url>` runs, THE SYSTEM SHALL parse
  the `Content-Security-Policy` header by splitting it on `;`, selecting the
  `script-src` directive, and splitting that directive on whitespace, rather than
  testing the header for a substring.
- IF any `script-src` token contains `sha256-`, `sha384-` or `sha512-` anywhere in
  the token and is not exactly `'<algo>-<base64>'` wrapped in single quotes, THEN
  THE SYSTEM SHALL record a problem whose message contains the offending token
  verbatim and exit with a non-zero status.
- WHEN the checker runs, THE SYSTEM SHALL additionally `GET /`, extract the inline
  `<script>` body with the same regular expression `scripts/csp-hash.mjs` uses,
  compute its SHA-256 in base64, and require the `script-src` directive to contain
  exactly `'sha256-<that hash>'`.
- IF the served CSP carries a correctly quoted hash that does not equal the hash of
  the inline script actually served, THEN THE SYSTEM SHALL record a problem naming
  both the expected and the found token and exit with a non-zero status.
- WHILE the hash checks are replaced, THE SYSTEM SHALL keep every existing check
  unchanged: all eight security headers with their expected values on every probed
  path, the absence of any `http(s)` origin in the CSP, the `/_astro/` discovery
  and fallback behaviour, and the expected status code per path.

### Proof by mutation

- WHEN `npm test` runs, THE SYSTEM SHALL execute a test that asserts, for the same
  checker used by `scripts/check-headers.mjs`: a CSP with the hash correctly quoted
  yields no problems; the same CSP with the surrounding single quotes stripped
  yields at least one problem; and a CSP with a correctly quoted but wrong hash
  fails the end-to-end comparison.
- WHILE asserting the failing cases, THE SYSTEM SHALL assert on the content of the
  failure messages — the offending token for the unquoted case, the expected and
  found token for the stale case — and not only on the fact that a failure
  occurred.
- WHEN a new test file is added under `test/`, THE SYSTEM SHALL add it to the
  explicit file list in the `test` script of `package.json`, which names each test
  file rather than globbing.

### Documentation and ADR

- WHEN `docs/hardening-notes.md` is read, THE SYSTEM SHALL contain the exact CSP
  string as served, with the quoting, and one short paragraph stating that the
  mechanical checks were insufficient because they asserted the presence of a
  substring rather than the validity of a source expression.
- WHEN `astro build` runs, THE SYSTEM SHALL accept a new ADR-0006 with
  `id: 6`, `status: accepted`, `visibility: public`, a `date` equal to the day the
  change lands, and all five Nygard sections (Context, Decision, Consequences,
  Drivers, Revisit criteria) in that order, each carrying both an English and a
  Russian block, exactly as `src/lib/adr.ts` (`checkAdrBodies`) requires.
- WHEN `/colophon/` renders, THE SYSTEM SHALL list ADR-0006 in the ADR index table
  with a link to `/colophon/adr/0006-browser-verified-security-headers/`, and that
  page SHALL exist in `dist/`.
- WHILE the new content lands, THE SYSTEM SHALL keep `scripts/check-dist.mjs`
  green: every `dist/**/*.html` has equal counts of `class="l en"` and
  `class="l ru"`, and no file under `dist/` ends in `.js`.

## Out of scope

Everything below is deliberately deferred to a later cycle in this wave and must
not be touched here:

- Link colour in content (`#0000EE` on dark, WCAG 1.4.3) — separate cycle.
- Colophon table overflow, timestamp formatting, lead-time computation.
- The `/work/` page: links inside `<details>`, list indentation, private-repo
  placeholders.
- Toggle spacing in RU, `aria-current`, skip-link, `role="group"`, `<summary>`
  headings.
- `og:image` PNG, font preload, `Cache-Control` on static assets, the DevLoop
  diagram.
- Adding a headless browser to CI. The browser step belongs to the production
  contract, run by the operator; ADR-0006 says so explicitly.

Also out of scope for this proposal, for the reasons given in Open questions:

- Any change to `security-headers.conf`, `nginx.conf` or `src/layouts/Base.astro`.
  The inline script and the CSP template are correct as written; only the token
  emitted into the template is wrong.
- Superseding or editing ADR-0001..0005.

## Open questions

1. **The issue names `0006-browser-verified-security-headers.en.md` and `.ru.md`;
   this repository has no such file shape.** Every ADR under `src/content/adr/` is
   a single bilingual file (`0001-bootstrap-boundary.md` .. `0005-…md`), and the
   loader in `src/content.config.ts` globs `[0-9][0-9][0-9][0-9]-*.md` and then runs
   `checkAdrBodies`, which fails any body missing an English or a Russian block.
   Two single-language files would therefore fail `astro build` outright, produce
   two collection entries with the same frontmatter `id: 6` in the `/colophon/`
   index, and make `scripts/check-dist.mjs` expect pages at
   `/colophon/adr/0006-…-security-headers.en/`. Acceptance criterion 6 of the issue
   ("`astro build` accepts it; the ADR index on `/colophon/` lists it") is only
   satisfiable by the repository's actual convention, so this proposal specifies
   **one** file, `src/content/adr/0006-browser-verified-security-headers.md`,
   carrying both languages in `.l.en` / `.l.ru` pairs. The issue's EN and RU prose
   is used verbatim, in that one file.
2. **The issue supplies no ADR title.** All five sections are given verbatim, but
   `title.en` / `title.ru` are required by the schema. This proposal fixes them as
   `Browser-verified security headers` / `Заголовки безопасности, проверенные
   браузером`; the full frontmatter is written out in `design.md` so the
   implementer copies rather than invents it.
3. **Acceptance criterion 2 of the issue asks for the `curl -sI` output to be
   "visible in the PR".** `AGENTS.md` states that the implementer opens its pull
   request from a fixed template it cannot edit, so a criterion satisfied only in
   the PR body deadlocks the cycle. The evidence is therefore redirected to two
   places the implementer can commit: the exact served header string is recorded in
   `docs/hardening-notes.md` (which criterion 5 already requires), and
   `scripts/check-headers.mjs` proves the same property mechanically against the
   running container in `.github/workflows/build.yml`. No behaviour is lost; only
   the location of the evidence changes.
4. **No journal entry is authored by this proposal.** `AGENTS.md` requires one
   `src/content/journal/` entry per DevLoop cycle, but its schema requires
   `issue_opened_at` (and the cycle's other timestamps), which are not derivable
   from the proposal. The issue also does not list the journal among the files
   expected to change. The entry is left to the cycle-closing step by whoever holds
   those timestamps; `tasks.md` carries it as an optional, clearly-marked task.
5. **The date in ADR-0006 frontmatter must be the day the change lands.** The
   proposal writes `'2026-09-11'`, the date the issue was raised and the expected
   landing day. If the commit lands later, the implementer sets the actual date;
   nothing else in the file changes.
