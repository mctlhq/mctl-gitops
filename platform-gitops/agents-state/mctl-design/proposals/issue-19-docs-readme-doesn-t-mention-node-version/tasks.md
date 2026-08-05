# Tasks: issue-19-docs-readme-doesn-t-mention-node-version

- [ ] 1. Add a "Requirements" callout to `README.md` immediately under the
      `## Development` heading, before the existing ```bash code block,
      stating Node 22+ and pnpm via `corepack` are required (see design.md
      for exact wording) — DoD: the callout text appears between the
      `## Development` heading line and the opening ```` ```bash ```` fence,
      mentions "Node 22" (or "22+") and "corepack", and is at most 1-2 lines
      of prose (no new `##`/`###` heading added).
- [ ] 2. Verify no contradiction with the existing "Node 22." sentence in
      the **Repository layout** section (depends on 1) — DoD: both mentions
      state the same version (22 / 22+); the Repository layout sentence is
      left unchanged unless it conflicts with the new callout's wording.
- [ ] 3. Cross-check the stated version against `package.json`
      (`engines.node`), `.nvmrc`, and the `node-version` values in
      `.github/workflows/ci.yml` and `.github/workflows/publish.yml`
      (depends on 1) — DoD: all sources agree on Node 22; no version-file
      changes are made as part of this task (doc-only proposal).

## Tests
- [ ] T1. Manual/visual review: render `README.md` (e.g. GitHub preview or
      a local Markdown viewer) and confirm the Requirements callout is
      visible immediately above the Development code block without
      scrolling past it.
- [ ] T2. Grep check: `grep -n "Node 22" README.md` returns at least two
      matches (Repository layout + new Development callout) and they do
      not conflict (no "Node 22" alongside a different number elsewhere).
- [ ] T3. Lint/format check: run whatever Markdown formatting the repo
      already uses for consistency (none is enforced by CI today per
      `ci.yml`, which runs lint/typecheck/build/build:storybook/
      check:versions on code, not docs) — DoD: no CI job fails as a result
      of this change; `pnpm check:versions` is unaffected since no
      `package.json`/version file is touched.

## Rollback
Single-file, additive Markdown change. To roll back: revert the commit
touching `README.md` (`git revert <sha>`) or manually remove the added
Requirements line under `## Development`. No data, service, deploy, or
version-file state is affected, so rollback carries no downstream risk.
