# Evaluate and bump anthropic-sdk-go to v2.15.0

## Context
anthropic-sdk-go v2.15.0 was released on 24 Nov with a date-time serialization fix and new APIs. The diagnose phase uses Claude, either via the SDK or direct HTTP.

## User stories
- AS an operator I WANT the SDK kept current if used SO THAT we receive fixes with low risk

## Acceptance criteria (EARS)
- WHEN go.mod references anthropic-sdk-go THE SYSTEM SHALL be upgraded to v2.15.0 and build and pass all tests.
- IF the service uses direct HTTP calls THEN THE SYSTEM SHALL keep them unchanged and this proposal is closed as no-op.
- WHEN the diagnose phase runs after upgrade THE SYSTEM SHALL produce the same results on recorded fixtures.

## Out of scope
- Switching the Anthropic API client (needs an ADR).
- Adopting new Google/compliance APIs.
