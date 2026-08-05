# Add a durable link between README and LICENSE

## Context
Issue #21 asks for the README to link to the repo's `LICENSE` file with a
short "License" section near the bottom, since `mctl-design` ships a license
at the root but (per the issue) does not reference it from the README.

Investigation of the current `main` branch shows this literal request is
already satisfied: `README.md` ends with a `## License` section
(`Apache-2.0 — see [LICENSE](./LICENSE).`) that links to the root-level
`LICENSE` file, and `package.json` (root and every workspace package) already
declares `"license": "Apache-2.0"` consistent with that file's content. There
is no diff needed to add the link itself.

Because the underlying request is already met, this proposal reframes the
issue as "make the README-to-LICENSE reference durable" rather than "add it
for the first time": guard against the link silently rotting (e.g. `LICENSE`
being renamed/removed, or the declared SPDX id drifting from the file's
actual license text) the same way `pnpm check:versions` already guards
lockstep versioning. This gives the Tier 2 implementer concrete, safe,
low-risk work instead of a no-op PR.

## User stories
- AS a new contributor or downstream consumer reading the README I WANT a
  working link to the LICENSE file SO THAT I can quickly confirm the terms
  under which `@mctlhq/*` packages are distributed.
- AS a maintainer I WANT the README's license link and the declared SPDX
  license id to stay consistent with the actual `LICENSE` file SO THAT a
  future rename/removal of `LICENSE` or an accidental license-field edit is
  caught in CI instead of silently shipping a broken reference.

## Acceptance criteria (EARS)
- WHEN a reader opens `README.md` THE SYSTEM SHALL present a `## License`
  section near the end of the file containing a Markdown link to the
  root-level `LICENSE` file.
- WHEN the `## License` section states a license identifier (e.g.
  `Apache-2.0`) THE SYSTEM SHALL keep that identifier consistent with the
  `license` field in the root `package.json` and with every workspace
  package's `package.json`.
- WHILE `LICENSE` exists at the repository root THE SYSTEM SHALL keep the
  README's license link pointing at `./LICENSE` (relative path, so it
  resolves both on GitHub and in any rendered copy).
- IF CI runs on a pull request THEN THE SYSTEM SHALL verify that the
  `LICENSE` file referenced by the README still exists and that the
  README's stated license id matches the root `package.json` `license`
  field, failing the build otherwise.
- IF the `LICENSE` file is ever renamed or removed THEN THE SYSTEM SHALL
  fail CI with a clear error message rather than leaving a dangling link
  undetected.

## Out of scope
- Changing the actual license terms or the Apache-2.0 choice.
- Adding a license badge/shield to the README header (not requested by the
  issue; can be a follow-up if desired).
- Per-package `LICENSE` files inside `packages/*` — the repo uses a single
  root `LICENSE` for the whole monorepo, which this proposal preserves.
- Editing `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, or `SECURITY.md` — none of
  them are in scope of the issue.

## Open questions
None — the issue is fully specified and, per its own text, is a throwaway
smoke-test issue for the dev-workflow control plane's Phase-4 E2E
verification ("safe to close/ignore"). The most reasonable interpretation,
given the literal ask is already met in the code, is to add a lightweight,
low-risk safeguard (a CI check) so the resolved state stays resolved, rather
than proposing a no-op change.
