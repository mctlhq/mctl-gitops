# Tasks: mctl-agent-argocd-skill

- [ ] 1. Read the current `docs/platform/components.md` to locate the mctl-agent
        section. — DoD: understand the exact heading/structure to patch.
- [ ] 2. Update `docs/platform/components.md` with the content from
        `proposed-content.md` (UPDATE mode — add built-in skills subsection under
        the mctl-agent block). — DoD: file updated, `vitepress build docs` is green.
- [ ] 3. Verify no sidebar or nav change is needed (`components.md` is already
        linked). — DoD: confirmed in `.vitepress/config.{js,ts}`.
- [ ] 4. Run `npm run dev` locally and open `docs/platform/components.md`. — DoD:
        the skills table renders correctly, links resolve, page layout is not broken.
- [ ] 5. Cross-link: check `docs/reference/troubleshooting.md` — if there is a
        section on ArgoCD CRD issues, add a "see also" pointer in the new subsection.
        — DoD: cross-reference in place or explicitly noted as not yet applicable.
- [ ] 6. Open a PR against `mctlhq/mctl-docs`, run codex review, merge.
        — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the updated section resolves (no 404s).
- [ ] T3. The skills table renders in a readable format (check on mobile viewport
        as well — tables can overflow on narrow screens in VitePress 1.6).

## Rollback
- Revert the `components.md` change via a PR. Low risk — one section update,
  no nav changes.
