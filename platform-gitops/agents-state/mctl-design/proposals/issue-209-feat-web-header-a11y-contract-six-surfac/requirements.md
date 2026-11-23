# Web header accessibility contract: six-surface navigation behavior specification (docs-only)

## Context

Epic mctlhq/.github#330 (decided outcome `STANDARDIZE_CONTRACTS_KEEP_RUNTIMES`) finished its
evidence-only slice in mctl-design#207 / PR #208, which produced
`docs/evidence/web-contract-evidence.md`. That report found that the six public surfaces
(`mctl.ai`, `docs.mctl.ai`, `tg.mctl.ai`, `academy.mctl.ai`, `alice.mctl.ai`,
`seerrsense.mctl.ai`) use different menu mechanisms, and that every header behavior check in its
section 6 is `not-run`: no headless browser and no consumer source was available. The design system
already ships the visual half of a header in `packages/css/src/site.css` (`.mctl-site-header`,
`.mctl-site-nav`, `.mctl-site-burger`, `data-nav-open`, the 768px drawer and the 980px
`.mctl-site-header--drawer-wide` variant). The comment block above `.mctl-site-burger` states that
"the CSS owns the look only. The consumer owns the behaviour", but that behavior is described in a
code comment and the README, not in a contract that can be tested.

Issue #209 is the epic's P1 work item `web-header-a11y-contract`. It asks for exactly one
framework-neutral, versioned contract document, `docs/contracts/web-header-a11y.md`, with a
traceability appendix. The document defines observable navigation behavior and behavioral
equivalents for the six runtimes, marks the places where a runtime cannot meet the contract as
exceptions that need owner sign-off, and gives a provenance-tagged acceptance-case matrix in which
every unexecuted browser check stays `not-run`. It changes no code, CSS, tests, CI, GitOps, CSP or
production state. A shared header implementation is explicitly out of scope.

## User stories

- AS a site owner (mctl-web, mctl-docs, mctl-telegram, mctl-academy, mctl-alice, seerrsense) I WANT
  a contract that states the observable header behavior my runtime must show, in terms my framework
  can meet natively, SO THAT I can adopt it without a shared component, a shared element ID or a
  common breakpoint.
- AS a keyboard, screen-reader or reduced-motion user I WANT every public header to open, close,
  announce its state and return focus in the same way SO THAT navigation behaves the same on every
  MCTL site.
- AS an mctl-design maintainer I WANT the split between `site.css` (visuals) and consumer code
  (behavior) written down as normative requirements SO THAT CSS changes and consumer behavior can
  be reviewed against one reference.
- AS a future test author (design#14, design#34) I WANT an acceptance-case matrix with actions,
  focus expectations, viewports and selectors where known SO THAT Storybook and pinned-Playwright
  preview checks can be written later without reinterpreting the contract.
- AS the epic owner I WANT every claim provenance-tagged and every missing browser proof marked
  `not-run` SO THAT nothing unexecuted is read as a pass and the rollout gate stays a separate
  decision.

## Acceptance criteria (EARS)

Scope and change surface

- WHEN the implementing PR is opened THE SYSTEM SHALL add exactly one new file,
  `docs/contracts/web-header-a11y.md`, and change no other file in the repository.
- WHILE the contract is in its first version THE SYSTEM SHALL NOT change any file under
  `packages/`, `apps/`, `scripts/`, `.github/`, `nginx.conf`, `security-headers.conf`, `Dockerfile`
  or any `package.json`, and SHALL NOT bump the root or package version.
- THE SYSTEM SHALL keep the contract document passing the repository's existing `prettier --check .`
  run (CI `format:check`).

Contract identity

- THE SYSTEM SHALL give the contract a header that states its own contract version (`1.0.0`), its
  status (`draft, not adopted`), the mctl-design source commit it was written against (full
  40-character SHA) and the design-system version that commit carries (`0.20.2` at the time of
  investigation).
- THE SYSTEM SHALL state that the contract version is independent of the design-system lockstep
  version, and that a contract change bumps the contract version: MAJOR for a removed or tightened
  requirement or a newly mandatory behavior for an existing consumer, MINOR only for backward-compatible additions (such as optional guidance or a new consumer), PATCH for clarifications.

Normative behavior

- THE SYSTEM SHALL define the observable navigation states `desktop` (inline nav, no toggle),
  `narrow-closed` and `narrow-open`, and state that the boundary between desktop and narrow is a
  site-owned input.
- THE SYSTEM SHALL give every requirement a stable identifier (`HDR-<n>`), a single testable
  statement, and the provenance tag of the evidence it is based on.
- THE SYSTEM SHALL cover at least: toggle by pointer, Enter and Space; Tab order in each state;
  Escape dismissal; outside-pointer dismissal; close on route transition; close on viewport
  transition from narrow to desktop; focus restoration to the toggle; toggle state exposure
  (`aria-expanded` or a documented native equivalent); toggle-to-panel association
  (`aria-controls` or a documented native equivalent); visible focus indicator; accessible name of
  the toggle and of the navigation landmark; reduced-motion; and no-JS reachability of every primary
  navigation link.
- WHERE a requirement is stated in terms of an attribute THE SYSTEM SHALL also state the observable
  outcome it protects (for example "assistive technology reports expanded/collapsed"), so that a
  framework-native or CSS-only runtime can meet it with an equivalent mechanism. Mere DOM adjacency
  of a toggle and a panel SHALL NOT be claimed as a programmatic/assistive-technology association:
  a native equivalent needs source-backed semantic evidence or a separately pending exception.
- THE SYSTEM SHALL NOT require a common component, element ID, class name, state attribute or
  script for any consumer; `data-nav-open` and `.mctl-site-burger` SHALL be described as the
  `site.css` hook for consumers that opt into the shared drawer visuals, not as a mandate.

Behavioral equivalents and exceptions

- THE SYSTEM SHALL contain one behavioral-equivalent section per consumer: `mctl-web` (Nuxt/Vue),
  `mctl-docs` (VitePress DefaultTheme), `mctl-telegram` (Go server, CSS checkbox public chrome, no
  forced JS), `mctl-academy` (Vue/Hono), `mctl-alice` (local native JS) and `seerrsense` (local
  native JS).
- IF a consumer's mechanism cannot meet a requirement as stated (for example a CSS checkbox toggle
  cannot close on Escape or restore focus without JS, and a checkbox does not expose
  `aria-expanded`) THEN THE SYSTEM SHALL record it as a numbered exception (`EX-<n>`) naming the
  requirement, the gap, the user impact, the owner who must sign off, and the sign-off state
  `pending`, and SHALL NOT describe the checkbox as equivalent to a button.
- IF the mechanism of a consumer is not established from pinned source THEN THE SYSTEM SHALL say
  `unknown (not observed)` with the reason, and SHALL NOT claim `not-applicable` for that consumer.

Breakpoints

- THE SYSTEM SHALL record the narrow/desktop boundary per consumer as site-owned input: 981px
  (drawer up to 980px via `.mctl-site-header--drawer-wide`) for `mctl-academy` and `mctl-alice`,
  768px (drawer up to 767px) for `seerrsense` and for the default `site.css` drawer, and
  `unknown (not observed)` for consumers whose boundary is not established.
- THE SYSTEM SHALL NOT mandate a common breakpoint, and SHALL tag the 981px/768px consumer values
  with their source (the issue statement and, where pinned, consumer source) rather than presenting
  them as observed.

Acceptance-case matrix

- THE SYSTEM SHALL contain an acceptance-case matrix with one row per (case, consumer, route class),
  each row naming the action, the expected focus and state outcome, the selector or framework API
  where known (`unknown (not observed)` otherwise), the viewport(s) on both sides of that consumer's
  boundary, the no-JS and reduced-motion variants where applicable, the expected fail-safe behavior,
  the evidence tag and the status.
- THE SYSTEM SHALL use only the status values `observed`, `not-run`, `not-applicable` (proven absent
  in pinned source only) and `exception (EX-<n>)`, and the provenance tags `[CODE]`, `[CONFIG]`,
  `[LIVE]`, `[PREVIEW]` as defined in `docs/evidence/web-contract-evidence.md` section 1.
- WHILE no browser run has executed a case THE SYSTEM SHALL mark that case `not-run` and SHALL NOT
  use the word PASS for it.
- WHEN an implementation claim is made THE SYSTEM SHALL pin it to a full 40-character commit SHA or
  an immutable link; IF no pin is available THEN the claim SHALL be `unknown (not observed)`.

Future verification and gates

- THE SYSTEM SHALL specify how the Storybook stories in
  `apps/storybook/stories/foundations/SiteHeader.stories.ts` and the pinned Playwright runner
  (`scripts/browser-tests-docker.sh`, `apps/storybook/visual/stories.spec.ts`) and an isolated
  preview would later exercise each case (play-function interactions, both themes, axe, screenshot,
  viewport pairs, `reducedMotion: 'reduce'`, `javaScriptEnabled: false`), and SHALL state that no
  test is added by this work item.
- THE SYSTEM SHALL reference design#14 and design#34 as the owners of that test infrastructure, and
  existing trackers (telegram#599, academy#210, design#78) where relevant, rather than opening new
  issues.
- THE SYSTEM SHALL define a Preview Assurance execution gate that is separate from contract approval,
  and per-consumer adoption, rollout and rollback boundaries, each with a named owner role.

Sensitive routes and security

- THE SYSTEM SHALL classify Telegram connect/manage/OAuth-lite routes, Alice OAuth routes and
  SeerrSense consent and error routes as sensitive, and SHALL state that their header cases are
  verified only from source and isolated fixtures, never by production authentication probes.
- THE SYSTEM SHALL NOT recommend loosening any CSP, adding a remote script, or adding a shared
  header script, and SHALL state that the contract can be met inside each site's current CSP.

## Out of scope

- Any shared header implementation (for example a `site-header.js`), Vue component in `@mctlhq/ui`,
  or change to `packages/css/src/site.css`.
- Any test, story, screenshot baseline, workflow, CI step, GitOps, runtime, CSP or production change.
- Adapter or code changes in any of the six consumer repositories, and their pilot or rollout.
- Executing the browser checks; running them is the Preview Assurance gate, owned by design#14 /
  design#34 and the site owners.
- `ui.mctl.ai` as a product consumer: it is the contract's design-source and preview surface only.
- `mctl.ru`: it 301-redirects to `mctl.ai` (evidence section 4) and inherits the `mctl-web` rows.
- Approval of any exception; the contract records exceptions as `pending` for owner sign-off.

## Open questions

- Consumer source pins. The evidence run had no access to the six consumer repositories. If the
  implementer can read them, it pins claims to full SHAs; otherwise every consumer mechanism,
  selector and breakpoint stays `unknown (not observed)` and the 981px/768px values are recorded as
  stated by issue #209, not as observed. Proceeding with that rule.
- `mctl-web` and `mctl-docs` breakpoints are not stated in the issue and not in the evidence;
  recorded as `unknown (not observed)`.
- Telegram's checkbox toggle: the contract records it as an exception (EX) needing mctl-telegram
  owner sign-off, with the option of a progressive-enhancement script inside the current CSP left
  to that owner. Whether the owner accepts the exception or chooses enhancement is not decided here.
- VitePress DefaultTheme: whether its native hamburger meets Escape, outside-pointer and focus
  restoration is not established; recorded `unknown (not observed)` with a conditional exception
  that applies only if pinned source or a preview run shows the gap.
- Contract versioning: chosen as an independent contract semver (`1.0.0`) that records the
  design-system version it was written against, because the lockstep rule in `CLAUDE.md` governs
  packages and images, not documents. A reviewer may prefer to tie it to the lockstep version.
- Owner names: the contract uses owner roles (mctl-design maintainers, each site's repository
  owner, epic owner). Named individuals are not in the clone and are not invented.
