# Tasks: vitepress-upgrade-strategy

- [ ] 1. Create `context/decisions/0003-vitepress-2-upgrade-strategy.md` from the ADR template.
      Content — from `proposed-content.md` (ADR section). — DoD: file is present, contains
      transition criteria and a checklist.
- [ ] 2. Update `docs/reference/faq.md` — add a Q&A section about the VitePress version.
      Content — from `proposed-content.md` (FAQ patch section). — DoD: question and answer
      are present, the link to the ADR resolves.
- [ ] 3. Locally verify `npm run dev` → open `/reference/faq` — DoD: renders, the new Q&A
      block is visible, mermaid blocks (if any) render correctly.
- [ ] 4. Cross-link: ensure `context/decisions/0001-vitepress-stack.md` references the new
      ADR 0003 as "See also". — DoD: cross-reference added.
- [ ] 5. Open a PR in `mctlhq/mctl-docs`, codex review, merge. — DoD: deployed to docs.mctl.ai.

## Tests

- [ ] T1. `vitepress build docs` finishes without errors or warnings.
- [ ] T2. The link `/reference/faq#vitepress-version` resolves (the anchor exists).
- [ ] T3. The link from the FAQ to the ADR `context/decisions/0003-…` is correct (or yields a
      clear error if the ADR is not published in public docs).

## Rollback

- Remove `context/decisions/0003-...md` and revert the FAQ changes via a revert PR.
- Remove the cross-link from ADR 0001.
- Zero risk — only markdown.
