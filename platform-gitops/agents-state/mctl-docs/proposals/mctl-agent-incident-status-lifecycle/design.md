# Design: mctl-agent-incident-status-lifecycle

## Source commits
- mctl-agent:4ab7e7d — feat(pipeline): add an escalated status so diagnosed tickets stop claiming to be analyzing
- mctl-agent:106ef91 — fix(poller): include EscalatedAfter in the resolveStale guard
- mctl-agent:60a9089 — fix(pipeline): set analyzing before publishing to mctl-api
- mctl-agent:937c7c1 — fix(pipeline): order the mctl-api syncs instead of racing them
- mctl-agent:8c4bb92 — fix(pipeline): emit fix_failed before escalating, not after
- mctl-agent:67c0cc9 — fix(pipeline): close the remaining analyzing leaks in handleHighConfidenceFix
- mctl-agent:e04153e — fix(pipeline): send mctl-api a ticket snapshot, and test escalate

## Current state of documentation
- `docs/reference/troubleshooting.md` — "Self-Healing Agent" section
  describes the PR/approval flow ("Agent not creating PRs", "Agent PR was
  not merged") but never lists incident status values.
- `docs/mcp/tools-reference.md` — "Incidents" section lists the 6 incident
  tools (`mctl_list_incidents`, `mctl_get_incident`, `mctl_incident_summary`,
  `mctl_acknowledge_incident`, `mctl_resolve_incident`,
  `mctl_trigger_incident_responder`) with one-line descriptions, but the
  status values a ticket can hold are never enumerated.
- `docs/platform/components.md` — the `mctl-agent` block says "Full
  incident lifecycle: detect, analyze, propose fix, review, verify" — this
  is a prose summary of *stages*, not a literal list of the `status` field
  values (which are `open`, `analyzing`, `escalated`, `fix_proposed`,
  `resolved`, `suppressed`, `acknowledged`).

This is a pre-existing gap (no status enum was ever documented), which the
new `escalated` value makes more consequential: `analyzing` no longer
covers "handed to a human," and a reader has no way to know that from any
current page.

## Proposed solution
Add an "Incident Status Values" subsection to
`docs/reference/troubleshooting.md`'s existing "Self-Healing Agent"
section — this is where a reader already goes when incident state is
confusing, and it keeps the addition close to the existing
"Agent PR was not merged" entry that already references
`"Show me details of incident INC-xxx"`. Include a short status table and
one sentence on the `escalated` auto-resolve default.

## Alternatives
1. **New page `docs/platform/incidents.md`.** Dropped — a single status
   table doesn't justify a new nav entry; it fits as a subsection of an
   existing, already-linked page.
2. **Put it in `docs/mcp/tools-reference.md`'s "Incidents" section
   instead.** Considered — that page is more "reference," which is
   arguably the more natural home for an enum table. Deferred in favor of
   troubleshooting.md because that's the page explicitly designed for
   "what does this state mean and what do I do about it," and it already
   has a Self-Healing Agent section to extend. Compromise: add a one-line
   cross-link from `tools-reference.md`'s Incidents section pointing to
   the new table, so both audiences find it.

## Impact
- Sidebar/nav: no change — existing page.
- Diagrams: not needed — a status table plus 2-3 sentences suffices; a
  full state-machine diagram is explicitly out of scope per
  `requirements.md`.
- Versioning: none (no versioned docs on this site).
