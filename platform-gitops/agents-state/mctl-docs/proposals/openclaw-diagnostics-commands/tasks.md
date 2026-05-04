# Tasks: openclaw-diagnostics-commands

- [ ] 1. Update `docs/platform/openclaw.md` — append the new H2 section
         "Privileged commands & diagnostics" using the ready patch in
         `proposed-content.md`.
         DoD: file saved, `vitepress build docs` exits 0, section appears in the
         rendered page.

- [ ] 2. Update `docs/reference/troubleshooting.md` — insert the `::: tip` callout
         pointing to `/diagnostics` in the appropriate "gathering diagnostic info"
         area, using the ready patch in `proposed-content.md`.
         DoD: file saved, build is green, tip appears in the rendered Troubleshooting
         page.

- [ ] 3. No `.vitepress/config` change needed. Both edited pages are already in the
         sidebar. Verify that the sidebar entries still resolve after the edits.
         DoD: `vitepress build docs` produces no broken-anchor warnings for either
         page.

- [ ] 4. Cross-link audit — check `docs/platform/openclaw.md` for any existing
         "see also" block and confirm it does not need updating. Check
         `docs/getting-started/index.md` to see whether it mentions pairing; if so,
         add a sentence pointing to the new bootstrap note.
         DoD: at most one cross-reference added where appropriate; no orphan mentions.

- [ ] 5. Open a PR against `mctlhq/mctl-docs`, apply codex review, merge.
         DoD: changes deployed to `docs.mctl.ai` via ArgoCD sync.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings (exit code 0).
- [ ] T2. Every link in the changed sections resolves — in particular the
          root-relative cross-link `/platform/openclaw` inside troubleshooting.md
          must not 404.
- [ ] T3. The CLI code block
          `openclaw sessions export-trajectory --session-key <key>` is rendered
          correctly (bash syntax highlight, no escaping artefacts).
- [ ] T4. The version-status callout is visible in both the new section and the
          troubleshooting tip.
- [ ] T5. Run `npm run dev` locally; open both changed pages; confirm the `::: tip`
          callout renders as a VitePress tip box (not as raw markdown).

## Rollback

Revert the two file changes via a follow-up PR. Risk is low — both changes are
additive markdown edits to existing pages; no config files are modified. A revert PR
restores the previous state of `docs/platform/openclaw.md` and
`docs/reference/troubleshooting.md` without side effects.
