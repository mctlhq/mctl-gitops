# Tasks: mermaid-dep-security

- [ ] 1. Create `context/decisions/0002-mermaid-dep-security.md` from the ADR template (see `context/decisions/README.md`).
      Insert the content from `proposed-content.md` (ADR section). — DoD: the file is present, status "accepted" or "proposed".
- [ ] 2. Add a "Known dependency advisories" section to `docs/reference/troubleshooting.md`.
      Use the content from `proposed-content.md` (troubleshooting patch section). — DoD: the section appears on the page.
- [ ] 3. Check the mctl-docs `package.json` for `overrides`/`resolutions` for lodash-es.
      If absent, add `"overrides": { "lodash-es": "^4.18.1" }` as a temporary mitigation.
      — DoD: `npm audit` does not show CVE-2026-4800, CVE-2026-2950 as high/critical.
- [ ] 4. Locally verify `npm run dev` and `vitepress build docs` after the overrides — DoD: build green, mermaid renders.
- [ ] 5. Open a PR in `mctlhq/mctl-docs`, code review, merge. — DoD: deployed to docs.mctl.ai.

## Tests

- [ ] T1. `vitepress build docs` finishes without errors or warnings.
- [ ] T2. `npm audit --audit-level=high` does not show CVE-2026-4800, CVE-2026-2950 (after the overrides pin).
- [ ] T3. The page `docs/reference/troubleshooting` renders with the new section; the ADR link resolves correctly.

## Rollback

- Remove the ADR file and the section from troubleshooting.md via a revert PR.
- Drop the `overrides` from package.json if the pin causes breaking changes in mermaid.
- Low risk — markdown + package.json patch only.
