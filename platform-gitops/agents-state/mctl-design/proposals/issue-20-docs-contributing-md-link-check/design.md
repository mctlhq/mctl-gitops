# Design: issue-20-docs-contributing-md-link-check

## Current state
Verified directly in the clone:

- `README.md` (repo root, 2542 bytes) contains these `##` sections in order:
  `Packages`, `Repository layout`, `Development`, `Versioning`,
  `Consuming the packages` (with `VitePress` / `Nuxt / Vue` / `Tailwind`
  sub-sections), `Components`, `License`. There is no table of contents and
  no `Contributing` or `Code of Conduct` section.
- The only outbound link in `README.md` besides the Storybook URL
  (`https://ui.mctl.ai`) is `[LICENSE](./LICENSE)` under `## License`. This
  establishes the existing convention: root-level governance docs are linked
  with a relative Markdown link, one short paragraph, near the end of the
  file.
- `CONTRIBUTING.md` (repo root, 1489 bytes) exists and its content matches
  current repo reality: it documents `corepack enable`, `pnpm install`,
  `pnpm dev` / `build` / `build:storybook` / `lint` / `typecheck` /
  `check:versions`, the `main`-is-deployable branch strategy, `feat/`/`fix/`
  branch naming, conventional commits, lockstep versioning via
  `pnpm check:versions`, and the `M`-prefixed component convention
  (`packages/ui/src/components/M<Name>.vue`, exported from
  `packages/ui/src/index.ts`, with a story under `apps/storybook/stories/`).
  Cross-checked against `package.json` scripts, `.claude/CLAUDE.md`
  ("Conventional commits", "Lockstep versioning", "Components prefixed M"),
  and `pnpm-workspace.yaml` — all consistent. No inaccuracy found.
- `CODE_OF_CONDUCT.md` (repo root, 2432 bytes) is the standard Contributor
  Covenant v2.1 text, enforcement contact `security@mctl.ai`. That address
  matches `SECURITY.md`'s reporting contact (`security@mctl.ai`), so it is
  internally consistent with the rest of the repo's documented contacts. No
  inaccuracy found.
- `grep -rn "CONTRIBUTING\|CODE_OF_CONDUCT" --include="*.md" .` across the
  whole repo returns no matches — confirmed neither file is linked from
  anywhere, not just from `README.md`.
- `.github/PULL_REQUEST_TEMPLATE.md` and `.github/ISSUE_TEMPLATE/*` also do
  not reference either file; they are out of scope per requirements but
  noted here as evidence there is no other discovery path GitHub would
  surface automatically for this repo.

## Proposed solution
Add a new `## Contributing` section to `README.md`, placed after
`## Components` and before `## License` (i.e. as the second-to-last
section), containing two short lines:

```md
## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for local setup, branch strategy,
and commit conventions. This project follows the
[Code of Conduct](./CODE_OF_CONDUCT.md).
```

This follows the exact link style already used for `[LICENSE](./LICENSE)`
(relative path, repo-root file, no `docs/` indirection) so it is consistent
with the one existing precedent in this file, and keeps the addition to the
minimum needed to make both documents discoverable — no new tooling, no
restructuring of the rest of the README.

No table of contents is added: `README.md` doesn't have one today for any
other section, and the issue's own phrasing conditions that expectation on
"if it has one." Introducing a full ToC purely to shelter two links would
be a disproportionately large change to an otherwise stable, actively
maintained file, and would need to be kept in sync with every future
section addition — an ongoing maintenance cost the issue does not ask for.

Content of `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` is left unchanged:
the currency check (see Current state) found both accurate against the
present toolchain and conventions. No edits to either file are proposed.

## Alternatives
1. **Add a full README table of contents.** Would satisfy the issue's
   conditional clause literally, but is a much larger diff touching every
   existing section, and doesn't match this README's current style (no
   other section list exists). Dropped as disproportionate to the actual
   gap (two missing links), per requirements' "Out of scope."
2. **Move the links to the top of `README.md` (above `## Packages`).**
   Considered for maximum visibility, but the sole existing precedent
   (`LICENSE`) is placed near the end of the file; moving Contributing/Code
   of Conduct to the top would break that established convention and read
   oddly ahead of the package table most readers land on the README for.
   Dropped in favor of keeping the new section adjacent to `## License`,
   preserving the file's existing structure.
3. **Add a CI markdown-link-checker (e.g. `lycheeverse/lychee-action`) to
   `ci.yml` to prevent future link rot.** Genuinely useful longer-term, but
   the issue asks for a one-time confirmation pass ("worth a quick pass"),
   not standing infrastructure, and `ci.yml` today only runs
   install/lint/typecheck/build/build:storybook/check:versions per
   `CLAUDE.md`. Dropped as out of scope for this proposal; left as a
   possible follow-up issue rather than folded in here.

## Platform impact
- **Migrations:** none — this is a documentation-only change to
  `README.md`. No package code, build output, or published artifact changes.
- **Backward compatibility:** none affected. `README.md` is not consumed
  programmatically by `pnpm check:versions`, the Storybook build, or any
  published package; only human/GitHub-rendered.
- **Resource impact:** none — no CI, build, or runtime cost changes to
  `ci.yml`, `publish.yml`, `deploy.yml`, or the Docker image build.
- **Risks:** minimal. The only risk is a broken relative link if the
  section is miskeyed; mitigated by the rollback/verification step in
  `tasks.md` (render/lint the Markdown and confirm both link targets exist
  at the repo root, which they already do).
- **Mitigations:** since `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` already
  exist at the exact paths referenced, the relative links cannot 404 as long
  as filenames are typed correctly, which is verified as part of the task.
