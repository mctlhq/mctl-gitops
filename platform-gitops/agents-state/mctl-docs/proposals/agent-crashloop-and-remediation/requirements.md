# mctl-agent crash-loop diagnosis and remediation behaviour

version-status: unverified, see commit SHA (mctl-agent 2.10.1 per release commit ab3bc31; not verified in prod)

## Context
mctl-agent gained a skill that diagnoses crash loops from pod state, with credential redaction in logs and no crash-loop classification for clean-exit containers (36ffb0d, f8308db, 291012c, 303e055, 7b675cf, 9f637f4). Rollback handling changed (2223296 and siblings 46b076b, edbbac4, e234177), scale-up now matches only on an HPA signal (b24f23a), and failed fix generation or PR-less proposals are escalated (5880140 and siblings). The builtin skill list was documented in the repo (610ba08). Docs pages on rollbacks, scaling, troubleshooting and components may describe older behaviour (not re-verified against the live tree).

## User stories
- AS a developer I WANT to know what the agent does for a crash-looping pod SO THAT I interpret its tickets.
- AS a platform admin I WANT to know rollback and scale-up rules SO THAT I predict automated actions.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/platform/components.md` THE SYSTEM SHALL list the mctl-agent builtin skills including crash-loop diagnosis `<TODO: confirm full skill list with author of 610ba08>`.
- WHEN a reader opens `docs/reference/troubleshooting.md` THE SYSTEM SHALL explain that crash-loop diagnosis reads pod state, redacts credentials in logs, and does not flag clean-exit containers.
- WHEN a reader opens `docs/guides/rollbacks.md` THE SYSTEM SHALL state that a gitops image bump counts as a deploy, the pinned digest is restored, rollback goes past every bump in the window, and it fails closed on unrecognised image history.
- WHEN a reader opens `docs/guides/scaling.md` THE SYSTEM SHALL state that automatic scale-up matches only on an HPA signal.
- WHEN a reader opens the mctl-agent block THE SYSTEM SHALL state that failed fix generation or proposals without a PR are escalated, and that poller tickets close once the app is healthy.
- IF a statement cannot be confirmed THEN THE SYSTEM SHALL carry a `<TODO: confirm with author of <sha>>` marker.

## Out of scope
- mctl-agents (R&D agents) internals, alert-rule authoring, localisation.
