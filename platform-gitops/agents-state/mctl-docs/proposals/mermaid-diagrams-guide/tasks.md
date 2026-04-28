# Tasks: mermaid-diagrams-guide

- [ ] 1. Create `docs/reference/diagrams.md` with the content from `proposed-content.md`. —
      DoD: the file is present, `vitepress build docs` is green.
- [ ] 2. Update `.vitepress/config.{js,ts,mts}` — add a sidebar entry under "Reference":
      `{ text: 'Diagram Types', link: '/reference/diagrams' }`. —
      DoD: the page `/reference/diagrams` appears in the left nav under "Reference".
- [ ] 3. Locally verify `npm run dev` → open `/reference/diagrams` —
      DoD: all mermaid blocks render (flowchart, sequence, Wardley Map, etc.),
      beta callouts are visible, the page is readable.
- [ ] 4. Cross-link: add a link to `/reference/diagrams` from `docs/reference/faq.md`
      in the documentation-site (or contributing) section. —
      DoD: link added and resolves.
- [ ] 5. Audit existing `.md` files in `docs/` for `htmlLabels` — if found, create a separate
      fix-PR to remove them. —
      DoD: either no `htmlLabels` is found (OK) or a tracking issue/PR is created.
- [ ] 6. Open a PR in `mctlhq/mctl-docs`, codex review, merge. —
      DoD: deployed to docs.mctl.ai, `/reference/diagrams` is reachable.

## Tests

- [ ] T1. `vitepress build docs` finishes without errors or warnings.
- [ ] T2. All links in `docs/reference/diagrams.md` resolve (no 404).
- [ ] T3. Each mermaid block on the page renders correctly in a browser (flowchart, sequence,
      architecture; beta types — verify visually, they may have rendering quirks).
- [ ] T4. `grep -r "htmlLabels" docs/` returns no results in the production branch.

## Rollback

- Remove `docs/reference/diagrams.md` and drop the sidebar entry via a revert PR.
- Remove the cross-link from the FAQ.
- Low risk — only markdown + a config line.
