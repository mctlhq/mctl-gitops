# docs: link CONTRIBUTING.md and CODE_OF_CONDUCT.md from README.md

## Context
`mctl-design` ships a `CONTRIBUTING.md` and a `CODE_OF_CONDUCT.md` at the repo
root, but a full-text search of every Markdown file in the repository
(`grep -rn "CONTRIBUTING\|CODE_OF_CONDUCT" --include="*.md" .`) turns up zero
references to either filename anywhere, including in `README.md`. The
`README.md` has no "Contributing" section and no table of contents at all —
it goes straight from a title/description into a `## Packages` table. Both
governance documents are current in content (they match this repo's actual
conventions: pnpm/Turborepo workflow, conventional commits, lockstep
versioning, `security@mctl.ai` as the contact) but are effectively
undiscoverable: a visitor reading `README.md` on GitHub has no way to find
them short of browsing the repo root file listing.

This matters because `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` are the
standard entry points contributors and community members look for, and
GitHub surfaces them more prominently (e.g. in the "Community profile" and
new-issue flow) when they are cross-linked from the README. Leaving them
unlinked undermines their purpose even though the files themselves are
accurate and up to date.

## User stories
- AS a first-time contributor reading `README.md` I WANT a visible link to
  `CONTRIBUTING.md` SO THAT I know how to set up the repo and follow the
  branch/commit conventions before opening a PR.
- AS a community member evaluating whether to engage I WANT a visible link
  to `CODE_OF_CONDUCT.md` SO THAT I understand the expected standards of
  behavior.
- AS a maintainer I WANT the governance docs to stay accurate and linked SO
  THAT the project's public-facing documentation is trustworthy and does not
  silently rot.

## Acceptance criteria (EARS)
- WHEN a reader opens `README.md` THE SYSTEM SHALL present a link to
  `CONTRIBUTING.md` that is visible without scrolling past the top-level
  sections (e.g. in a "Contributing" section or an intro-level list).
- WHEN a reader opens `README.md` THE SYSTEM SHALL present a link to
  `CODE_OF_CONDUCT.md` alongside or near the `CONTRIBUTING.md` link.
- WHEN the links are added THE SYSTEM SHALL use relative Markdown links
  (`[Contributing](./CONTRIBUTING.md)`, `[Code of Conduct](./CODE_OF_CONDUCT.md)`)
  consistent with the existing `[LICENSE](./LICENSE)` link style already used
  in `README.md`.
- IF `README.md` gains a table of contents in this change THEN THE SYSTEM
  SHALL include "Contributing" and "Code of Conduct" as entries in it.
- IF no table of contents is added THEN THE SYSTEM SHALL still ensure both
  links are reachable from a short scan of `README.md` (i.e. not buried at
  the end of an unrelated paragraph).
- WHILE reviewing this change THE SYSTEM SHALL verify that the content of
  `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` is still accurate for the
  current repo state (pnpm workspaces, Turborepo, Node 22, lockstep
  versioning, conventional commits) before merely adding links to them, per
  the issue's request to confirm both are "current" as well as linked.
- WHEN this proposal is implemented THE SYSTEM SHALL NOT alter the
  substantive guidance in `CONTRIBUTING.md` or `CODE_OF_CONDUCT.md` unless an
  inaccuracy is found during the currency check.

## Out of scope
- Rewriting or restructuring the content of `CONTRIBUTING.md` or
  `CODE_OF_CONDUCT.md` beyond fixing factual inaccuracies discovered while
  verifying currency.
- Adding a full README table of contents for sections unrelated to
  Contributing/Code of Conduct (e.g. auto-generated ToC tooling) — a minimal
  ToC or a lightweight intro list is sufficient if used at all.
- Changes to `SECURITY.md`, `.github/ISSUE_TEMPLATE/*`, or
  `.github/PULL_REQUEST_TEMPLATE.md` (these are separate docs, not mentioned
  in the issue).
- Enforcing link-check automation (e.g. a CI markdown-link-checker) — the
  issue asks for a one-time pass, not an ongoing check. (See Open questions.)

## Open questions
- The issue's framing ("if it has one") already anticipates that `README.md`
  may lack a table of contents. Since it does lack one, the most reasonable
  interpretation is: add direct links in a short "Contributing" section
  rather than build out a full ToC. Proceeding on that basis.
- The issue is titled "link check" but the underlying finding is "link
  absent," not "link broken." Proceeding on the interpretation that the fix
  is to add the missing links (and confirm content currency), not to build
  tooling that checks links going forward.
- No maintainer guidance was given on exact README section placement.
  Proceeding with placing a "Contributing" section near the end of
  `README.md`, before `## License`, since that mirrors common OSS README
  ordering and keeps the existing structure intact.
