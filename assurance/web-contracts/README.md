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
| spike document, consumer promotion | NOT present yet (later PRs) |

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
| `FAIL` | the testcase executed and failed; the run exits 1 and makes no compliance claim |
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
