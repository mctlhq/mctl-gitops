# Tasks: issue-2544-feat-web-contract-preview-assurance-isol

Precondition: this proposal is approved through its exact content digest by the owner. Nothing below runs before that approval. All work happens in mctl-gitops only. There is no cluster deploy, no GitOps sync, and no change to consumer repos or to mctl-design.

- [ ] 1. Create `assurance/web-contracts/pins.json` and `README.md`.
  - `pins.json` holds:
    - the Playwright `v1.64.1-noble` image by digest;
    - the nginx image by digest;
    - mctl-design `918d671651f8e9d3eb2882f7581a9a0495588929`;
    - contract IDs and versions read from the merged `docs/contracts/*.md` at that commit;
    - six `sites[]` entries with GitOps tags from `platform-gitops/services/*/values.yaml`. Each entry starts as `mode: not-run` with a reason, `image: null` and `breakpoint` from the contract (981 for academy and alice, 768 for seerrsense, null for the others).
  - `README.md` gives exact reproduce commands, boundaries and the status vocabulary.
  - DoD: the file contains no tag-only or short-SHA pins. The README states "preview assurance only; not production conformance".
- [ ] 2. Write `assurance/web-contracts/report/build_report.py` (stdlib only) with `--check-pins` and report generation (depends on 1).
  - The report iterates over `cases.json`.
  - Status mapping: missing, skipped or early-error becomes NOT-RUN with a reason. A negative control that passes exits 2.
  - It writes `results.json`, including the attempt ID, pins and artifact SHA-256, and `matrix.md`, the six-site table plus the AC/G1-G4 crosswalk.
  - URLs are sanitized to host and path.
  - DoD: `--check-pins` rejects bad pins, and both outputs are produced from a sample JUnit file.
- [ ] 3. Add `tests/test_web_contract_report.py` (stdlib, `python3 tests/...` style) with synthetic JUnit fixtures (depends on 2).
  - DoD: it covers PASS, FAIL, skipped becoming NOT-RUN, a missing testcase becoming NOT-RUN, a negative control that passes (exit 2), exception becoming EXCEPTION-PENDING, an unsanitized URL being stripped, and an unpinned image being rejected.
- [ ] 4. Build the fixtures under `assurance/web-contracts/fixtures/` (depends on 1).
  - The origin `nginx.conf` is derived from mctl-design `nginx.conf` at the pin, plus test-only CSP allow/deny and ACAO on/off server blocks on stand-in `*.fixture.test` hosts.
  - `manifest-0.20.2.test-only.json` is labelled test-only and not published.
  - `header/reference.html` and `header/checkbox.html` load `site.css` from the pinned archive.
  - `broken/` holds the eight negative controls: bad-sha, sri-mismatch, no-acao, csp-deny, no-escape, focus-lost, no-aria-expanded, motion-ignored.
  - DoD: no fixture references a production hostname. `grep -r 'mctl\.ai\|mctl\.ru' fixtures/` matches only comments that cite provenance.
- [ ] 5. Write `tests/guard.ts`, `tests/header.spec.ts`, `tests/assets.spec.ts` and `cases.json`, plus `package.json` and a lockfile with `@playwright/test@1.64.1` and `@axe-core/playwright` pinned exactly (depends on 4).
  - DoD: every test ID `WCA-H-*` and `WCA-A-*` appears in `cases.json` with its AC/HDR or G id.
  - Sensitive route classes target fixtures only.
  - A site with `breakpoint: null` emits NOT-RUN for its `B-1`/`B` cases.
- [ ] 6. Write `assurance/web-contracts/run.sh` (depends on 2, 5).
  - It runs the pin check, then fetches `git archive` of mctl-design at the pin before isolation.
  - It creates the network with `docker network create --internal` and starts the fixture origin and the `mode: image` consumers with dummy env and a 60 s health wait (failure becomes NOT-RUN with a sanitized reason).
  - It runs Playwright in the pinned image, builds the report, and always removes the containers and network (`trap`).
  - DoD: the script runs locally with no outbound request after isolation, verified by guard counters equal to 0 for unexpected hosts.
- [ ] 7. Add `.github/workflows/web-contract-assurance.yml` (depends on 3, 6).
  - Triggers: `workflow_dispatch` (input `allow_public_probe` default `false`, unused) and `pull_request` filtered to its own paths.
  - Permissions: `contents: read` and `packages: read`. Actions pinned by SHA. No secrets, Vault or OIDC. Event data is bound through `env:`, per `validate-gha-expression-injection.py`.
  - It uploads `assurance-out/` with `retention-days: 7`. Not a required check.
  - DoD: `validate-gha-expression-injection.py` and yamllint pass, and `validate-manifests.yml` is unchanged.
- [ ] 8. Promote consumers from `not-run` to `mode: image`, one at a time, in the same PR (depends on 7).
  - For each consumer, resolve the digest of the GitOps tag's image. Try it in CI. Keep `mode: image` only if it starts healthy on the internal network with dummy env. Otherwise record the observed reason.
  - DoD: each of the six rows is either backed by an executed case or carries a concrete `not_run_reason`. No consumer repository is modified.
- [ ] 9. Write `docs/spikes/2544-web-contract-preview-assurance.md` from the first CI run (depends on 8).
  - It includes the STATUS line, pins, reproduce commands, the six-site matrix with run URL and artifact digest, the contract crosswalk, missing inputs with owners (design#34, design#78, telegram#599, academy#210, gitops#500), pending exceptions (EX-1/2/3), and the decision memo. The memo says rollout readiness for G2/G3 is not a GO.
  - DoD: every PASS in the report cites an executed test ID from the linked run. The report contains no PASS without a test.

## Tests

- [ ] T1. `python3 tests/test_web_contract_report.py` passes. It covers the fail-closed mapping, pin rejection and URL sanitization.
- [ ] T2. Negative controls: a run against `fixtures/broken/*` yields FAIL for all eight. Flipping one broken fixture to the conformant one makes the run exit 2, which proves red detection.
- [ ] T3. Reference fixture: all HDR cases at 375, 767/768 and 980/981 (both breakpoint variants), plus 1280, are PASS on `reference.html`. On `checkbox.html` the cases are PASS or EXCEPTION-PENDING (EX-1/EX-2), and never PASS for HDR-5/6/8/12.
- [ ] T4. Assets: G1 SHA-256 equal for all four `0.20.2` sheets. SRI valid applies; mismatch and no-ACAO block, with the page readable. CSP deny raises a violation; CSP allow applies. Versioned and floating cache headers match. Origin-down plus no-JS fallback is readable.
- [ ] T5. Isolation: a test that requests `https://mctl.ai/` and one that requests an `/oauth/` path are aborted by `guard.ts` and reported as `NOT-RUN (sensitive-route guard)` or `guard-blocked`. `docker network inspect` shows `Internal: true`.
- [ ] T6. The CI workflow runs on the PR with the artifacts uploaded. The job is red if any non-control case FAILs.

## Rollback

All changes are additive and contained in `assurance/web-contracts/`, `tests/test_web_contract_report.py`, `.github/workflows/web-contract-assurance.yml` and `docs/spikes/2544-*.md`. Revert the PR to remove them.

No cluster, ArgoCD, Vault, CSP, Cloudflare or consumer state is touched, so nothing else needs undoing. If the workflow misbehaves, disable it in the GitHub UI or delete the workflow file. Uploaded artifacts expire after 7 days, or they can be deleted manually from the run.
