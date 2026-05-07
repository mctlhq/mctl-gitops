# Tasks: platform-temporal

- [ ] 1. Create `docs/platform/temporal.md` with the content from
        `proposed-content.md`. — DoD: file exists, `vitepress build docs` is green.
- [ ] 2. Update `.vitepress/config.{js,ts}` — add a `{ text: 'Temporal', link: '/platform/temporal' }`
        entry in the `platform/` sidebar group. — DoD: the new page appears in the
        left navigation under "Platform".
- [ ] 3. Update `docs/platform/components.md` — add a one-line row for Temporal in
        the platform services table (service name, URL `temporal.mctl.ai`, purpose).
        — DoD: components page lists Temporal.
- [ ] 4. Run `npm run dev` locally and open `docs/platform/temporal.md`. — DoD:
        page renders, mermaid diagram displays, all links resolve.
- [ ] 5. Resolve all `<TODO: confirm ...>` markers in `proposed-content.md` with
        the author of `c2066ae` before merging. — DoD: no `<TODO>` markers remain
        in the final page.
- [ ] 6. Cross-link: add a brief mention + link to `docs/platform/overview.md`
        (the "What is MCTL?" page should list Temporal as a platform component).
        — DoD: `platform/overview.md` references `temporal.md`.
- [ ] 7. Open a PR against `mctlhq/mctl-docs`, run codex review, merge.
        — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in `docs/platform/temporal.md` resolves (no 404s).
        Specifically: external links to temporalio.io, internal links to
        `components.md` and `overview.md`.
- [ ] T3. Mermaid diagram renders in the browser (no parse errors in dev console).
- [ ] T4. The `temporal` nav entry appears in the correct position under
        "Platform" in the sidebar.

## Rollback
- Delete `docs/platform/temporal.md`, revert the sidebar config entry, and revert
  the `components.md` and `overview.md` cross-links via a single revert PR.
  Low risk — markdown + config changes only.
