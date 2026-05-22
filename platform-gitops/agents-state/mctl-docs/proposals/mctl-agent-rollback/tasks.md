# Tasks: mctl-agent-rollback

- [ ] 1. Update `docs/guides/rollbacks.md` by appending the new "Agent-triggered
        rollback" section from `proposed-content.md`. — DoD: file updated,
        `vitepress build docs` exits with code 0 and no warnings.

- [ ] 2. Verify `.vitepress/config.{js,ts}` — confirm `docs/guides/rollbacks.md` is
        already listed in the sidebar. If it is absent, add it under the "Guides"
        group. — DoD: the rollbacks page appears in the left navigation when running
        `npm run dev`.

- [ ] 3. Run `npm run dev` locally and open `/guides/rollbacks` in the browser.
        — DoD: the new "Agent-triggered rollback" section renders correctly; the
        mermaid diagram displays without a parse error; all anchor links (e.g.
        `#agent-triggered-rollback`) resolve to the correct heading.

- [ ] 4. Cross-link: open `docs/platform/components.md`, locate the mctl-agent
        capability block, and add the one-sentence cross-reference described in
        `design.md`. — DoD: the sentence "For automated image rollbacks, see
        [Agent-triggered rollback](/guides/rollbacks#agent-triggered-rollback)." is
        present and the anchor resolves.

- [ ] 5. Resolve the two `<TODO>` markers in `proposed-content.md` before merging:
        (a) fallback behaviour when no previous tag is found within 20 commits;
        (b) auto-merge policy for the shepherd. Confirm details with the author of
        `mctl-agent:f955a0e`. — DoD: no `<TODO>` markers remain in the final page.

- [ ] 6. Open a PR against `mctlhq/mctl-docs`, run code review, address any
        feedback, merge. — DoD: changes are deployed to docs.mctl.ai and the new
        section is visible at `https://docs.mctl.ai/guides/rollbacks`.

## Tests

- [ ] T1. `vitepress build docs` completes with no errors and no warnings (treat
        warnings as errors for this change).
- [ ] T2. Every link in the updated `docs/guides/rollbacks.md` resolves — no 404s.
        Include the new anchor `#agent-triggered-rollback` and the cross-link in
        `docs/platform/components.md`.
- [ ] T3. The mermaid block renders correctly in both `npm run dev` (hot-reload) and
        the production build (`vitepress build docs` → preview).
- [ ] T4. The "Available since mctl-agent 1.7.0" callout is present and the version
        number matches the production image referenced in `mctl-gitops@4f05252`.

## Rollback

Revert by opening a PR that removes the "Agent-triggered rollback" section from
`docs/guides/rollbacks.md` and removes the cross-reference sentence from
`docs/platform/components.md`. Low risk — markdown only, no config changes, no
database migrations.
