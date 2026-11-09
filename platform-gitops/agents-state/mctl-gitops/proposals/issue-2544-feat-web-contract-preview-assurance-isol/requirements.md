# Web contract preview assurance: isolated browser/a11y and CSS/SRI/CSP verification harness (P3)

## Context

Epic mctlhq/.github#330 has three earlier parts:

- P0 evidence (mctl-design#207, PR #208) captured anonymous HTTP headers and four CSS SHA-256 matches.
- Two contracts are merged in mctl-design:
  - `docs/contracts/web-header-a11y.md` (contract `web-header-a11y` v1.0.0, HDR-1..HDR-16, cases `AC-<HDR>-<consumer>-<route class>`), from mctl-design#209, PR #212, merge `918d671651f8e9d3eb2882f7581a9a0495588929`;
  - `docs/contracts/web-asset-integrity.md` (manifest spec, delivery modes A/B, gates G1-G4), from mctl-design#210, PR #211, merge `9561bf725fc21c21b02d1142b198d6e74ec89394`.

Every test matrix in those contracts is still `not-run`. No browser, a11y, runtime SRI, CORS, CSP or failure test has run against any of the six consumers: mctl-web, mctl-docs, mctl-telegram, mctl-academy, mctl-alice and seerrsense.

Issue mctlhq/mctl-gitops#2544 is the required work item `web-contract-preview-assurance` (phase `assurance`, owner mctl-gitops). It asks for an isolated, reproducible preview-only assurance slice. mctl-gitops is the coordinator. The slice has three parts:

- a pinned browser harness with isolated fixtures;
- a fail-closed evidence matrix that maps real test IDs back to the contract IDs;
- a decision memo on what is proven.

None of this changes production behavior, consumer repositories, CSP, Cloudflare or package pins. Without this slice, gate G3 (SRI enforcement) and any per-consumer adoption would rest on claims instead of observed results. Gate G3 is defined in `web-asset-integrity.md`.

## User stories

- AS the epic #330 owner I WANT a deterministic, preview-only test matrix for both signed-off contracts SO THAT G2/G3 consumer rollout decisions rest on observed results, not on assumptions.
- AS a consumer owner (mctl-web, mctl-docs, mctl-telegram, mctl-academy, mctl-alice, seerrsense) I WANT a per-site row with PASS/FAIL/NOT-RUN and a reason SO THAT I know which HDR requirements and integrity gates my site meets, and which exceptions need my sign-off.
- AS a reviewer I WANT every result pinned to a source commit, an image digest, a browser image digest and an attempt ID SO THAT I can reproduce it and trust that no missing test turned into a PASS.
- AS a platform operator I WANT the harness to run without any cluster deploy, GitOps sync, production auth or outbound network SO THAT running it cannot change or harm any live service.

## Acceptance criteria (EARS)

Pinning and provenance

- WHEN the harness runs, THE SYSTEM SHALL record all of the following in the run's `run.json`:
  - the Playwright image by digest (`mcr.microsoft.com/playwright:v1.64.1-noble@sha256:...`);
  - the mctl-design source commit (40-hex) and both contract IDs and versions;
  - each consumer's source commit or OCI image digest, or `not-run` with a reason;
  - the attempt ID;
  - the SHA-256 digest of the artifact bundle.
- IF any pin in `assurance/web-contracts/pins.json` is a tag, a branch, a short SHA or a floating URL, THEN THE SYSTEM SHALL fail the run before any browser starts.
- THE SYSTEM SHALL label every matrix cell with exactly one provenance tag from the contracts' legend: `[CODE]`, `[CONFIG]`, `[PREVIEW]`, `[LIVE]` or `not-run`.

Fail-closed result mapping

- WHEN the report is generated, THE SYSTEM SHALL derive each cell's PASS or FAIL only from a JUnit testcase that executed. A testcase that is skipped, missing, errored before its assertion, or absent for a catalogued case SHALL be reported as `NOT-RUN` with a reason.
- IF a contract case ID has no mapped executed test, THEN THE SYSTEM SHALL report it as `NOT-RUN`, never PASS.
- IF any executed test fails, THEN THE SYSTEM SHALL mark the affected site and gate as "not compliant" and SHALL exit non-zero. The summary SHALL state "no compliance claim".
- WHEN the self-test (negative-control) suite runs against the deliberately broken fixtures, THE SYSTEM SHALL require every negative control to produce FAIL. If any negative control passes, THE SYSTEM SHALL fail the whole run. The broken fixtures cover a bad SHA, an SRI mismatch, a CORS-denied response, a CSP deny, a broken Escape handler, lost focus, a missing `aria-expanded`, and an animation that ignores reduced motion.

Header accessibility (contract `web-header-a11y` v1.0.0)

- WHEN a header case runs, THE SYSTEM SHALL exercise HDR-1..HDR-16 in an isolated Chromium session:
  - a11y navigation landmark;
  - Enter/Space on the toggle;
  - Tab order closed and open;
  - Escape closes and restores focus;
  - outside pointer and scrim;
  - `aria-expanded`, or a source-proven native equivalent;
  - route transition;
  - viewport growth past `B`;
  - `prefers-reduced-motion: reduce`;
  - JS-disabled link reachability;
  - an axe scan of the header region.
- WHILE testing a site, THE SYSTEM SHALL use that site's own breakpoint `B` at `B-1` and at `B`, plus 375px and 1280px. It SHALL keep the 768px and 981px values distinct and SHALL NOT impose a common breakpoint.
- WHERE a site uses a CSS checkbox (mctl-telegram) or the VitePress native navigation (mctl-docs), THE SYSTEM SHALL test the behavioral equivalent the contract defines. Where the contract registers an exception (EX-1, EX-2, EX-3), THE SYSTEM SHALL report that exception as pending sign-off, not as PASS.

Asset integrity (contract `web-asset-integrity`, G1-G4)

- WHEN an asset case runs, THE SYSTEM SHALL compute SHA-256 over the `0.20.2` sheets (`mctl.css`, `global.css`, `prose.css`, `site.css`) from mctl-design `apps/storybook/public/0.20.2/` at the pinned commit. It SHALL compare them byte-for-byte with a test-only frozen manifest fixture labelled "test-only, not a published artifact" (G1).
- WHEN SRI cases run, THE SYSTEM SHALL serve those bytes from a local fixture origin inside the isolated network and SHALL assert the browser outcome for each of these cases:
  - valid sha384 with `crossorigin="anonymous"` and ACAO `*`: the sheet applies;
  - sha384 mismatch: the sheet is blocked and the page stays readable;
  - CORS denied (no ACAO): the sheet is blocked;
  - a locally vendored (Mode B) copy: hash parity with Mode A;
  - CDN unreachable and no-JS: the fallback renders.

  Network errors and console messages SHALL be captured.
- WHEN cache cases run, THE SYSTEM SHALL assert `Cache-Control: public, max-age=31536000, immutable` for versioned paths and `max-age=3600` for floating paths at the fixture origin, which reuses mctl-design `nginx.conf` at the pinned commit. The origin-versus-edge TTL discrepancy (3600 versus 14400) SHALL be recorded as `not-run` at the edge unless an authorized anonymous GET is enabled.
- WHEN CSP cases run, THE SYSTEM SHALL apply test-only CSP headers on the fixture origin: an allow case (`style-src 'self' https://ui.mctl.ai`, using a local stand-in host) and a deny case (`style-src 'self'` with a cross-origin sheet). It SHALL assert the blocked or applied outcome and the reported violation.

Sensitive-route and production guard

- WHILE any test runs, THE SYSTEM SHALL run the browser and fixture containers on a Docker network created with `--internal`, so there is no outbound network. Playwright SHALL abort every request whose host is not on the fixture allowlist.
- IF a test target resolves to a production host, an OAuth/connect/manage/consent/callback route, or a real credential or cookie, THEN THE SYSTEM SHALL refuse to run that case and SHALL report it as `NOT-RUN (sensitive-route guard)`.
- WHILE anonymous public GET/HEAD probing is not explicitly enabled by an owner-set `allow_public_probe: true` input, THE SYSTEM SHALL make no request to any public host.
- THE SYSTEM SHALL NOT deploy to the cluster, trigger a GitOps sync, create a preview through `preview-deploy`, change any CSP or Cloudflare rule, or enable SRI on any production page.

Artifacts

- WHEN a run completes, THE SYSTEM SHALL emit `junit.xml`, `results.json`, `matrix.md` and screenshots and traces of failures only, with every URL sanitized to its host and path. GitHub Actions artifact retention SHALL be 7 days.

## Out of scope

- Any change to consumer repositories (mctl-web, mctl-docs, mctl-telegram, mctl-academy, mctl-alice, seerrsense) or to mctl-design source. Tests are not added to mctl-design#14 or #34 by this proposal.
- Changes to live CSP, Cloudflare or CDN rules, ingress, package version pins, Telegram MTProto, academy#210, telegram#599, design#78 or gitops#500.
- SRI enforcement, a shared header script, publishing a real release manifest, and any migration or production rollout.
- Making this workflow a required check on mctl-gitops `main`.
- Binding the issue in `mctlhq/.github/roadmap/epics/web-platform-contracts.yaml`. That is a separately reviewed roadmap PR.

## Open questions

- Consumer runnability. The harness can only produce `[PREVIEW]` rows for consumers whose OCI image starts in an isolated network with dummy env and no backend. This proposal assumes that is plausible for mctl-web, mctl-docs and seerrsense. It may not be for mctl-telegram (MTProto), mctl-alice (OAuth) or mctl-academy (backend). Sites that cannot start report `not-run` with the observed reason; no consumer change is made to fix that. Owners should confirm which images are expected to start standalone.
- GHCR access. Whether `ghcr.io/mctlhq/<consumer>` packages are readable by the mctl-gitops `GITHUB_TOKEN` (`packages: read`) has not been observed. If they are not, the affected consumer rows stay `not-run`.
- Site breakpoints for mctl-web, mctl-docs and mctl-telegram are `unknown (not observed)` in the contract. The harness takes `B` from `pins.json`. Until an owner or pinned source supplies it, those sites' `B-1`/`B` cases are `NOT-RUN (breakpoint unknown)`.
- Public probing. The issue allows "explicitly authorized anonymous safe HEAD/GET" only. This proposal keeps it off by default (`allow_public_probe: false`). Who authorizes it, and for which hosts, is open.
- Reuse of mctl-design browser infrastructure. Reuse means the same pinned Playwright image and the same docker-run conventions as `scripts/browser-tests-docker.sh`, invoked from mctl-gitops. It does not mean a change inside mctl-design. If the owner prefers the header cases to live in mctl-design#14/#34 Storybook stories instead, that is a separate mctl-design issue. This harness would then only consume their JUnit output.
