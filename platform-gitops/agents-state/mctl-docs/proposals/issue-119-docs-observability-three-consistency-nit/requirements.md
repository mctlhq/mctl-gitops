# Telemetry attribute catalog: three wording-consistency fixes

## Context
`mctlhq/mctl-docs#117` merged the telemetry attribute catalog
(`docs/reference/telemetry-attributes.md`). Three P3 review findings from its final
round were deferred and recorded in issue #119: (1) the Cardinality section opens with
"Three classes of *dimension*" although only the first class ("Bounded") is a grouping
dimension; (2) naming rule 6 ("Identifiers end in `id`; human-readable names end in
`name`", plus the `_id` sub-entity amendment) does not cover `mctl.issue.number` and
`mctl.pr.number`, which are identifiers ending in neither; (3) cross-repo references are
not written in full everywhere - `.github#48` is bare at the token-counter site.

The page exists to be precise, so internal contradictions in it undermine its purpose. The
fix is wording only: no attribute name, type, status or cardinality class changes.

## User stories
- AS a producer author adding an attribute I WANT rule 6 to state when an identifier may end in `number` SO THAT I have a precedent for the next externally-numbered identifier.
- AS a reader of the Cardinality section I WANT the opener to count what the section enumerates SO THAT the class labels do not contradict the class bodies.
- AS a reader outside the org's conventions I WANT every cross-repo reference written as `owner/repo#N` SO THAT each one resolves unambiguously.

## Acceptance criteria (EARS)
- WHEN a reader reads the opener of `## Cardinality` in `docs/reference/telemetry-attributes.md` THE SYSTEM SHALL describe the three classes as cardinality classes, without calling them "dimensions", and SHALL account separately for the measurements / per-decision paragraph.
- WHILE the Cardinality section lists the classes "Bounded", "Unbounded but necessary" and "Must not become attributes" THE SYSTEM SHALL keep each class's heading, membership and body text unchanged except where needed for the opener to agree.
- WHEN a reader reads naming rule 6 THE SYSTEM SHALL state that an identifier assigned by an external system may keep that system's own term, citing `mctl.issue.number` and `mctl.pr.number` (GitHub issue and pull-request numbers) as the case, with the reason that renaming to `.id` would obscure which identifier is meant.
- WHEN the page cites an issue or pull request in a repository other than `mctlhq/mctl-docs` THE SYSTEM SHALL write it as `mctlhq/<repo>#<n>`; this covers `.github#48` (Cardinality/token-counter site in the `gen_ai.*` section), `mctl-agents#196` (Ownership prose and the `mctl.execution.id` row), `#1280` (DevLoop execution trace section) and `#658` (Bounded class).
- IF an edit would change an attribute name, type, status or cardinality class THEN THE SYSTEM SHALL NOT make it.
- WHEN `docs/reference/telemetry-attributes.md` changes THE SYSTEM SHALL regenerate the tracked `docs/public/llms-full.txt` with `bun run generate:llms` so the two stay identical.
- WHEN the change is built with `bun run build` THE SYSTEM SHALL build without errors.

## Out of scope
- Any change to an attribute name, type, status or cardinality class (explicit in the issue).
- Renaming `mctl.issue.number` / `mctl.pr.number` to `.id`.
- Bare references on other pages (e.g. `mctl-api#261` in `docs/api/index.md`).
- Changes to `.vitepress/config.ts`, navigation or other pages.

## Open questions
- The issue names only `.github#48`, but its acceptance criterion says "written in full throughout". This proposal also expands `mctl-agents#196` (two sites) and the short back-references `#1280` and `#658`, which follow an earlier full mention. If the reviewer prefers to keep short back-references after a first full mention, drop those two edits; `.github#48` and `mctl-agents#196` are not back-references in that sense and should be expanded regardless.
- Exact wording of the Cardinality opener is the implementer's choice within the criteria above; a suggested text is in design.md.
