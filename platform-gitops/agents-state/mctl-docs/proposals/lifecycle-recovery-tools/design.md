# Design: lifecycle-recovery-tools

## Source commits
- mctl-api:e7ce245 — feat(mcp): add lifecycle recovery tools
- mctl-api:f93d0fd — feat(api): expose lifecycle recovery transitions and conflict evidence over HTTP
- mctl-api:cacd7e3 — feat(lifecycle): add guarded operator recovery transitions to the store

## Dependency
**This proposal depends on `proposals/lifecycle-ownership/` landing first.**
That proposal creates `docs/platform/lifecycle-ownership.md` (base concept:
entity/phase/owner, the closed status vocabulary, the `503`≠`404` rule) and
the `## Lifecycle Ownership` sections of `docs/api/index.md` and
`docs/mcp/tools-reference.md`. This proposal only *adds* a "Recovery"
subsection and five more tool/endpoint entries to those same targets — it
does not re-propose the base page. `proposed-content.md` below is written
as a diff against `proposals/lifecycle-ownership/proposed-content.md`'s own
output (its Block 1 / Block 2 / Block 3), not against a live file, since
neither exists on `main` yet.

## Current state of documentation
- `docs/platform/lifecycle-ownership.md` — missing; will exist once
  `proposals/lifecycle-ownership/` lands. This proposal's content is an
  additive "## Recovery" section to be inserted before that page's existing
  "## Where to find it" section.
- `docs/api/index.md` — currently has no `## Lifecycle Ownership` section
  at all (confirmed via live fetch of `main`); it will gain one four-endpoint
  read-only section once the base proposal lands. This proposal adds five
  more endpoints (one read, four write) to that same section.
- `docs/mcp/tools-reference.md` — currently has no `## Lifecycle Ownership`
  section (confirmed via live fetch); it will gain one tool
  (`mctl_get_lifecycle_ownership`) once the base proposal lands. This
  proposal adds five more tools to that same section.
- `docs/mcp/examples.md` — currently has no lifecycle-ownership example
  (confirmed via live fetch); the base proposal adds one. This proposal
  adds a second example specific to the recovery flow.

## Proposed solution
1. **Append** a `## Recovery` subsection to `docs/platform/lifecycle-ownership.md`
   (once created), immediately before its `## Where to find it` section. It
   maps each mutating action onto the status vocabulary already defined
   earlier on that same page: `dead` → `mctl_fence_lifecycle_claim`,
   `stuck` → `mctl_request_lifecycle_handoff`, `handoff-stalled` →
   `mctl_retry_lifecycle_handoff`, any status → `mctl_request_lifecycle_reconcile`
   (no licensing condition — a reconcile request changes no ownership
   column). It states the universal precondition contract (`expected_owner_type/id`,
   `expected_epoch`, `expected_version`, optional `expected_last_seen_at`,
   all fail closed with `412` naming what moved) and that
   `mctl_inspect_lifecycle_conflict` is the required evidence step before
   any of the four mutations. It states plainly: none of the five actions
   grants GitHub merge or approval authority.
2. **Extend** the `## Lifecycle Ownership` section of `docs/api/index.md`
   with the five new endpoints (`GET .../conflict`,
   `POST .../recovery/reconcile`, `POST .../recovery/fence`,
   `POST .../recovery/handoff/request`, `POST .../recovery/handoff/retry`),
   including request body shape (shared across all four mutations:
   `kind`, `id`, `phase`, `expected_owner_type`, `expected_owner_id`,
   `expected_epoch` as an integer, `expected_version`, `reason`, optional
   `expected_last_seen_at`; handoff additionally takes `to_owner_type`/
   `to_owner_id`), and the specific meaning of `409` (owner not
   dead/stuck/stalled as required) vs. `412` (precondition mismatch) on
   this endpoint family.
3. **Extend** the `## Lifecycle Ownership` section of `docs/mcp/tools-reference.md`
   with the five new tools, their parameters, and which two require
   `confirm="yes"`.
4. **Extend** `docs/mcp/examples.md` with a second lifecycle-ownership
   example specific to the recovery flow (inspect → fence, and inspect →
   request-handoff).

## Alternatives
1. **Wait until `proposals/lifecycle-ownership/` is actually implemented
   before writing this proposal.** Rejected: the analyst explicitly ranked
   this as a distinct, already-shipped gap this cycle (5 confirmed-live MCP
   tools); waiting would push real, already-usable documentation debt to an
   indefinite future cycle. Writing this proposal now as an explicit diff
   against the other proposal's *proposed* content keeps both movable
   in either order without blocking on implementation sequencing.
2. **Give recovery its own standalone page (`docs/platform/lifecycle-recovery.md`)
   instead of a section of the base page.** Rejected: recovery is
   meaningless without the status vocabulary and entity/phase/owner model
   already defined on the base page; splitting them risks the same
   vocabulary drift the base proposal's own "Alternatives" section already
   rejected for a different split (concept vs. REST docs).

## Impact
- No `.vitepress/config.ts` sidebar change beyond what
  `proposals/lifecycle-ownership/` already adds (this is a section within
  an existing page, not a new page).
- No new mermaid diagram required; the base page's plain status-vocabulary
  table already carries the needed structure. A future sequence diagram of
  inspect → fence/handoff → complete could be a nice-to-have follow-up.
- Tool-count banners (`docs/mcp/overview.md`, `docs/mcp/tools-reference.md`,
  `docs/reference/faq.md`) need +5 for this proposal's tools, on top of the
  base proposal's +1 and `mcp-roadmap-control-plane`'s +4 — see that
  proposal's design.md Impact section for the coordination note; the same
  `<TODO: confirm final cumulative tool count with the mctl-api maintainer>`
  applies here.
- Applies to the current `main` branch of `mctl-docs`; no versioning split
  needed.
