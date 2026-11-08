# Tasks: issue-207-feat-web-contract-evidence-csp-cdn-a11y

Precondition: a separate digest-bound human approval of this proposal. All tasks are read-only except
writing `docs/evidence/web-contract-evidence.md`.

- [ ] 1. Record run header: UTC date, mctl-design SHA, tool availability (HTTP client, headless
      browser, access to the six source repos), provenance tag legend — DoD: header block present;
      every unavailable tool named with reason.
- [ ] 2. (depends on 1) Parity table: for mctl-web, mctl-docs, mctl-telegram, mctl-academy,
      mctl-alice, seerrsense and mctl-design, record source SHA of the deployed tag `[CODE]`, GitOps
      `image.tag` from `services/<tenant>/<svc>/values.yaml` `[CONFIG]`, ArgoCD observed image and
      sync/health via `mctl_list_services` / `mctl_get_service_status` `[CONFIG]` — DoD: four layers
      per row, mismatches flagged, missing reads marked `unknown (not observed)`.
- [ ] 3. (depends on 2) Design usage per site: grep pinned source for `ui.mctl.ai` URLs and
      `@mctlhq/*` versions — DoD: exact URLs/versions listed, each classified as `0.20.2`, other pin,
      or floating.
- [ ] 4. (depends on 1) CDN evidence for `ui.mctl.ai`: anonymous `curl` of floating and `/0.20.2/`
      `{mctl,global,prose,site}.css` with and without `Origin: https://mctl.ai`; record status,
      Cache-Control, ETag, Last-Modified, Age/cache-status, ACAO, Vary, CSP, body SHA-256; compare with
      `nginx.conf` and `sha256sum apps/storybook/public/0.20.2/*.css` — DoD: each header row tagged
      `[LIVE]` with value or `not-run`; divergences from `nginx.conf` listed.
- [ ] 5. (depends on 1) Public page headers for the six sites (landing page only, plus `mctl.ru`
      redirect): redirect chain, CSP/CSP-Report-Only verbatim, cache headers, Vary; `Set-Cookie`
      names only — DoD: one row per site, `[LIVE]` or `not-run`, reproduction command per row.
- [ ] 6. (depends on 2) Sensitive routes from pinned source/config only: auth, consent, OAuth,
      error, redirect routes and their declared CSP — DoD: `[CODE]`/`[CONFIG]`/`[PREVIEW]` rows only;
      explicit statement that no production auth route was requested.
- [ ] 7. (depends on 1) Header behaviour with Playwright from the pinned image used by
      `scripts/browser-tests-docker.sh`: Storybook `Foundations/Site Header` stories at the pinned
      SHA, `tg-preview.mctl.ai`, and anonymous public landing pages where permitted; at 768px and
      981px; toggle, Enter/Space/Escape, outside pointer, `aria-expanded`, focus return, tab order,
      reduced motion, JS disabled — DoD: per site and check, "observed" and "proposed criterion"
      columns; `not-run` where not executed; script quoted in the report, not committed.
- [ ] 8. (depends on 2-7) Evidence/unknown/owner matrix linking design#34, design#78,
      telegram#599, academy#210, gitops#500 — DoD: every claim has tag, value or `unknown`, owner repo,
      existing issue or "none"; no new implementation issues created.
- [ ] 9. (depends on 8) Next gates for `web-header-a11y-contract` and
      `web-asset-integrity-contract` with owners and entry conditions — DoD: bounded, no CSP
      relaxation recommended, nothing started or approved.
- [ ] 10. (depends on 9) Open a docs-only PR (conventional commit `docs: add web contract evidence
      baseline (#207)`), linking epic mctlhq/.github#330 — DoD: diff touches only `docs/`; CI green;
      independent human review requested; not self-merged.

## Tests

- [ ] T1. `pnpm format:check` and `pnpm lint` pass with the new Markdown file.
- [ ] T2. `git diff --name-only origin/main` lists only `docs/evidence/web-contract-evidence.md`.
- [ ] T3. `pnpm check:token-version` and `pnpm check:versions` pass without a version bump.
- [ ] T4. Grep the report: every table row contains one of `[CODE]`, `[CONFIG]`, `[LIVE]`,
      `[PREVIEW]`, `unknown (not observed)` or `not-run`.
- [ ] T5. Grep the report for `Cookie:`, `Authorization`, tokens, `code=`, `state=` query
      parameters: none present.
- [ ] T6. A reviewer re-runs two `[LIVE]` reproduction commands and gets matching headers (or a
      documented, dated drift).
- [ ] T7. Confirm `Dockerfile` does not copy `docs/` into the image, so `ui.mctl.ai` output is unchanged.

## Rollback

Revert the docs-only commit or close the PR. Nothing is deployed, no configuration or production
state is changed, so no other rollback is needed.
