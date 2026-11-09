# Design: issue-209-feat-web-header-a11y-contract-six-surfac

## Current state

Investigated at mctl-design `7340576f6dccbf5da47049d64a5bef216277bb7a` (merge of PR #208), root
version `0.20.2` (`package.json`, `packages/{tokens,css,ui}/package.json`).

Header visuals in `packages/css/src/site.css` `[CODE]`:

- `.mctl-site-header`, `__inner`, `.mctl-site-nav` (lines 56-130); active item is
  `a[aria-current='page']` (line 126). The `--app` variant adds `__context`, badge and `__actions`
  slots (lines 159-226).
- Visible focus: `.mctl-site-header__context:focus-visible` and `.mctl-site-burger:focus-visible`
  (lines 199-200). Nav links have no dedicated `:focus-visible` rule in this file; they rely on the
  global focus style (to be confirmed by the implementer in `global.css` and recorded with a tag).
- Behavior split, comment above `.mctl-site-burger` (lines 228-236): "The CSS owns the look only.
  The consumer owns the behaviour: toggle data-nav-open on the header and keep aria-expanded /
  aria-controls on the burger in step; close on Escape, on a click outside the nav (the scrim is a
  ::after ...), on route change and when the viewport grows past 768px (981px with --drawer-wide);
  return focus to the burger."
- Drawer: `@media (max-width: 767px)` with `.mctl-site-header:has(.mctl-site-burger)` (line 285).
  The closed drawer is `visibility: hidden; transform: translateX(100%)` (so closed links are out of
  the Tab order), open via `[data-nav-open]`, scrim via `::after` (lines 314-350). Without `:has()`
  support the burger stays hidden and the inline nav remains (lines 280-284).
- Wide variant: `.mctl-site-header--drawer-wide` under `@media (max-width: 980px)` (lines 353-425).
- Reduced motion: `@media (prefers-reduced-motion: reduce)` removes nav and burger transitions
  (lines 427-436).

Storybook `apps/storybook/stories/foundations/SiteHeader.stories.ts` (`Foundations/Site Header`)
`[CODE]`: `ActiveItem`, `AppVariant`, `MobileDrawer` (mobile1 viewport; play clicks the burger,
asserts visibility, right-edge flush, width <= 300px, `aria-expanded="true"`), `DrawerWide`
(tablet 800px), `DefaultDrawerEndsBelow768`, `ActionsWithBurger`, `WideActionsWithBurger`,
`StaticRecipe` (named "Static HTML recipe (alice, seerrsense)": inline nav, no burger) and
`NoBurgerKeepsInlineNav`. No story drives Escape, outside click, Tab order, focus return, Enter/Space
or no-JS. The browser runner `scripts/browser-tests-docker.sh` (pinned
`mcr.microsoft.com/playwright:v1.64.1-noble`) runs `apps/storybook/visual/stories.spec.ts`, which
renders every story in dark and light, waits for the play function and compares a full-page
screenshot under `apps/storybook/visual/__screenshots__`; axe runs per `CLAUDE.md`.

Evidence `docs/evidence/web-contract-evidence.md` (the only file under `docs/` today) `[CODE]`:
section 1 defines the provenance legend reused here; section 2 has the per-site GitOps tags and
states that no consumer source was cloned; section 4 has landing-page CSPs (alice `style-src 'self'`
and `script-src-attr 'none'`; tg `default-src 'none'`, `form-action 'self'`; seerrsense no CSP
returned); section 5 says sensitive routes were not probed; section 6 lists eight header checks, all
`not-run`; section 7 maps unknowns to trackers (design#34, telegram#599, academy#210, design#78);
section 8 proposes the entry gate for this item.

`README.md` documents `site.css` and `--drawer-wide` (lines ~100-130) and still shows `0.19.0` URLs.
`.prettierignore` does not exclude `docs/`, so `format:check` covers the new file.
`check:token-version` only watches `packages/{tokens,css}/{src,scripts}` (per `CLAUDE.md`), so a
docs-only file needs no version bump.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-design/values.yaml`: `image.tag "7340576f6dcc"`, hosts
  `ui.mctl.ai`, `admins-mctl-design.mctl.ai` `[CONFIG]` (the clone HEAD).
- `services/admins/mctl-web/values.yaml`: tag `7.21.1`; host line not matched by my grep, so the
  host is not re-confirmed here (evidence section 2 names `mctl.ai` and `mctl.ru`).
- `services/admins/mctl-docs/values.yaml`: tag `0.1.66`, host `docs.mctl.ai`.
- `services/labs/mctl-telegram/values.yaml`: tag `0.137.1`, host `tg.mctl.ai`;
  `services/labs/mctl-telegram-preview/` exists (preview surface, evidence section 2).
- `services/labs/mctl-academy/values.yaml`: tag `0.1.76`, host `academy.mctl.ai`.
- `services/labs/mctl-alice/values.yaml`: tag `2.13.1`, host `alice.mctl.ai`.
- `services/labs/seerrsense/values.yaml`: tag `1.14.1`, host `seerrsense.mctl.ai`.
- All tags equal evidence section 2. No mctl MCP call, HTTP request or browser run was made in this
  investigation; nothing `[LIVE]` is newly observed. Consumer source repositories were not read: their
  header mechanisms, selectors and breakpoints remain `unknown (not observed)` (see Open questions in
  requirements.md).

## Proposed solution

Add one file, `docs/contracts/web-header-a11y.md`. No other file changes. Its structure:

1. **Header block.** Contract id `web-header-a11y`, contract version `1.0.0`, status
   `draft, not adopted`, written against mctl-design `7340576f6dccbf5da47049d64a5bef216277bb7a`
   (`0.20.2`), epic mctlhq/.github#330, work item `web-header-a11y-contract`, depends on
   `web-contract-evidence` (#207/#208). Versioning rule: independent semver (MAJOR removes or tightens
   a requirement, MINOR adds one or adds a consumer, PATCH clarifies). States plainly: docs-only, no
   application or design-system change, approval of this document authorizes nothing else.
2. **Terms and provenance.** Reuse the evidence legend verbatim by reference (`[CODE]`, `[CONFIG]`,
   `[LIVE]`, `[PREVIEW]`, `unknown (not observed)`, `not-run`, `not-applicable`); add `exception
   (EX-n)`. "PASS" is not a status in this document. Normative keywords MUST / SHOULD / MAY.
   Ownership split: `site.css` owns visuals, the consumer owns behavior.
3. **States.** `desktop` (inline nav visible, toggle absent or inert), `narrow-closed` (toggle
   visible, panel not visible and not in the Tab order or accessibility tree), `narrow-open` (panel
   visible, links reachable). The desktop/narrow boundary `B` is a per-site input.
4. **Requirements `HDR-1` .. `HDR-16`**, each with statement, observable outcome, applies-to-states,
   and the `site.css` hook if the consumer uses the shared drawer:
   - HDR-1 navigation landmark has an accessible name (`<nav aria-label>` or equivalent);
   - HDR-2 toggle is a focusable control with an accessible name;
   - HDR-3 pointer activation toggles narrow-closed/narrow-open;
   - HDR-4 Enter and Space on the focused toggle toggle the state (native `<button>` satisfies it);
   - HDR-5 toggle exposes expanded/collapsed to assistive technology (`aria-expanded`, or a
     documented native equivalent);
   - HDR-6 toggle is programmatically associated with the panel (`aria-controls` to an existing id,
     or DOM adjacency documented as the equivalent);
   - HDR-7 Tab order: narrow-closed skips panel links; narrow-open reaches toggle then panel links
     in DOM order; no focus trap while closed;
   - HDR-8 Escape in narrow-open closes and returns focus to the toggle;
   - HDR-9 pointer outside the panel (including the scrim) closes;
   - HDR-10 route transition closes the panel (client-side navigation; a full page load meets it
     trivially);
   - HDR-11 viewport growth past `B` closes and leaves no hidden open state;
   - HDR-12 after any close initiated from inside the panel or by Escape, focus is on the toggle or
     on the newly navigated page's first focus target, never lost to `body` in the old panel;
   - HDR-13 visible focus indicator on toggle and every nav link (`:focus-visible`);
   - HDR-14 active route marked with `aria-current="page"`;
   - HDR-15 under `prefers-reduced-motion: reduce` the panel opens and closes with no transition
     (`site.css` lines 427-436 give this for the shared drawer);
   - HDR-16 with JS disabled every primary navigation link is reachable at every viewport (inline
     nav, CSS-only toggle, or a no-JS fallback list), and no control is shown that does nothing.
5. **Breakpoints (site-owned input).** Table: academy and alice `B = 981px` (drawer at <= 980px,
   `.mctl-site-header--drawer-wide`); seerrsense `B = 768px`; default `site.css` `B = 768px`;
   mctl-web, mctl-docs, mctl-telegram `unknown (not observed)`. The 981px/768px consumer values are
   tagged "per issue #209" unless the implementer pins consumer source. Statement: no common
   breakpoint is mandated; test cases run at `B - 1` and `B` for each site.
6. **Behavioral equivalents, one subsection per consumer.** For each: runtime, mechanism (pinned
   source or `unknown (not observed)`), how each HDR is expected to be met, CSP context from evidence
   section 4, and the route classes. Key positions:
   - `mctl-web` (Nuxt/Vue): router `afterEach` or equivalent meets HDR-10; SSR output must keep
     HDR-16.
   - `mctl-docs` (VitePress DefaultTheme): framework-native hamburger is accepted as the mechanism;
     no class/ID/`data-nav-open` demand; conditional exception EX-3 applies only if source or preview
     shows HDR-8/9/12 gaps.
   - `mctl-telegram` (Go, CSS checkbox, no forced JS): EX-1 (HDR-5/HDR-6: a checkbox reports
     checked/unchecked, not expanded/collapsed, and a `<label>` is not a button) and EX-2
     (HDR-8/HDR-12 need JS). Both `pending` mctl-telegram owner sign-off; the owner may choose
     progressive enhancement inside the existing CSP (`script-src 'self'` already permitted) rather
     than accept. The contract does not call the checkbox equivalent to a button. telegram#599
     referenced.
   - `mctl-academy` (Vue/Hono): drawer-wide at 981px; academy#210 referenced for asset supply.
   - `mctl-alice` (local native JS): drawer-wide at 981px; CSP `style-src 'self'` and
     `script-src-attr 'none'` mean `site.css` must be vendored locally and handlers must be attached
     from a `'self'` script, not inline attributes; noted as constraints, not changes.
   - `seerrsense` (local native JS): 768px; no CSP observed on the landing page (evidence section 4,
     owner decision on adding one is outside this contract).
   - Note: the `StaticRecipe` story labelled for alice/seerrsense shows an inline nav with no burger;
     whether those sites now use the burger is `unknown (not observed)`.
7. **Exceptions register.** `EX-n`: requirement(s), consumer, gap, user impact, mitigation options,
   sign-off owner, state `pending`. Unsigned exceptions block that consumer's adoption gate, not the
   contract.
8. **Route classes and sensitive routes.** Classes: `landing`, `content` (docs/reading),
   `app-shell` (signed-in chrome where present), `sensitive` (Telegram connect/manage/OAuth lite,
   Alice OAuth, SeerrSense consent and error). Sensitive rows are verified from `[CODE]` and isolated
   `[PREVIEW]` fixtures only; no production auth probe, no new remote script, no CSP loosening.
9. **Acceptance-case matrix.** Cases `AC-<HDR>-<consumer>-<route class>` with columns: case id,
   HDR id, consumer, route class, viewport(s) (`B-1`, `B`, plus 375px), JS on/off, reduced motion,
   action, expected state/focus, selector or framework API (`unknown (not observed)` if not pinned),
   fail-safe expectation (for example "if JS fails to load, links stay reachable"), evidence tag,
   status. Every row is `not-run` or `exception (EX-n)` at version 1.0.0; `not-applicable` only with a
   pinned-source proof. Storybook rows for `Foundations/Site Header` are listed as the design-source
   reference with their status taken only from what the existing play functions assert (click opens,
   `aria-expanded="true"`), everything else `not-run`.
10. **Future verification plan (no tests added).** Layer 1, Storybook (design#34 / design#14 own the
    infrastructure): play functions for Enter/Space, Escape plus focus return, outside click, Tab
    order, viewport growth, using the existing runner in both themes with axe and screenshots; the
    stories need a reference behavior harness, which is a test-time fixture, not a shipped script.
    Layer 2, pinned-Playwright preview: same image as `scripts/browser-tests-docker.sh`, contexts at
    each site's `B-1`/`B`, `reducedMotion: 'reduce'`, `javaScriptEnabled: false`, anonymous landing and
    content routes on preview hosts (for example `tg-preview.mctl.ai`), sensitive routes only on
    isolated fixtures. Results record the run date, image and commit, and flip rows to `observed`.
11. **Roles, gates, rollout and rollback.** Roles: contract owner (mctl-design maintainers), site
    owner per consumer, epic owner (mctlhq/.github#330), test-infrastructure owners (design#14,
    design#34). Gates, independent and in order: G0 contract approval (this document, digest-bound
    owner approval); G1 Preview Assurance execution (runs Layers 1-2, no production change); G2
    per-consumer adoption (site owner, exceptions signed); G3 per-consumer release (site owner's own
    release process). Each consumer rolls out and rolls back alone: rollback is reverting that site's
    own change; the contract and `site.css` are untouched by a consumer rollback.
12. **Appendix A, traceability.** One row per HDR: source text (`site.css` line range, README,
    evidence section), Storybook story covering it today (or none), evidence check row (evidence
    section 6), acceptance cases, exceptions, tracker issue.

Why this shape: the issue asks for observable behavior that six different runtimes can meet, so
requirements are written as outcomes with the `site.css` hook as one way to satisfy them, never the
only way. Reusing the evidence legend keeps the two documents comparable, and putting every gap in
an exception register or `not-run` cell keeps approval of the text separate from proof of behavior.

## Alternatives

- **Shared header script or `MSiteHeader` component in `@mctlhq/ui`.** Gives one behavior for free,
  but the issue forbids it, it cannot serve the Go/CSS-only Telegram chrome or VitePress, and alice's
  CSP would need a vendored copy anyway. Dropped.
- **Extend the `site.css` comment block and README instead of a new document.** No stable
  requirement IDs, no matrix, no exception register, and edits under `packages/css/src` trigger
  `check:token-version` and a release. Dropped.
- **Contract mandating `.mctl-site-burger`, `data-nav-open`, `aria-controls` ids and a single 768px
  breakpoint.** Easy to test with one selector set, but it breaks the 981px drawer-wide sites, forces
  VitePress overrides and would quietly equate Telegram's checkbox with a button. Dropped in favor
  of outcome-based requirements with per-consumer equivalents.
- **Write the contract and the Storybook play-function tests together.** Faster to proof, but the
  issue limits this GO to the document and design#14/#34 own the test infrastructure. Deferred to G1.

## Platform impact

- Migrations: none. Backward compatibility: no code, CSS, package, image or URL changes; consumers
  are unaffected until each site owner adopts at G2.
- CI: `format:check` covers the new Markdown; `check:token-version`, `check:versions`,
  `check:generated` and browser tests are unaffected (no package or story change, no version bump).
  The Storybook image built from mctl-gitops is unchanged in behavior.
- Resource impact: none.
- Risks and mitigations:
  - Unverified claims read as facts: every consumer claim carries a tag or `unknown (not observed)`;
    no PASS anywhere; SHAs full 40 hex.
  - Contract read as a rollout license: header and gates section state that G0 authorizes nothing
    beyond the document.
  - Exceptions silently accepted: register entries default to `pending`, and an unsigned exception
    blocks only that consumer's G2.
  - Sensitive-route probing during later verification: section 8 forbids production auth probes and
    restricts sensitive rows to source and isolated fixtures.
  - Drift between `site.css` and the contract: the contract pins the design commit and line ranges;
    a later `site.css` change to the drawer requires a contract version bump (recorded as a rule, not
    enforced by CI in this item).
