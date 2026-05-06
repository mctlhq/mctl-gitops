# Document OpenClaw Agent Active-Hours Scheduling

## Context

On 2026-05-02, commit `10448a0` in `mctlhq/mctl-openclaw` fixed a meaningful
scheduling bug in the heartbeat phase-seeker: when an agent was configured with an
`active-hours` window (start/end times + timezone), the heartbeat could still fire
during quiet hours because phase slots were computed in raw UTC rather than in the
agent's configured timezone. The fix adds timezone-aware phase seeking so that
heartbeats only fire within the configured active window.

The fix was shipped in mctl-openclaw 2026.5.2-mctl.1, deployed to production on
2026-05-04 via mctl-gitops (`532bd16`). The `active-hours` feature is therefore live
and working correctly for all tenants using mctl-openclaw.

No page on `docs.mctl.ai` currently mentions the `active-hours` configuration option,
agent scheduling windows, or the interaction between `active-hours` and heartbeat
frequency. Users who want time-bounded agents (e.g. an assistant that only responds
during business hours in their timezone) have no platform documentation to guide them.

## User Stories

- AS a **tenant operator** I WANT to configure my OpenClaw agent to be active only
  during defined business hours in my timezone SO THAT the agent does not send messages
  or consume resources during nights or weekends.
- AS a **developer** integrating mctl with a customer-facing assistant I WANT to
  understand the `active-hours` config key and its effect on heartbeat scheduling
  SO THAT I can predict when the agent will and will not fire.
- AS a **platform troubleshooter** I WANT docs that explain quiet-hours behaviour
  SO THAT I can distinguish intentional scheduling silence from a broken agent.

## Acceptance Criteria (EARS)

- WHEN a user opens `docs/platform/openclaw.md` THE SYSTEM SHALL present a dedicated
  subsection describing the `active-hours` configuration option, including the timezone
  field and the start/end time format.
- WHEN a user wants to restrict their agent to business hours THE SYSTEM SHALL provide
  a concrete YAML example showing a valid `active-hours` config block with a timezone
  (e.g. `Europe/Berlin`, `Asia/Shanghai`).
- WHILE the exact config key format has not been confirmed with the feature author THE
  SYSTEM SHALL display a clear `<!-- TODO: confirm key syntax with author of 10448a0 -->`
  marker in the proposed content so a human reviewer can fill it in before merging.
- IF a user's agent appears silent during expected active hours THE SYSTEM SHALL (via
  cross-link to `docs/reference/troubleshooting.md`) point to the active-hours check as
  a diagnostic step.
- WHEN a user wants to know when heartbeats fire THE SYSTEM SHALL explain that the
  heartbeat period (e.g. `4h`) is always aligned to in-window phase slots, meaning
  quiet-hours slots are skipped rather than accumulated.

## Out of Scope

- Documenting the full heartbeat configuration API (that is broader than this commit).
- Creating a standalone `/guides/scheduling.md` page — a subsection of the existing
  `openclaw.md` page is sufficient for this change.
- Video tutorials or localisation.
- Documenting the internal `heartbeat-schedule.ts` implementation details.
