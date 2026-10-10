# Validate labs memory effect of 2026.9.9 plugin reuse

## Context
Release 2026.9.9 says switching models reuses large running plugins instead of copying them. `labs` is close to its memory limit, so any change in either direction matters.

## User stories
- AS an operator I WANT before/after memory data for `labs` SO THAT I can gate promotion on it.

## Acceptance criteria (EARS)
- WHEN the `labs` upgrade begins THE SYSTEM SHALL record baseline memory (peak and p95 over 24h).
- WHEN `labs` has run the new version for the observation period THE SYSTEM SHALL compare memory with the baseline.
- IF memory is higher than baseline by any amount THEN THE SYSTEM SHALL block promotion and flag the proposal as risky.
- WHILE measuring THE SYSTEM SHALL NOT change resource limits.

## Out of scope
- Raising `labs` quotas.
