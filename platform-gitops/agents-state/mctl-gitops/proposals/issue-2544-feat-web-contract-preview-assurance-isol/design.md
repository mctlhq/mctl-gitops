# Design: issue-2544-feat-web-contract-preview-assurance-isol

## Current state

mctl-gitops has no browser, a11y or web-asset test tooling today. The investigation read the clone at `77d31f8bedc3c43536b428950603d54fe8f170bc` (2026-11-09T13:10:39Z).

- `grep -ri playwright` returns hits only inside proposal documents under `platform-gitops/agents-state/`, never in code.
- `scripts/` holds Python validators run by CI. Examples: `validate-glovo-m1-staging.py`, `validate-obi-spike.py`, and `validate-gha-expression-injection.py`, which has a `--selftest` that proves it detects. `tests/` holds stdlib-only `python3 tests/test_*.py` checks, with fixtures in `tests/fixtures/`.
- `.github/workflows/validate-manifests.yml` is the required validator. Its comment at line ~320 warns that "a paths filter would block every PR (or let a skipped check pass)". `tests/test_required_check_job_ids.py` pins the required job IDs. Actions are pinned by commit SHA, for example `actions/checkout@3d3c42e5...` (# v7).
- `tests/test_base_images_pinned.py` requires `@sha256` digests for base images inside `platform-gitops/argo-workflows` and `platform-gitops/bootstrap`. That establishes the repo's "pin by digest" convention.
- `.github/workflows/no-root-yaml.yml` rejects top-level `*.yaml` and `*.yml` files. Nested YAML in a new top-level directory is allowed.
- `.github/workflows/auto-merge.yml` lists `protected_re` paths that need a human merge. `validate-manifests.yml` is on that list, so this proposal does not touch it.
- `platform-gitops/argo-workflows/cluster-templates/wft-preview-deploy.yaml` deploys preview Helm releases into `{team}-preview`. The issue forbids "cluster deploy ... just to run a browser test", so this proposal does not use it.
- Spike and evidence docs live under `docs/spikes/<issue>-<slug>.md`, for example `docs/spikes/2286-obi-evaluation.md`. They use a `STATUS:` line and the rule that "not observed" never means "absent".
- The prior proposals `platform-gitops/agents-state/mctl-design/proposals/issue-209-*` and `issue-210-*` are both `status: merged`, as PR #212 and PR #211. They record:
  - the contract structure: HDR-1..16, cases `AC-<HDR>-<consumer>-<route class>`, exceptions EX-1 (telegram checkbox: HDR-5/6), EX-2 (telegram no-JS: HDR-8/12) and EX-3 (docs, conditional), and gates G1-G4;
  - the Storybook runner `scripts/browser-tests-docker.sh` with `mcr.microsoft.com/playwright:v1.64.1-noble`;
  - the `0.20.2` sheet bytes and sha384 values (`[CODE]` only);
  - mctl-design `nginx.conf`: versioned sheets are `immutable, max-age=31536000` with ACAO `*`, floating sheets are `max-age=3600`, and no CSP is set;
  - breakpoints: academy and alice `981px`, seerrsense and the `site.css` default `768px`, mctl-web, mctl-docs and mctl-telegram unknown.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-design/values.yaml`: `image.tag "918d671651f8"`, hosts `ui.mctl.ai` and `admins-mctl-design.mctl.ai` `[CONFIG]`. This is the PR #212 merge commit `918d671651f8e9d3eb2882f7581a9a0495588929`, so both contracts are in the deployed image.
- `mctl_get_service_status(admins, mctl-design)`: `Synced`, `Healthy`, imageTag `918d671651f8`, updatedAt `2026-11-09T13:23:12Z`. `revision` is empty, so the deployed digest is `unknown (not observed)`.
- `services/admins/mctl-web/values.yaml`: `ghcr.io/mctlhq/mctl-web:7.21.1`, hosts `mctl.ru` and `mctl.ai`.
- `services/admins/mctl-docs/values.yaml`: `ghcr.io/mctlhq/mctl-docs:0.1.66`, `docs.mctl.ai`.
- `services/labs/mctl-telegram/values.yaml`: `ghcr.io/mctlhq/mctl-telegram:0.137.1`, `tg.mctl.ai`.
- `services/labs/mctl-telegram-preview/values.yaml`: tag `main-27c671d`, host `tg-preview.mctl.ai`. This is a long-lived preview service, but it is reachable only over the public internet, so this harness does not use it.
- `services/labs/mctl-academy/values.yaml`: `0.1.76`, `academy.mctl.ai`.
- `services/labs/mctl-alice/values.yaml`: `2.13.1`, `alice.mctl.ai`.
- `services/labs/seerrsense/values.yaml`: `1.14.1`, `seerrsense.mctl.ai`.
- Not observed in this run:
  - consumer source, header selectors and breakpoints for web, docs and telegram;
  - consumer OCI digests, and whether the GHCR packages can be read from mctl-gitops CI;
  - whether any consumer image starts without its backend.

  No HTTP request or browser run was made. These gaps are recorded under Open questions in requirements.md.

## Proposed solution

Add a self-contained, preview-only harness in a new top-level directory, `assurance/web-contracts/`. Add one evidence report, `docs/spikes/2544-web-contract-preview-assurance.md`, and one non-required workflow. Nothing under `platform-gitops/` changes, so ArgoCD sees no diff.

### Layout

```
assurance/web-contracts/
  README.md                 exact reproduce commands, boundaries, status vocabulary
  pins.json                 every pin; validated before anything runs
  cases.json                catalog: test id -> contract id (AC/HDR, G1-G4), site, route class, viewport
  run.sh                    docker orchestration (internal network, no egress)
  fixtures/
    origin/nginx.conf       copy of mctl-design nginx.conf at the pinned commit + test-only CSP/ACAO variants
    manifest-0.20.2.test-only.json   frozen SHA-256/sha384, labelled test-only, not a published artifact
    header/reference.html   conformant synthetic header (site.css drawer + minimal behavior script)
    header/checkbox.html    CSS-checkbox equivalent (telegram pattern, no JS)
    broken/                 negative controls: bad-sha, sri-mismatch, no-acao, csp-deny,
                            no-escape, focus-lost, no-aria-expanded, motion-ignored
  tests/
    header.spec.ts          HDR-1..16 parameterized by target + breakpoint
    assets.spec.ts          G1 byte equality, SRI valid/mismatch/CORS-denied, Mode B parity,
                            cache headers, CDN-down + no-JS fallback, CSP allow/deny
    guard.ts                request interceptor: abort non-allowlisted hosts and sensitive paths
  report/
    build_report.py         stdlib Python: junit.xml + cases.json + pins.json -> results.json, matrix.md
tests/test_web_contract_report.py  unit tests for fail-closed mapping (no browser)
.github/workflows/web-contract-assurance.yml
docs/spikes/2544-web-contract-preview-assurance.md
```

### Pins (`pins.json`)

`pins.json` holds:

- `playwright_image`: `mcr.microsoft.com/playwright:v1.64.1-noble@sha256:<digest>`. The implementer resolves the digest once and records it. The `@playwright/test` version is `1.64.1`, pinned in `assurance/web-contracts/package.json` with a lockfile.
- `mctl_design`: commit `918d671651f8e9d3eb2882f7581a9a0495588929`; contracts `web-header-a11y@1.0.0` and `web-asset-integrity` at the version recorded in the merged document; design version `0.20.2`.
- `sites[]`: one entry per consumer, holding:
  - `name`;
  - `gitops_tag` `[CONFIG]`;
  - `image` (`ghcr.io/mctlhq/<site>@sha256:...`, or null);
  - `source_commit` (40-hex, or null);
  - `breakpoint` (number, or null);
  - `route_classes`, from the contract's approved list, with `sensitive` always mapped to fixture-only;
  - `mode`: `image`, `fixture-only` or `not-run`;
  - `not_run_reason`.

`run.sh` first runs `build_report.py --check-pins`. That check rejects any image without `@sha256:`, any commit that is not 40-hex, any `http(s)://` URL to a non-fixture host, and any `mode: image` site that has no digest.

### Isolation (`run.sh`)

`run.sh` works like this:

1. Run `docker network create --internal wca-<attempt>`, so the network has no egress.
2. Start the fixture origin: an `nginx` container pinned by digest that serves the mctl-design bytes and fixtures. The mctl-design bytes come from a read-only `git archive` of the pinned commit, fetched before the network is created. The origin answers on stand-in hostnames such as `ui.fixture.test` and `site.fixture.test` (network aliases), never on production names.
3. For each `mode: image` site, start the consumer image by digest on the same internal network. It gets dummy env only: no Vault, no secrets, and `OAUTH_*`/`TELEGRAM_*` unset or set to dummy values. If the container is not healthy within 60 s, record `NOT-RUN (image did not start: <last log line, sanitized>)`.
4. Run Playwright in the pinned image on the same network, with `--user` set to the runner UID and the repo mounted read-only.

`guard.ts` registers `page.route('**/*')` and aborts any request to a host outside the allowlist, recording `guard-blocked` in the results. A case whose route class is `sensitive`, or whose path matches `/(oauth|connect|manage|consent|callback|auth)/`, runs only against `fixtures/` and never against an image.

This mirrors the mctl-design `scripts/browser-tests-docker.sh` convention: the same image and Playwright version, run in Docker. It is a bounded mctl-gitops copy of the invocation, not a second test platform. The header cases are written so they can later move into the mctl-design#14/#34 Storybook stories without changes.

### Header cases (`header.spec.ts`)

Test IDs are `WCA-H-<HDR>-<site>-<routeclass>-<viewport>`. They map 1:1 to the contract's `AC-<HDR>-<consumer>-<route class>` through `cases.json`.

For each target (the reference fixture, the checkbox fixture, and each running consumer image) at viewports `B-1`, `B`, 375 and 1280, the spec checks:

- landmark name and axe on the header region (HDR-1, 2, 13);
- Enter/Space toggles (HDR-4);
- `aria-expanded`, or the registered equivalent (HDR-5, 6);
- Tab order closed and open (HDR-7);
- Escape plus focus return (HDR-8, 12);
- outside click and scrim (HDR-9);
- client route change (HDR-10);
- resize past `B` (HDR-11);
- `aria-current` (HDR-14);
- `emulateMedia({reducedMotion: 'reduce'})` with zero computed `transition-duration` (HDR-15);
- a JS-disabled context reaching every primary nav link (HDR-16).

Two rules keep the results honest:

- An exception case (EX-1/2/3) asserts the documented equivalent behavior and reports `EXCEPTION-PENDING`, never PASS.
- A site with `breakpoint: null` yields `NOT-RUN (breakpoint unknown)` for its `B-1`/`B` cases.

### Asset cases (`assets.spec.ts`)

Test IDs are `WCA-A-G<n>-<case>`.

- **G1 byte equality.** Node `crypto` computes SHA-256 of each `0.20.2` sheet from the pinned archive and compares it with `manifest-0.20.2.test-only.json` and with the body served by the fixture origin.
- **G2 SRI, in a real browser.**
  - Valid sha384 with crossorigin and ACAO: computed styles change.
  - Mismatch: the sheet is not applied, a console error is captured, and the page text stays readable.
  - ACAO removed: the sheet is blocked.
  - Mode B (the vendored copy on the same origin) has equal hashes.
- **G3 preconditions.** Cache headers for versioned and floating paths. Origin unreachable (container stopped) plus no-JS: the fallback content stays readable.
- **CSP.** Two test-only header variants on the origin. Allow: the sheet applies. Deny: the sheet is blocked and a `securitypolicyviolation` event is captured.
- **G4.** Exact pinning is a `[CODE]` check of consumer manifests. It is `not-run` here because consumer source is out of scope, and it is reported as such.

### Report and fail-closed mapping (`build_report.py`)

`build_report.py` iterates over `cases.json`, not over JUnit. It derives each case's status like this:

- No `<testcase>`, a `<skipped>` element, or an `<error>` raised before the first assertion: `NOT-RUN` with a reason.
- A `<failure>`: `FAIL`.
- Otherwise: `PASS`, carrying the provenance tag of its target. Fixtures are `[PREVIEW]`; a consumer image is `[PREVIEW]` and names its digest.

The negative-control cases are inverted: they must report FAIL, and a PASS there exits 2 with "scaffolding cannot detect failure".

The script writes:

- `results.json`, which includes the attempt ID (`GITHUB_RUN_ID-GITHUB_RUN_ATTEMPT`, or a local UUID), every pin, and the SHA-256 of the artifact tarball;
- `matrix.md`, with the six-site by route class by gate table and the AC/G crosswalk.

`summary.compliant` is true only when every catalogued case of a site is PASS. The report always prints "preview assurance only; not production conformance". URLs are reduced to host and path; query strings and fragments are dropped.

### CI (`.github/workflows/web-contract-assurance.yml`)

The workflow:

- triggers on `workflow_dispatch` (input `allow_public_probe`, default `false`, reserved and unused until an owner authorizes it) and on `pull_request` with a paths filter on `assurance/web-contracts/**`, the workflow file, and `tests/test_web_contract_report.py`;
- is not a required check, which follows the validate-manifests warning about paths filters;
- has `permissions: contents: read, packages: read`;
- pins actions by SHA;
- has no Vault, no deploy key and no OIDC;
- runs a job that:
  1. checks out the repo;
  2. runs `python3 tests/test_web_contract_report.py`;
  3. fetches mctl-design at the pinned commit;
  4. pulls the pinned images;
  5. runs `run.sh`;
  6. uploads `assurance-out/` with `retention-days: 7`.

The job fails if `build_report.py` exits non-zero. Failures therefore block any compliance claim. They do not block unrelated PRs.

### Evidence report

`docs/spikes/2544-web-contract-preview-assurance.md` has a `STATUS:` line: `PENDING_RUN` until the first CI run, then `EVIDENCE_RECORDED`. It contains:

- the pins;
- the reproduce commands;
- the six-site matrix copied from the first green-or-red run's `matrix.md`, with the run URL and artifact digest;
- the contract crosswalk;
- missing inputs, each with an accountable owner (design#34, design#78, telegram#599, academy#210, gitops#500);
- per-site exceptions needing sign-off;
- a decision memo stating what is proven, what is unknown, and that G2/G3 rollout readiness is not an automatic GO.

## Alternatives

- **Put all cases into mctl-design Storybook (design#14/#34) and run them there.** This reuses the most existing infrastructure. Dropped for this proposal for three reasons: it changes another repository, which the issue requires to be a separate reviewed gate; Storybook cannot host consumer images or test-only CSP and CORS origins; and the implementer of this proposal works only in mctl-gitops. The header specs are written so they can move there later.
- **Use `preview-deploy` to stand up per-consumer previews in `{team}-preview` and test them over HTTPS.** Dropped. The issue forbids a cluster deploy or GitOps sync just to run a browser test. Previews are also internet-reachable, which breaks the no-egress isolation, and they need preview Vault seeds.
- **Test the live public hosts with anonymous GETs.** Dropped as the default. That would be `[LIVE]`, not isolated preview assurance. It cannot exercise SRI mismatch, CORS denial or CSP deny without changing production, and the issue allows it only with explicit authorization. It is kept as a disabled, owner-gated input.

## Platform impact

- **No migration and no runtime change.** No file under `platform-gitops/`, `infrastructure/` or `deploy/` changes. ArgoCD has no diff, and no tenant, CSP, Cloudflare or CDN rule is touched.
- **Backward compatibility.** The new workflow is not required and only triggers on its own paths, so existing PRs are unaffected. `no-root-yaml` passes because YAML files are nested.
- **Resources.** CI only: one ubuntu runner for about 10-20 minutes, pulling the Playwright image (about 2 GB), nginx and up to six consumer images. There is no cluster cost.

| Risk | Mitigation |
| --- | --- |
| A consumer image phones home or needs secrets. | The `--internal` network blocks egress. Dummy env only. Startup failure yields `NOT-RUN`, not a workaround. |
| A test that never ran is reported as PASS. | The report iterates over the case catalog. Negative controls must fail. Unit tests cover the mapping. |
| Leaked URLs or cookies in artifacts. | No real sessions. URLs are sanitized. Screenshots and traces are kept for failures only, with 7-day retention. |
| The fixture header differs from real consumers. | Fixture results are labelled "reference", never as a consumer row. Consumer rows come only from consumer images, or stay `not-run`. |
| The Playwright image or GHCR packages are unavailable. | The pin check fails before the run. An unreadable image gives `NOT-RUN` with the reason. |
