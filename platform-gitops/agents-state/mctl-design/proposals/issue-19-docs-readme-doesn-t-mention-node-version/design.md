# Design: issue-19-docs-readme-doesn-t-mention-node-version

## Current state
Read directly from the clone:

- `README.md`, **Repository layout** section (lines ~16-24): ends with the
  sentence `Monorepo managed with **pnpm workspaces** + **Turborepo**. Node
  22.` — the only place the Node version is mentioned in prose.
- `README.md`, **Development** section (lines ~26-34): a fenced `bash` code
  block with `corepack enable`, `pnpm install`, `pnpm build`,
  `pnpm build:storybook`, `pnpm dev`, and no surrounding prose at all — no
  heading text besides `## Development`, no mention of prerequisites.
- `package.json` (root): `"engines": { "node": ">=22" }` and
  `"packageManager": "pnpm@9.12.0"` — the actual machine-enforced
  requirement and the exact pnpm version corepack will pin.
- `.nvmrc`: contains `22` — used by nvm/fnm-style version managers.
- `.github/workflows/ci.yml` line 24 and `.github/workflows/publish.yml`
  line 27: both set `node-version: 22` in `actions/setup-node`, confirming
  CI enforces the same version as `package.json`.
- No `.node-version` file exists (only `.nvmrc`).
- `CLAUDE.md` (project instructions) confirms the stack line: "pnpm
  workspaces + Turborepo monorepo, TypeScript, Node 22" and lists
  `docs:` as a valid Conventional Commit type for this kind of change.

So the requirement is real, consistently enforced (`package.json` engines,
`.nvmrc`, both CI workflows all say Node 22), and simply under-surfaced in
the README's prose — exactly what the issue describes. There is no
inconsistency to reconcile; this is a pure documentation placement/framing
problem.

## Proposed solution
Edit `README.md` only:

1. Insert a short **Requirements** callout immediately under the
   `## Development` heading, before the existing ```bash code block:

   ```markdown
   ## Development

   Requirements: Node 22+ and pnpm (enabled via `corepack`).

   ```bash
   corepack enable
   pnpm install
   pnpm build            # build all packages
   pnpm build:storybook  # build the static showcase
   pnpm dev              # run Storybook in watch mode
   ```
   ```

   A single bold-lead-in sentence (not a new heading level, not a bullet
   list) keeps it skimmable and proportionate to a one-line gap — matches
   the issue's ask for "a short Requirements note," not a new doc section.

2. Leave the existing "Node 22." mention in **Repository layout** as-is.
   It is not wrong and removing it risks an unrelated diff to a section
   the issue doesn't ask to change; the new callout is additive and takes
   priority as the thing a skimming reader actually sees.

3. No other files change. `package.json`, `.nvmrc`, CI workflows, and
   `CLAUDE.md` already state Node 22 correctly and consistently; nothing
   there needs to move in lockstep with a README wording tweak.

This directly satisfies the EARS criteria in requirements.md: the callout
sits adjacent to the install commands, states Node 22+ and corepack/pnpm,
and stays consistent with the pre-existing "Node 22." mention.

## Alternatives
1. **Replace the Repository-layout mention entirely, moving it into
   Development.** Dropped: churns an extra line in an unrelated section for
   no benefit — the issue only asks to *add* a callout near Development,
   not to relocate the existing one. Leaving both is lower risk and still
   satisfies "not mention it only once, easy to miss."
2. **Add a full "## Requirements" / "## Prerequisites" top-level section**
   (its own `##` heading, bullet list of Node/pnpm/OS, maybe editor
   recommendations). Dropped as over-scoped: the issue explicitly asks for
   a "short... note," and a new top-level section would also require
   updating the README's implicit structure/order for no real reader
   benefit on a one-fact gap.
3. **Add an `engines`-enforcement mechanism** (e.g. `.npmrc` with
   `engine-strict=true`, or a `preinstall` script that fails on wrong Node
   version) instead of / in addition to a doc change. Dropped: it's a
   behavioral/tooling change with its own blast radius (could break CI or
   contributors on slightly different patch versions) and is out of scope
   for a docs-labeled issue about README clarity; flagged in requirements.md
   as explicitly out of scope.

## Platform impact
- **Migrations**: none — plain Markdown edit to `README.md`.
- **Backward compatibility**: none — no code, API, package, or version
  changes. `pnpm check:versions` and CI are unaffected since no
  `package.json`/version files change.
- **Resource impact**: none.
- **Risks**: near-zero. The only risk is a wording drift between the new
  callout and the existing "Node 22." sentence or the actual enforced
  version (`>=22` in `package.json`); mitigated by copying the exact
  version string used in `package.json`/`.nvmrc`/CI (Node 22 / 22+) rather
  than inventing new phrasing, and by the tasks.md verification step that
  diffs the callout's stated version against those files.
- **Rollback**: trivial — revert the single-file Markdown change (see
  tasks.md).
