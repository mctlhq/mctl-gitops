# OpenClaw Privileged Commands & Diagnostics

## Context
Commit `mctl-openclaw:6ce1058` (2026-04-28, "Wire diagnostics through the core chat
command (#72936)") introduced three user-visible capabilities into the OpenClaw
multi-channel AI gateway. First, a `/diagnostics` slash command lets channel owners
trigger a local Gateway diagnostics export from inside any chat, with explicit
exec-approval gating and privacy-sensitive routing in group contexts. Second, a new
CLI subcommand `openclaw sessions export-trajectory` exports a redacted trajectory
bundle for any stored session; this is also the code path invoked by the
`/export-trajectory` slash command after owner approval. Third, approving an incoming
DM pairing code now automatically sets `commands.ownerAllowFrom` to the approving
sender when no command owner is yet configured, removing a manual config step for
first-time deployments.

None of these capabilities appear anywhere in `docs.mctl.ai`. The existing
`docs/platform/openclaw.md` page covers OpenClaw at an integration level but has no
section on owner-privileged slash commands, diagnostic workflows, or pairing-owner
bootstrap. The `docs/reference/troubleshooting.md` page has no pointer to
`/diagnostics` as a first-step debugging action. Because these features are
immediately usable by platform operators and tenant owners, the gap has direct
support-cost impact.

## User stories
- AS a tenant owner I WANT to know that `/diagnostics` exists and how to invoke it SO
  THAT I can produce a one-shot diagnostic bundle without leaving the chat where a
  problem occurred.
- AS a platform admin I WANT to understand the approval flow required before
  `/diagnostics` runs SO THAT I can brief operators on the security model before
  enabling the command.
- AS a developer debugging a session I WANT CLI syntax for
  `sessions export-trajectory` SO THAT I can export a redacted bundle without
  guessing subcommand flags.
- AS a first-time OpenClaw deployer I WANT to know that approving a pairing code
  auto-configures my owner identity SO THAT I do not need a separate config edit to
  unlock privileged commands.
- AS a support engineer I WANT a cross-reference in the Troubleshooting page pointing
  to `/diagnostics` SO THAT I can direct users to the right first step when gathering
  diagnostic information.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL present a
  "Privileged commands & diagnostics" section that describes `/diagnostics`, its
  approval flow, and its group-chat privacy routing.
- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL present the full
  CLI syntax for `openclaw sessions export-trajectory --session-key <key>` and
  describe its output (redacted trajectory bundle).
- WHEN a reader opens `docs/platform/openclaw.md` THE SYSTEM SHALL state that
  approving a DM pairing code sets `commands.ownerAllowFrom` automatically when no
  owner is configured, so that first-time setups gain an automatic owner.
- IF a reader wants to use `/diagnostics` or `sessions export-trajectory` THEN THE
  SYSTEM SHALL make clear that both require owner-level access and explicit exec
  approval before any command runs.
- WHEN a reader opens `docs/reference/troubleshooting.md` THE SYSTEM SHALL display
  a tip or callout pointing to `/diagnostics` as the recommended first step for
  gathering diagnostic information from a live channel session.
- WHILE the production deployment of commit 6ce1058 is unconfirmed THE SYSTEM SHALL
  tag the new section with a version-status notice ("version-status: unverified, see
  commit 6ce1058") so readers are aware the feature may not yet be live.

## Out of scope
- Migration guide for operators who already have `commands.ownerAllowFrom` set
  manually — the bootstrap only activates when no owner is configured, so no
  migration is needed.
- Video or screencast walkthrough of the `/diagnostics` flow.
- Localisation of the new section.
- Documentation of the internal `openclaw gateway diagnostics export` CLI beyond the
  JSON flag — that is an implementation detail of the gateway binary, not a
  user-facing doc concern.
- Any changes to `docs/security/` related to the exec-approval model — the approval
  flow is described at operational level here; a deeper threat-model writeup is out
  of scope for this proposal.
