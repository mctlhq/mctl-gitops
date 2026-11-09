# Tasks: issue-209-feat-web-header-a11y-contract-six-surfac

- [ ] 1. Re-read the inputs at the current `main` commit: `packages/css/src/site.css` (header,
      burger, drawer, drawer-wide, reduced-motion blocks), `packages/css/src/global.css` focus styles,
      `apps/storybook/stories/foundations/SiteHeader.stories.ts`, `apps/storybook/visual/stories.spec.ts`,
      `scripts/browser-tests-docker.sh`, `docs/evidence/web-contract-evidence.md` sections 1, 2, 4-8,
      and `README.md` site.css section. Record the full 40-hex commit SHA and root version. If consumer
      repositories are readable, note each one's full SHA and the files that implement its header;
      otherwise record `unknown (not observed)` with the reason. — DoD: a list of pinned sources and
      line ranges to cite; no file written in the repo yet.
- [ ] 2. Create `docs/contracts/web-header-a11y.md` with the header block (contract id, contract
      version `1.0.0`, status `draft, not adopted`, design commit SHA and version, epic and work-item
      links, versioning rule, docs-only statement) and the terms/provenance section reusing the
      evidence legend plus `exception (EX-n)`. (depends on 1) — DoD: no "PASS" status defined;
      ownership split "site.css owns visuals, consumer owns behavior" stated with a `[CODE]` cite.
- [ ] 3. Write the states section and requirements HDR-1..HDR-16, each with statement, observable
      outcome, states, and optional `site.css` hook. (depends on 2) — DoD: every requirement is
      testable by one observable check; none mandates a component, ID, class, attribute or script.
- [ ] 4. In HDR-6 and the versioning section, explicitly reject DOM adjacency alone as
      programmatic/AT association; require a verified native mechanism or a pending exception.
      Treat newly mandatory behavior for existing consumers as MAJOR, not MINOR. (depends on 3)
      — DoD: semantics and compatibility-versioning caveats are explicit.
- [ ] 5. Write the breakpoints table: academy and alice 981px (drawer-wide, <= 980px), seerrsense and
      default `site.css` 768px (<= 767px), others `unknown (not observed)`, each value tagged with its
      source; state that no common breakpoint is mandated. (depends on 3) — DoD: 981px and 768px both
      present and attributed.
- [ ] 5. Write the six behavioral-equivalent subsections (mctl-web, mctl-docs, mctl-telegram,
      mctl-academy, mctl-alice, seerrsense) with mechanism, per-HDR expectation, CSP context from
      evidence section 4 and route classes. (depends on 3, 4) — DoD: every implementation claim has a
      full SHA / immutable link or `unknown (not observed)`; no `not-applicable` without source proof.
- [ ] 6. Write the exceptions register: at least EX-1 (Telegram checkbox vs HDR-5/HDR-6), EX-2
      (Telegram no-JS vs HDR-8/HDR-12), EX-3 (VitePress conditional, HDR-8/9/12), each with gap,
      impact, options, sign-off owner role and state `pending`. (depends on 5) — DoD: the checkbox is
      never described as equivalent to a button.
- [ ] 7. Write the route-class and sensitive-route section (Telegram connect/manage/OAuth lite, Alice
      OAuth, SeerrSense consent/errors: source and isolated fixtures only; no production auth probe,
      new remote script or CSP loosening). (depends on 5) — DoD: explicit prohibitions present.
- [ ] 8. Write the acceptance-case matrix (case id, HDR, consumer, route class, viewports `B-1`/`B`,
      JS on/off, reduced motion, action, expected state/focus, selector or API, fail-safe, tag,
      status). (depends on 4-7) — DoD: every consumer x HDR has a row or a stated reason; all statuses
      are `not-run`, `exception (EX-n)`, `not-applicable` (with proof) or `observed` (only where the
      existing Storybook play functions assert it).
- [ ] 9. Write the future verification plan (Storybook layer and pinned-Playwright preview layer, both
      themes, axe, screenshots, `reducedMotion: 'reduce'`, `javaScriptEnabled: false`) referencing
      design#14 and design#34, plus roles, gates G0-G3 and per-consumer rollout/rollback boundaries,
      referencing telegram#599, academy#210, design#78. (depends on 8) — DoD: states no test is added
      now; Preview Assurance (G1) is separate from contract approval (G0); no new issue opened.
- [ ] 10. Write Appendix A traceability (HDR -> source lines / evidence section / story / cases /
      exceptions / tracker). (depends on 3-9) — DoD: every HDR id and every EX id appears in the
      appendix.
- [ ] 11. Run `pnpm exec prettier --write docs/contracts/web-header-a11y.md`, then open one PR
      `docs: add web header a11y contract (#209)` touching only that file. (depends on 10) — DoD: PR
      diff is one added file; CI green.

## Tests

- [ ] T1. `pnpm format:check` passes (the new file is not prettier-ignored).
- [ ] T2. `git diff --name-only origin/main...HEAD` prints exactly `docs/contracts/web-header-a11y.md`.
- [ ] T3. `grep -nw PASS docs/contracts/web-header-a11y.md` returns only the sentence that says PASS
      is not a status (no matrix cell says PASS).
- [ ] T4. Every `HDR-` and `EX-` id defined in the body appears in Appendix A (check with
      `grep -o 'HDR-[0-9]*' | sort -u` on body vs appendix).
- [ ] T5. Every commit reference in the file is 40 lowercase hex characters or an immutable link
      (`grep -oE '\b[0-9a-f]{7,39}\b'` reviewed by hand for truncated SHAs).
- [ ] T6. The document contains the strings `981px`, `768px`, `not-run`, `[CODE]`, `[CONFIG]`,
      `[LIVE]`, `[PREVIEW]`, and a subsection for each of the six consumers.
- [ ] T7. Full CI (`ci.yml`) is green, including `check:token-version` and the browser story tests,
      which must be unchanged because no story or package changed.
- [ ] T8. The resulting contract never treats sibling DOM adjacency as proof of a programmatic
      navigation association; it requires an AT-observable native equivalent or a pending exception.

## Rollback

Revert the single docs commit (or close the PR before merge). Nothing else depends on the file:
no code, CSS, story, CI, GitOps, image or consumer references it at contract version 1.0.0, so a
revert has no runtime effect and needs no CDN purge or version change.
