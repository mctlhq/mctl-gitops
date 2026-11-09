# Tasks: issue-207-feat-web-contract-evidence-csp-cdn-a11y

Precondition: a separate digest-bound human approval of this proposal. All tasks are read-only except
writing `docs/evidence/web-contract-evidence.md`.

- [ ] 1. Record run header: UTC date, mctl-design SHA, tool availability (HTTP client, headless
      browser, access to the six source repos), provenance tag legend — DoD: header block present;
      every unavailable tool named with reason.
- [ ] 2. (depends on 1) Parity table: for mctl-web, mctl-docs, mctl-telegram, mctl-academy,
      mctl-alice, seerrsense and mctl-design, record independently inspected source SHA/tag
      `[CODE]`, GitOps desired `image.tag` `[CONFIG]`, and authenticated ArgoCD observed image and
      sync/health via `mctl_list_services` / `mctl_get_service_status` `[LIVE]`. Separately check
      image-tag-to-source provenance via immutable build metadata, digest or release attestation;
      do not infer deployed source SHA from `main` or an image tag matching a short SHA — DoD:
      source, desired, observed and HTTP layers distinguishable, unproven deployed-source mapping
      `unknown (not observed)`, tag parity and missing reads explicitly recorded.
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
      reduced motion, JS disabled — DoD: per site/check, "observed", "proposed criterion", status
      and reason; `not-run` for applicable but unexecuted tests, `not-applicable` only for a
      source-proven absent implementation mechanism. Telegram's CSS-only menu and VitePress native
      navigation still require applicable user-visible keyboard, focus and no-JS checks; a missing
      browser tool is never N/A. Reproduction script quoted in report, not committed.
- [ ] 8. (depends on 2-7) Evidence/unknown/owner matrix linking design#34, design#78,
      telegram#599, academy#210, gitops#500 — DoD: every claim has provenance tag, value or
      `unknown`, observation/test status (`observed`, `not-run`, or justified `not-applicable`),
      owner repo, existing issue or "none"; no new implementation issues created.
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
- [ ] T4. Grep/check the report: every evidence row uses `[CODE]`, `[CONFIG]`, `[LIVE]`,
      `[PREVIEW]` or `unknown (not observed)` as provenance, and an independent status where
      relevant (`observed`, `not-run` with reason, or justified `not-applicable`). Confirm
      authenticated ArgoCD data is `[LIVE]` and desired GitOps is `[CONFIG]`.
- [ ] T5. Grep the report for `Cookie:`, `Authorization`, tokens, `code=`, `state=` query
      parameters: none present.
- [ ] T6. CONDITIONAL: If anonymous public HTTP requests were available, a reviewer re-runs two
      `[LIVE]` reproduction commands and records matching headers or dated drift. If outbound
      HTTP was unavailable, blocked or out of scope, mark T6 `not-run` with reason, keep the
      unobserved rows `unknown (not observed)`, and include reproduction commands for a later
      authorized run. T6 `not-run` is not a pass and does not block a truthful docs-only evidence
      report; downstream adoption of CDN/SRI contracts must retain an evidence gate.
- [ ] T7. Confirm `Dockerfile` does not copy `docs/` into the image, so `ui.mctl.ai` output is unchanged.

## Rollback

Revert the docs-only commit or close the PR. Nothing is deployed, no configuration or production
state is changed, so no other rollback is needed.
