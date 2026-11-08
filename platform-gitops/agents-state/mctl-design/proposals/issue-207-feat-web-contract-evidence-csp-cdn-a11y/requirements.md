# Web contract evidence: CSP/CDN/a11y baseline for six sites (epic #330, `web-contract-evidence`)

## Context

Issue mctlhq/mctl-design#207 is the first required evidence item (`web-contract-evidence`) of epic
mctlhq/.github#330. The owner chose `STANDARDIZE_CONTRACTS_KEEP_RUNTIMES` in spike mctlhq/.github#328
(decided in PR #331). The spike report pins source and GitOps/ArgoCD image parity, but the effective
HTTP Content-Security-Policy, the CDN CORS/cache behaviour of `ui.mctl.ai`, and browser accessibility
and no-JS behaviour of the shared public site header have not been observed. Unknowns must not be
read as passes, and must not be used to justify relaxing any CSP.

The deliverable is a single docs-only evidence report committed to `mctl-design` under
`docs/evidence/web-contract-evidence.md`, with source-pinned, dated, provenance-tagged findings for
mctl-web (`mctl.ai`), mctl-docs (`docs.mctl.ai`), mctl-telegram (`tg.mctl.ai`), mctl-academy
(`academy.mctl.ai`), mctl-alice (`alice.mctl.ai`) and seerrsense (`seerrsense.mctl.ai`), plus the
design CDN `ui.mctl.ai`. It ends with an evidence/unknown/owner matrix and explicit entry gates for
the next epic items `web-header-a11y-contract` and `web-asset-integrity-contract`. No code, CSS, JS,
CSP, CI, GitOps or production change is part of this work.

## User stories

- AS the epic #330 owner I WANT one reproducible evidence report per site SO THAT the next contract
  items are scoped on observed facts rather than assumptions.
- AS a security reviewer I WANT every CSP/CORS/cache claim tagged with its provenance and date SO
  THAT an unobserved value can never be mistaken for a passing one.
- AS a site owner (web, docs, telegram, academy, alice, seerrsense) I WANT findings mapped to my
  repository and to existing issues SO THAT I receive bounded next steps without duplicate tickets.
- AS a reviewer I WANT safe reproduction commands SO THAT I can re-run every live observation
  without touching auth flows or user data.

## Acceptance criteria (EARS)

- WHEN the report is written THE SYSTEM SHALL record, for each of the six sites and `ui.mctl.ai`,
  four separately labelled layers: independently inspected source SHA/tag `[CODE]`, GitOps desired
  image (`values.yaml` `image.tag`) `[CONFIG]`, authenticated ArgoCD observed image/sync/health `[LIVE]`,
  and anonymous public HTTP response `[LIVE]` (or `not-run`). The report SHALL additionally state
  whether the image-tag-to-source-commit relationship was independently established; a match of
  tags or a short SHA-looking image tag is NOT proof of deployed source provenance.
- WHEN a finding is stated THE SYSTEM SHALL use one supported provenance classification:
  `[CODE]` for pinned inspected source, `[CONFIG]` for GitOps declared/desired configuration,
  `[LIVE]` for authenticated observed ArgoCD state or anonymous HTTP observation (explicitly name
  which), `[PREVIEW]` for isolated preview, or `unknown (not observed)` with a reason. The report
  SHALL record UTC date/time and the source SHA, image tag or URL as applicable. `not-run` denotes
  an unexecuted check, while `not-applicable` denotes a behaviour genuinely absent by design;
  neither is a passing test or a substitute for provenance.
- WHEN a site's use of the design system is reported THE SYSTEM SHALL state the exact
  `ui.mctl.ai` URLs (versioned `/<X.Y.Z>/...css` or floating `/...css`) and/or `@mctlhq/*` package
  version found in that site's pinned source, and whether that equals `0.20.2`.
- WHEN a live HTTP observation is made THE SYSTEM SHALL use only anonymous read-only `GET`/`HEAD`
  requests without cookies, credentials or crafted query parameters, against public pages and the
  public CDN stylesheets, and SHALL record `Content-Security-Policy` (and `-Report-Only`),
  `Cache-Control`, `ETag`, `Last-Modified`, a SHA-256 of the body for stylesheets,
  `Access-Control-Allow-Origin`, `Vary`, `Age`/CDN cache status headers, and the redirect chain.
- IF a live request is blocked by edge protection, times out, or no HTTP tool is available THEN THE
  SYSTEM SHALL record the item as `not-run` with the reason and SHALL NOT infer a value.
- WHILE documenting auth, consent, OAuth, error or redirect routes THE SYSTEM SHALL use only pinned
  source `[CODE]`, GitOps `[CONFIG]` or isolated preview/synthetic fixtures `[PREVIEW]`, and SHALL NOT
  navigate production auth sessions, send credentials, invoke OAuth callbacks or generate sensitive
  query parameters.
- WHEN browser behaviour of the shared site header is reported THE SYSTEM SHALL cover: burger
  toggle, keyboard Enter/Space/Escape, outside pointer click, `aria-expanded`/`aria-controls`
  state, focus return to the burger, tab order, the 768px and 981px (`--drawer-wide`) breakpoints,
  `prefers-reduced-motion`, and no-JS rendering; and SHALL separate "observed result" from
  "proposed acceptance criterion".
- WHEN a particular header check does not apply because the implementation does not expose that
  mechanism (e.g. a JS drawer listener in Telegram's CSS-only public menu) THE SYSTEM SHALL
  mark it `not-applicable` with pinned `[CODE]` justification. User-visible accessibility outcomes
  (keyboard activation/dismissal, focus, tab order and no-JS operation) SHALL NOT be marked
  `not-applicable` merely because the site uses CSS-only navigation or VitePress native components.
- IF browser or preview testing is not permitted or not possible for a site THEN THE SYSTEM SHALL
  mark applicable, untested behaviours `not-run` with a reason; it SHALL NOT infer `PASS` or
  substitute `not-applicable` for inaccessible test infrastructure.
- WHEN the matrix is built THE SYSTEM SHALL list, per row, the claim, the evidence tag, the
  observed value or `unknown`, the test status (`observed`, `not-run`, or justified
  `not-applicable`), the owning repository, and the existing tracking issue (design#34,
  design#78, telegram#599, academy#210, gitops#500) where one applies, and SHALL NOT create new
  implementation issues that duplicate them.
- WHEN the report concludes THE SYSTEM SHALL state explicit, bounded entry gates for
  `web-header-a11y-contract` and `web-asset-integrity-contract`, each with an owner, and SHALL NOT
  start or approve any implementation.
- WHILE the report exists THE SYSTEM SHALL keep sensitive routes under their current strict policy:
  no finding SHALL recommend relaxing a CSP.
- WHEN the evidence PR is opened THE SYSTEM SHALL change only files under `docs/` and SHALL pass the
  existing `ci.yml` checks (notably `format:check`), with independent human review before merge.

## Out of scope

- Modifying JS, CSS, tokens, Vue components, or `nginx.conf` / `security-headers.conf`.
- Adding SRI enforcement, changing any CSP, adding CI jobs or monitoring infrastructure.
- Moving runtimes, changing GitOps values, ArgoCD apps or production configuration.
- Authenticated, consent, OAuth or callback flows against production; accessing any private user data.
- Creating new implementation issues where design#34, design#78, telegram#599, academy#210 or
  gitops#500 already track the work.
- Approving or triggering any DevLoop implementer, including a docs-only one; that needs a separate
  digest-bound human approval.

## Open questions

- Report path: the issue leaves it to the investigator. This proposal uses
  `docs/evidence/web-contract-evidence.md` (no `docs/` directory exists in the repo today). The
  reviewer may prefer a different path or placement in mctlhq/.github next to the spike report.
- Whether the implementer run is allowed to make outbound HTTP requests and run a headless browser
  against public production pages. If not, every `[LIVE]` row is `not-run` and the report ships with
  reproduction commands only; this is acceptable under the issue but reduces its value.
- Which preview environments exist for header tests. Only `tg-preview.mctl.ai`
  (labs/mctl-telegram-preview, image `main-5fb1de8`) was observed; for the other sites, `[PREVIEW]`
  evidence would come from local static builds of pinned source or the mctl-design Storybook
  `Foundations/Site Header` stories, not from per-site previews.
- mctl-web's GitOps host list is `mctl.ru` and `mctl.ai`; whether `mctl.ru` is in scope (the issue
  only names `mctl.ai`). Proposed: observe both redirect behaviour, report `mctl.ai` in full.
- The six source repositories are not in this clone; pinning their source SHAs requires read access
  to them at implement time. The inspected `main` SHA, GitOps tag and ArgoCD image are independent
  observations until an image digest, build attestation, immutable release mapping or equivalent
  provenance joins the deployed artifact to a particular commit. If unavailable the mapping is
  `unknown (not observed)` even when GitOps and ArgoCD tags match.
