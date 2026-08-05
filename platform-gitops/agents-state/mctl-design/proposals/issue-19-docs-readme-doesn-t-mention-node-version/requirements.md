# docs: add a Requirements callout near the Development section in README

## Context
`README.md` currently states the Node version requirement ("Node 22.") as a
trailing sentence at the end of the **Repository layout** section, several
lines above the **Development** section where a reader actually copies the
install commands (`corepack enable`, `pnpm install`, `pnpm build`, ...). A
reader skimming straight to the code block can easily run `pnpm install`
without realizing Node 22+ is required, and without knowing that `pnpm`
itself is expected to come from `corepack` rather than a separately
installed global.

The repo already enforces this at the tooling level — `package.json` has
`"engines": { "node": ">=22" }` and `"packageManager": "pnpm@9.12.0"`, there
is an `.nvmrc` containing `22`, and both `.github/workflows/ci.yml` and
`.github/workflows/publish.yml` pin `node-version: 22` — but none of that is
visible from the README's Development section itself. This is a
documentation-only gap: the fix is to make the existing requirement
impossible to miss, not to change what is required.

## User stories
- AS a new contributor cloning `mctl-design` for the first time, I WANT the
  Node/pnpm version requirement stated right next to the install commands,
  SO THAT I don't hit a confusing `engines` or lockfile error after already
  running `pnpm install`.
- AS a maintainer answering "why won't this build" questions, I WANT the
  README to be unambiguous about prerequisites, SO THAT I can point people
  at the doc instead of re-explaining it.

## Acceptance criteria (EARS)
- WHEN a reader views `README.md` on GitHub THE SYSTEM SHALL present a
  "Requirements" (or "Prerequisites") callout positioned immediately before
  or at the top of the **Development** section, i.e. adjacent to the
  `corepack enable` / `pnpm install` code block.
- THE SYSTEM SHALL state, within that callout, that Node 22+ is required.
- THE SYSTEM SHALL state, within that callout, that pnpm is expected to be
  enabled via `corepack` (matching the existing `corepack enable` step in
  the Development code block).
- WHILE the existing "Node 22." mention in the **Repository layout** section
  remains present, THE SYSTEM SHALL NOT contradict it (both mentions must
  agree: Node 22, or 22+, consistently).
- IF the Requirements callout duplicates version numbers that already exist
  in machine-readable form (`package.json` engines, `.nvmrc`) THEN THE
  SYSTEM SHALL keep the stated version consistent with those files (Node
  22, pnpm 9.12.0 via corepack) so the doc does not drift from the actual
  enforced versions.
- WHEN the README is rendered THE SYSTEM SHALL keep the callout short (a
  few lines: a heading or bold lead-in plus a one- or two-line list/sentence)
  so it reads as a quick note, not a new major section.

## Out of scope
- Changing the actual required Node/pnpm versions, `engines` field,
  `.nvmrc`, or CI `node-version` pins — this proposal is documentation-only.
- Adding automated enforcement (e.g. a `preinstall` engine-strict check or a
  README-linting CI step) beyond what already exists.
- Rewriting or restructuring the rest of the README beyond the Requirements
  addition and, if needed, a one-line tweak to the Repository layout mention
  to avoid duplication/contradiction.
- Adding a `.node-version` file (only `.nvmrc` exists today) or changing
  version-manager tooling.

## Open questions
- Whether to also remove/shorten the original "Node 22." sentence in
  Repository layout to avoid saying it twice, versus leaving it as a
  secondary reinforcement. Interpretation used here: leave the Repository
  layout sentence in place (it does no harm and reinforces the same fact)
  and add the new callout as the primary, skim-friendly statement near
  Development — this is the minimal, lowest-risk change and avoids
  reformatting an unrelated section.
- Whether to title the new block "Requirements" or "Prerequisites" — the
  issue title uses "Requirements"; this proposal uses "Requirements" for
  consistency with the issue.
