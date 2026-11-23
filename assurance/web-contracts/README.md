# Web contract preview assurance

Preview assurance only; not production conformance.

This directory holds an isolated, preview-only harness for the two mctl-design
contracts `web-header-a11y` (1.0.0) and `web-asset-integrity` (gates G1-G4). It
is tracked by mctlhq/mctl-gitops#2929 (re-file of #2544). It deploys nothing,
syncs nothing, and changes no consumer repository, CSP, Cloudflare or package pin.

## What is here today

| Path | State |
| --- | --- |
| `pins.json` | present: every pin, validated before anything runs |
| `report/build_report.py` | present: `--check-pins` and report generation (stdlib only) |
| `report/gen_cases.py` | present: generates and checks `cases.json` (stdlib only) |
| `cases.json` | present: the case catalogue (test id to AC/HDR or G id); the specs generate one test per case |
| `fixtures/` | present: fixture origin config, test-only manifest, `header/`, `assets/`, `broken/` (eight negative controls) |
| `tests/*.spec.ts`, `tests/guard.ts`, `playwright.config.ts`, `package.json`, `package-lock.json` | present: `@playwright/test` 1.64.1, `playwright-core` 1.64.1 and `@axe-core/playwright` 4.14.0, exact |
| `run.sh` | present: isolated run, report, guard counters, cleanup by name |
| `../../tests/test_web_contract_report.py` | present: fail-closed mapping tests (no browser) |
| `../../.github/workflows/web-contract-assurance.yml` | present: runs `run.sh` on PRs touching these paths and on demand; read-only token, no secrets, 7-day artifact, not a required check |
| consumer promotion | `mctl-web` is `mode: image`; the other five stay `not-run` until each is exercised in CI |
| spike document | present: `docs/spikes/2929-web-contract-preview-assurance.md` (evidence report and decision memo) |

## Reproduce

Available now:

```sh
# unit tests of the fail-closed report (no browser, no network)
python3 tests/test_web_contract_report.py

# pin check, syntax only (digests, 40-hex commits, exact versions, no non-fixture URLs)
python3 assurance/web-contracts/report/build_report.py --check-pins

# pin check plus the pinned mctl-design commit: needs a local mctl-design checkout
python3 assurance/web-contracts/report/build_report.py --check-pins --design-repo /path/to/mctl-design

# the same sheet facts without this script: the directory exists at the pin and the
# sha256 / sha384 of its four sheets (compare with pins.json mctl_design.sheets)
C=6d82a6b239365213d6859f2794c2449af7dd4e1f; D=/path/to/mctl-design; git -C $D ls-tree --name-only $C apps/storybook/public/0.21.0/ && for f in mctl global prose site; do git -C $D show $C:apps/storybook/public/0.21.0/$f.css | shasum -a 256; git -C $D show $C:apps/storybook/public/0.21.0/$f.css | openssl dgst -sha384 -binary | openssl base64 -A; echo; done
```

Without `--design-repo` the sheet check prints `design-sheets: NOT-RUN` and
verifies nothing about the commit; it never reports a silent pass. With a path
that cannot be read the check is a hard error, not a skip.

Recorded when this was written (2026-11-23): the pinned commit contains
`apps/storybook/public/0.21.0/` and `0.20.2/`, and the sha256 and sha384 of all
eight sheets equal the values in `pins.json` (`--check-pins --design-repo` exits 0).

Full run (needs Docker, Node and a local mctl-design checkout holding the pinned commit, or network access to fetch it):

```sh
# pin check, git archive of mctl-design at the pin, npm ci from the lockfile and image
# availability happen BEFORE isolation; then docker network create --internal, the fixture
# origin, Playwright in the pinned image, the report, and removal of everything this run created
WCA_DESIGN_REPO=/path/to/mctl-design assurance/web-contracts/run.sh

# print the docker commands without running anything (also prints the mode:image consumer
# commands for a pins file in which a site has mode image)
assurance/web-contracts/run.sh --consumer-plan-only
WCA_PINS=/path/to/pins-with-an-image-site.json assurance/web-contracts/run.sh --consumer-plan-only

# report only, from a finished run
python3 assurance/web-contracts/report/build_report.py \
  --junit assurance-out/junit.xml --cases assurance/web-contracts/cases.json \
  --pins assurance/web-contracts/pins.json --out-dir assurance-out --artifact assurance-out.tgz
```

`run.sh` environment: `WCA_PREFIX` (name prefix of every container and the network, default
`wca-run`; an existing network of that name is never touched), `WCA_OUT`, `WCA_WORK`,
`WCA_DESIGN_REPO`, `WCA_PINS`, `WCA_PW_ARGS` (extra Playwright arguments; a filtered run proves
nothing; it also exits 5, because the fixture cases are NOT-RUN). Extra exit codes: 4 = the guard saw
an unexpected request, its log is unreadable, or it holds fewer records than executed tests; 5 = setup
failed, the Playwright runner crashed (exit code other than 0 or 1), or a fixture case outside the
documented allowlist (G4, the catalogued known gaps) is NOT-RUN. After a change to the catalogue run `python3 assurance/web-contracts/report/gen_cases.py`.

## Isolation as built

- The Playwright dependencies are installed on the host from the lockfile before isolation, into a
  directory outside the repository, and mounted read-only.
- Every container runs as the runner UID with `--read-only`, `--cap-drop ALL`,
  `--security-opt no-new-privileges`, `--pull=never`, a `--pids-limit`, tmpfs for `/tmp`, no published
  ports and no Docker socket. The repository is mounted read-only; `/out` is the only writable mount.
- `tests/guard.ts` aborts a request to a host outside the allowlist (the `pins.json` fixture hosts plus
  the consumer aliases `run.sh` creates) and any path with a segment starting with oauth, oidc, auth,
  authorize, connect, manage, consent, callback, login, logout, signin, signup, sso, token or session
  (the path is percent-decoded until stable, lowercased and stripped of `;params` first), and records
  `guard-blocked`. A test that did not declare a deliberate probe fails when anything was blocked;
  `run.sh` sums the counters and exits 4 on any unexpected request or when the records do not account
  for every executed test (a spec using Playwright's bare `page` or `request` fixture leaves no record).
  The counter is an in-band tripwire: it sees only requests the browser contexts route through the
  guard (not WebSockets). The enforcement is the `--internal` network and the container hardening
  below, which are the sole isolation layers once consumer pages are exercised; Chromium runs
  with its sandbox disabled inside the cap-dropped container.
- `run.sh` refuses to start when a container or the network named `<prefix>-...` already exists, labels
  every container it creates with `wca.run=<id>` and removes only containers that carry its own label.
- `assurance-out/` (the default `WCA_OUT`) is gitignored.
- The "CDN unreachable" G3 case aborts the requests to the stand-in sheet host in the browser (the page
  and the sheets share one origin container), instead of stopping the container.

## Case catalogue note

Consumer rows for HDR-1, 13, 14 and 16 also run at 1280, a superset of the viewport set in the
contract's AC matrix (no AC id is missing or extra); HDR-11 runs at `B-1` and returns to `B`.
A `known_gap` skips only the single named assertion (the Enter step of HDR-4, the checked/hidden-state
checks of HDR-11); any other failure in those cases is a FAIL.

## Pins

`pins.json` pins the Playwright image and the nginx image by digest, mctl-design
by a 40-hex commit (css `0.21.0`, with `0.20.2` also covered), the contract ids
and versions as written in the documents at that commit, and one entry per
consumer. Consumer `gitops_tag` is a snapshot of
`platform-gitops/services/*/values.yaml` and moves with every release: re-read it
when a site is promoted. `observed_image_digest` is a note, not a pin: every site
stays `mode: not-run` with `image: null` until it has started healthy on the
internal network. Whether a consumer starts standalone is `unknown (not observed)`.

`--check-pins` rejects: an image without `@sha256:<64 hex>`, a commit that is not
40 lowercase hex, a range for `@playwright/test`, any `http(s)://` URL whose host
is not in `fixture_hosts`, a `mode: image` site whose image is null or not
digest-pinned, a `not-run` site without a reason, and a site list that is not
exactly the six sites.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `PASS` | a JUnit testcase for the catalogued case executed and passed, on a site whose pins mode is `image` (or a fixture target) |
| `FAIL` | the testcase executed and failed; no compliance claim. On a fixture or harness case the run exits 1; on a consumer case it is a finding (exit 0, listed under `summary.consumer_findings`, annotated in the workflow) |
| `NOT-RUN` | missing testcase, skipped, error before the assertion, or pins mode not `image`; always carries a reason; never PASS |
| `EXCEPTION-PENDING` | the testcase passed but the case is a registered exception (EX-1, EX-2, EX-3) awaiting owner sign-off; never PASS |

Negative controls are inverted: each must FAIL. A control that PASSES, or does
not run, exits 2 ("scaffolding cannot detect failure"). Exit codes: 0 ok, 1 a case
FAILed, 2 a control is broken, 3 unreadable or malformed input or a rejected pin.
Provenance tags per cell: `[CODE]`, `[CONFIG]`, `[PREVIEW]`, `[LIVE]` or `not-run`.

## Boundaries

- The report iterates over `cases.json`, never over JUnit: a case nobody ran is `NOT-RUN`.
- "Could not observe" is never "observed absent": malformed or unreadable junit,
  cases or pins is a hard error with no output, never an empty result.
- Every URL in any emitted text is reduced to host and path (no query, fragment or userinfo).
- No cluster deploy, GitOps sync, Vault, OIDC, outbound network after isolation,
  production host, OAuth/connect/manage/consent/callback route, real credential or cookie.
- Fixtures label themselves reference targets, never a consumer row.
- Not a required check; revert the PR to remove it.

## Substituted hosts (consumer pages)

A consumer page references the design sheets on the production CDN host (`ui.mctl.ai`) and web fonts on
`fonts.googleapis.com` / `fonts.gstatic.com`. None of them is reachable from the internal network, and
without the sheets a consumer renders unstyled, so every layout case would fail for a harness reason.
The guard therefore answers exactly two kinds of request locally instead of sending them anywhere:

- `https://ui.mctl.ai/<pinned version>/<sheet>.css` (GET, no port, no userinfo; versions from `pins.json`
  `mctl_design`; sheets `mctl|global|prose|site`). The bytes come from the read-only pinned mctl-design
  archive and are checked at serve time: a regular file (a symlink is never followed) whose sha-256 equals
  the one `pins.json` records for exactly that version and sheet. A missing, corrupted or unpinned file
  is blocked, not served. Any other path on that host is blocked. The response carries
  `access-control-allow-origin: *`, which the harness supplies: what production `ui.mctl.ai` sends is not
  verified here.
- GET requests over https to the two font hosts get an empty `text/css` response, whatever the path, so
  no web font is ever loaded. Font metrics can therefore differ from production, and a layout result that
  depends on them is not evidence. Non-GET and non-https requests to these hosts are blocked.

Answered requests are counted as `substituted` in `guard.jsonl` and never as requests that reached the
host: the claim is "nothing left the network", not "nothing was requested". `run.sh` writes
`substitutions.json` (per test and in total) before it builds the hashed bundle and passes it to the
report: `results.json` carries `substitutions`, every case that ran with answered requests carries
`answered_locally` and shows it in the matrix, and the matrix header states the font limitation. A report
built without the file says the substitution state is unknown; an unreadable file is a hard error.
Case `WCA-A-ISO-guard-design-host` proves the decision table, that every pinned sheet of every pinned
version is served with its pinned sha-256, that an unpinned version is blocked, and the serve-time checks.

## Contract scope decisions (owner, 2026-11-23)

- **HDR-1** counts named navigation landmarks inside the header region only (AC-1: "inspect the header
  navigation landmark"). A named landmark in page content or a footer is not the header's.
- **HDR-14** counts every link of the header region carrying `aria-current="page"`, the brand link
  included: exactly one. The route-change step (click a route link, the marker must follow) runs only for
  a site that declares `selectors.routes` in `pins.json`; a section anchor or an external link is not a
  route, and the harness never guesses one from an href. Without `selectors.routes` the case is NOT-RUN
  with the reason "route-change step not run", never PASS. The fixtures declare their links as routes.
- **HDR-7** on `mctl-web` is a catalogued `known_gap` (NOT-RUN, "observed gap, no exception registered"): the
  toggle follows the panel in DOM order, exactly as in the mctl-design `SiteHeader` reference stories, so
  Tab from the toggle cannot reach the panel links, while the contract row requires the toggle then the
  panel links in DOM order. Only the open-state Tab walk is covered by the gap; the closed-state checks still
  run. The gap converts a failure into NOT-RUN and nothing else: a site whose toggle precedes its panel
  passes. Mutation-verified on the fixture (toggle moved after the nav turns HDR-7 red).
- **HDR-8 / HDR-12** put focus inside the open panel directly (`focus()` on the first panel link) instead of by
  Tab from the toggle, because that route depends on the DOM order HDR-7 covers. What is asserted after the
  Escape or the link click (the panel closes, focus is on the toggle or the navigation target) is unchanged,
  and the `no-escape` and `focus-lost` negative controls still FAIL.
- **HDR-15** measures transitions that would actually run, on the panel (`nav`) and the toggle's icon lines
  (`::before`, `::after`): exactly the selectors of the `prefers-reduced-motion` block in `site.css`, which the
  contract names as the implementation. A transition runs when its `transition-property` is not `none` and
  duration plus delay is above zero (an animation: name not `none`, duration above zero). A global
  `transition-duration: 0.01ms !important` reset on top of `transition: none` therefore does not count; the
  `fixture-reset` case proves that, and the `motion-ignored` control proves a real transition still FAILs. The
  detector precondition (something runs without the preference) turns a detector that measures nothing red.

## Declared, expected blocks (`expected_blocked`)

A consumer page may call hosts the isolated run does not allow (mctl-web: an analytics script, a bot-check
script, a signup-status call). Without a declaration the guard fails every test that page loads in, which
hides the outcome of the assertions. A site can list exact `host/path` strings under `sites[].expected_blocked`
in `pins.json` (host and path as the guard logs them, no scheme, query, port or wildcard; the format is checked, and an
entry with a dot segment, an empty segment or a trailing newline is rejected). A request matching an entry is
still aborted and never answered, so nothing leaves the network and no response is invented; it is counted per
host and path as `expected_blocked`, shown on the case row and in the matrix, and the matrix states that the
page ran without those scripts and calls, so a result that depends on them is not evidence.

Matching is on the lower-cased host plus path only: the scheme, port, userinfo, query and HTTP method of the request are
not part of the entry, so `http://` and `https://`, any port and any method to that host and path are all matched (and all
still aborted). Only a host the allowlist refuses can be declared: a declared entry for an allowlisted host with a sensitive path
(`/oauth/...`), an unparseable URL, another path on the same host or the same path on another host is still an
unexpected block that fails the test. A case where an undeclared block was seen is NOT-RUN, worded as "the case
outcome is not a verdict", because the guard error is raised by the fixture teardown, after the assertions ran. A PASS
that ran with declared blocks stays PASS, but the site is never `Compliant` while one exists, and the matrix counts them.
A declared entry that a run never saw is listed as "declared but never observed" (stale or mistyped). `WCA-A-ISO-guard-expected-blocked`
proves each of those, and was mutation-verified (honouring a declared sensitive path turns it red).

HDR-2 counts the control selected as the toggle that has the role and an accessible name, not every named button on
the page (the same page-wide scope mistake as HDR-1).

## Verdict split: harness failure or consumer finding

The job is red when the harness itself is broken: a fixture case FAILs (exit 1), a negative control does not FAIL
(exit 2), an input or pin is rejected (3), the guard cannot account for the run (4) or setup or completeness fails
(5). A consumer case that FAILs is evidence about the consumer, not a broken run: the exit code stays 0, there is
still no compliance claim, `results.json` lists the ids under `summary.consumer_findings` (and `harness_failures`
separately), the matrix header counts both, and the workflow raises a warning annotation per run so a finding is not
hidden behind a green job. Merging a consumer promotion therefore does not turn the advisory check red.

HDR-13 on a narrow viewport gives each panel link focus directly instead of walking to it with Tab, for the same
reason as HDR-8 and HDR-12: the visibility of the focus indicator does not depend on DOM order, which HDR-7 owns.
On a wide viewport the Tab walk stays. The toggle's own indicator is still checked after a real Tab from the brand.


## Declared dummy environment for a consumer (`env`, `tmpfs`)

Some consumer images need a few variables or a writable path to start under the hardened run (read-only root, all
capabilities dropped). `sites[].env` maps upper-case names to plain placeholder values and `sites[].tmpfs` lists up to
four absolute paths mounted as small tmpfs (`noexec,nosuid,nodev`, 16 MiB). Both are checked before anything runs:
`PORT` is reserved (the harness forces 8080), values use a small shell-inert character set that excludes `@` (so
credentials cannot ride in a URL) and any URL in the file must still point at a fixture host, and a tmpfs path may not
be `/` or lie in or below `/proc`, `/sys` or `/dev`, contain a `.` or `..` segment, or carry mount options. The file is public: only
placeholders belong here, never a real secret. The declared values are appended after the harness defaults. A site that
still does not start stays NOT-RUN with the last three sanitized log lines as the reason.

## Sensitive paths and static asset files

The guard refuses any request whose path has a segment starting like an auth word (`oauth`, `login`, `token`,
`session` and the rest of the list in `tests/guard.ts`). That prefix rule also read a site's own `/assets/tokens.css` as a
token endpoint and blocked its stylesheet, so a page ran unstyled and the guard failed the run. The final segment of
a path that does not end in a slash is now treated as a file, not a route, when it ends in one of a narrow list of inert
asset extensions (`css`, `js`, `mjs`, `map`, `svg`, `png`, `jpg`, `jpeg`, `gif`, `webp`, `avif`, `ico`, `woff`, `woff2`).
Every directory segment above it is still checked (`/oauth/x.css` stays blocked), a decoded trailing slash makes it a
directory again (`/tokens.css%2F`), and `.json`, `.html`, `.php` and extensionless names stay routes (`/token`, `/tokens`,
`/token.json`). `guard-oauth-path` holds the table and was mutation-verified in both directions.
