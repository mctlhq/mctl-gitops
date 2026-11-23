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
| `../../tests/test_web_contract_report.py` | present: fail-closed mapping tests (no browser) |
| `cases.json`, `fixtures/`, `tests/*.spec.ts`, `run.sh`, workflow | NOT present yet (PR 2). Commands below marked "after PR 2" do not work until that lands. |

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

Available after PR 2 lands (not runnable today):

```sh
# full run: pin check, fixture origin on a --internal network, Playwright, report
assurance/web-contracts/run.sh

# report only, from a finished run
python3 assurance/web-contracts/report/build_report.py \
  --junit assurance-out/junit.xml --cases assurance/web-contracts/cases.json \
  --pins assurance/web-contracts/pins.json --out-dir assurance-out --artifact assurance-out.tgz
```

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
