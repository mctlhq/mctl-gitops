# Tasks: issue-119-docs-observability-three-consistency-nit

- [ ] 1. Rewrite the Cardinality opener in `docs/reference/telemetry-attributes.md` so it no longer calls the three classes "dimensions" and accounts separately for the measurements / per-decision paragraph — DoD: the opener names cardinality classes; class headings and member lists are unchanged.
- [ ] 2. Extend naming rule 6 with the externally-assigned-identifier clause covering `mctl.issue.number` and `mctl.pr.number`, with its reason — DoD: rule 6 explicitly permits the `.number` leaf and names both attributes.
- [ ] 3. Write cross-repo references in full: `.github#48` -> `mctlhq/.github#48`, `mctl-agents#196` -> `mctlhq/mctl-agents#196` (Ownership prose and `mctl.execution.id` row), `#1280` -> `mctlhq/mctl-gitops#1280`, `#658` -> `mctlhq/mctl-telegram#658` — DoD: the grep in T2 returns no hits.
- [ ] 4. Regenerate `docs/public/llms-full.txt` with `bun run generate:llms` (depends on 1-3) — DoD: the generated file contains the new text and its diff touches only the same sentences.
- [ ] 5. Open a PR from a feature branch with a conventional `docs(observability):` title referencing #119 (depends on 4) — DoD: PR open, CI green.

## Tests
- [ ] T1. `bun run build` succeeds (runs the mermaid-links test, llms generation and the VitePress build).
- [ ] T2. `grep -nE '(^|[^/a-z.])(\.github|mctl-[a-z]+)#[0-9]+|[`( ]#[0-9]+' docs/reference/telemetry-attributes.md` returns no matches; every cross-repo citation has the form `mctlhq/<repo>#<n>`.
- [ ] T3. `grep -n 'classes of \*dimension\*' docs/reference/telemetry-attributes.md docs/public/llms-full.txt` returns nothing.
- [ ] T4. `grep -n 'number' docs/reference/telemetry-attributes.md` shows the rule 6 clause naming `mctl.issue.number` and `mctl.pr.number`.
- [ ] T5. Diff review: no attribute row (name, type, status, meaning) and no cardinality class membership has changed.

## Rollback
Revert the PR's merge commit (one content file plus the regenerated `llms-full.txt`) and cut a new
patch tag; the release pipeline redeploys the previous content. No data or config to restore.
