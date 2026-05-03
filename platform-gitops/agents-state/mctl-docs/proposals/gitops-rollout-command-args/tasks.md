# Tasks: gitops-rollout-command-args

- [ ] 1. Open `docs/guides/gitops-workflows.md` and append (or insert before the
        "CI/CD Integration" section) the "Overriding Container Command and Arguments"
        subsection from `proposed-content.md`.
        — DoD: file saved, content appears in the correct position, no broken markdown.

- [ ] 2. Check `docs/guides/services.md` — if it already has a "Helm values" or
        "Container configuration" section, move the new content there and replace the
        `gitops-workflows.md` addition with a one-line cross-link instead.
        — DoD: content lives in exactly one page; a cross-link exists if it was moved.

- [ ] 3. Run `npm run dev` locally and open the affected page(s).
        — DoD: page renders without errors, code block is syntax-highlighted, VitePress
        warning callout (`::: warning`) renders correctly.

- [ ] 4. Cross-link check: open `docs/reference/troubleshooting.md` and add a bullet
        under a relevant section (e.g. "Service starts with unexpected command") that
        references `command` / `args` values and the rollout parity fix.
        — DoD: cross-reference in place; no orphan link.

- [ ] 5. Open a PR against `mctlhq/mctl-docs`, run codex review, merge.
        — DoD: change deployed to docs.mctl.ai.

## Tests

- [ ] T1. `vitepress build docs` completes with no errors and no warnings.
- [ ] T2. Every link on the changed page resolves (no 404s); in particular the
        cross-link to `docs/reference/troubleshooting.md` (if added) must resolve.
- [ ] T3. The YAML code block in the example has been hand-checked: field names match
        the actual base-service `values.yaml` schema (`command`, `args` as YAML lists).

## Rollback

Delete the added subsection via a revert PR. No schema or config changes — markdown only.
