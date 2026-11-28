# Alert when the circuit breaker disables a skill

## Context
The skill circuit breaker auto-disables failing skills. ADR 0001 notes this can hide real problems and that an alert is needed. Currently no alert exists.

## User stories
- AS an operator I WANT to be notified when a skill is auto-disabled SO THAT failures do not go unnoticed

## Acceptance criteria (EARS)
- WHEN the circuit breaker disables a skill THE SYSTEM SHALL emit a Telegram notification naming the skill and failure count.
- WHILE a skill is disabled THE SYSTEM SHALL expose a gauge `mctl_agent_skill_disabled{skill}=1`.
- WHEN a skill is re-enabled THE SYSTEM SHALL reset the gauge to 0.
- IF the notification fails THEN THE SYSTEM SHALL log the error and continue.

## Out of scope
- Changing circuit breaker thresholds (needs real prod data).
