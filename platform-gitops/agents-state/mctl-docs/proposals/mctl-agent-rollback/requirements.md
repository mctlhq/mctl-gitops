# Agent-Triggered Automatic Rollback

## Context
Prior to mctl-agent 1.7.0, the `rollback_image` fix type was a stub that returned
"image rollback requires previous tag — not yet implemented" for every incident it
matched. Operators who triggered a rollback through the agent received no action;
the previous image tag had to be located and applied manually via the mctl CLI or a
direct GitOps PR.

Commit `mctl-agent:f955a0e` (2026-05-02) replaced the stub with a working
implementation: the agent now walks up to 20 commits of the relevant GitOps values
file history via the GitHub API, extracts the most-recent prior image tag, and opens
a PR that flips the tag back — all without operator intervention. A series of follow-up
fixes (`a8e00cf`, `73ef4e5`, `2b6d314`, `60d364b`, `2395f74`, `9fb40c1`, 2026-05-02
to 2026-05-03) hardened the YAML parser to handle indented `image:` blocks, inline
comments, chart-level scoping, and non-404 GitHub API error propagation. Version 1.7.0
was confirmed in production via `mctl-gitops:4f05252` / `d906880` on 2026-05-03.
The current `docs/guides/rollbacks.md` page covers only user-initiated rollbacks
(mctl CLI and manual GitOps PRs) and must be extended to describe the automated path.

## User stories
- AS a platform operator I WANT to know that mctl-agent can automatically roll back a
  broken deployment SO THAT I understand I only need to review and merge an
  automatically opened PR rather than diagnose the previous tag myself.
- AS a developer whose service has just crashed in production I WANT to understand how
  the agent decides what tag to roll back to SO THAT I can trust the automated PR
  without manually verifying the GitOps history.
- AS a new tenant onboarding to the platform I WANT a single page that covers all
  rollback paths (manual and automated) SO THAT I do not miss that there is an
  automated safety net.
- AS a platform admin I WANT to know what YAML shapes the agent's parser handles SO
  THAT I can write values files that are compatible with automatic rollback.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/guides/rollbacks.md` THE SYSTEM SHALL show a dedicated
  section titled "Agent-triggered rollback" that explains the end-to-end automated
  flow introduced in mctl-agent 1.7.0.
- WHEN a reader opens `docs/guides/rollbacks.md` THE SYSTEM SHALL show a mermaid
  sequence or flow diagram illustrating: alert fires → agent detects `rollback_image`
  fix type → agent queries GitOps commit history → PR opened → operator review /
  auto-merge.
- WHEN a reader opens `docs/guides/rollbacks.md` THE SYSTEM SHALL state that the agent
  searches up to 20 commits of the values file history to locate the previous tag.
- WHEN a reader opens `docs/guides/rollbacks.md` THE SYSTEM SHALL state which mctl-agent
  version (1.7.0) introduced the feature and note that it is the current production
  version as of 2026-05-03.
- IF a reader wants to understand what YAML `image:` shapes the parser supports THEN
  THE SYSTEM SHALL list the supported patterns (indented blocks, inline comments,
  chart-level scoping).
- IF a reader wants to understand what happens when no previous tag is found within 20
  commits THEN THE SYSTEM SHALL describe the fallback behaviour.
  (`<TODO: confirm with author of f955a0e>`)
- WHILE automatic rollback is triggered THE SYSTEM SHALL make clear that a PR is opened
  for human review and that the shepherd may auto-merge it — operators are not bypassed.
- WHEN a reader opens `docs/platform/components.md` THE SYSTEM SHALL contain a
  cross-reference to the "Agent-triggered rollback" section of `docs/guides/rollbacks.md`.

## Out of scope
- Migration guide for operators who wrote custom tooling around the old stub behaviour.
- Documentation of the AlertManager → mctl-agent webhook configuration (covered, or
  to be covered, in `docs/platform/components.md` and `docs/reference/troubleshooting.md`).
- Video tutorial or interactive walkthrough.
- Localisation / translations of the new section.
- Documenting the internal Go implementation details of `internal/fixer/previous_tag.go`.
- Documentation of the mctl CLI rollback command (already covered in the existing
  `docs/guides/rollbacks.md` sections).
