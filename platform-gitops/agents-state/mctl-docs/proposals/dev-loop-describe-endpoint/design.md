# Design: dev-loop-describe-endpoint

## Source commits

- `mctl-api:d6aca27` — feat(dev-loop): describe endpoint for workflow liveness

## Current state of documentation

- **Existing page:** `docs/api/index.md` — "REST API"
  - Documents the platform's REST API surface but does not mention any DevLoop
    endpoints at all. This is a gap, not stale content: the endpoint is new and the
    page has never covered this area.

## Proposed solution

Add a small "DevLoop" subsection (or a single entry if the page is organized as a flat
table) to `docs/api/index.md` documenting the new `describe` endpoint:

- HTTP method and path — `<TODO: confirm with author of d6aca27>`.
- Purpose — reports whether a DevLoop workflow execution is still alive.
- Response shape — `<TODO: confirm with author of d6aca27>` (likely a boolean liveness
  flag plus a workflow/run identifier, but not confirmed from source in this pass).
- Auth — admin-only, consistent with the rest of the DevLoop admin surface
  (`mctl-agents-approve`, `mctl_approve_dev_loop`) covered in the
  `platform-operations-approval-flow` proposal.
- A `curl` example.

No new page or sidebar entry is needed — this is a single-entry addition to an existing
reference page.

## Alternatives

1. **Fold this into `platform-operations-approval-flow`'s `docs/reference/operations.md`
   page** instead of `docs/api/index.md`. Dropped: the `describe` endpoint is a REST
   endpoint, not a platform operation in the `mctl_list_operations` catalog sense —
   it belongs with the rest of the REST API surface in `docs/api/index.md`. It is,
   however, cross-linked from the "Approving agent proposals" section proposed in
   `platform-operations-approval-flow`, since checking liveness is part of the decision
   guide for which approval path to use.

2. **Skip documenting until the endpoint's exact contract can be confirmed from
   source.** Dropped: per the "gap, not stale" analysis, docs/api/index.md is already
   silently missing the entire DevLoop area, and a `<TODO: confirm with author>`-marked
   stub entry is more useful to a reader (it tells them the endpoint exists and where to
   look) than no entry at all, provided the TODO markers are resolved before merge.

## Impact

- **Sidebar / nav config:** no change required — `docs/api/index.md` already exists in
  the sidebar.
- **Diagrams (mermaid):** not required for a single endpoint entry.
- **Documentation versioning:** applies to mctl-api 4.37.0 and later (commit `d6aca27`,
  shipped 2026-08-29, same release window as the `platform-operations-approval-flow`
  commits).
