# Design: upgrade-pgx-5-11-v2

## Current state
See context/architecture.md (mctl-api 4.14.0, tenant admins). pgx/v5 5.8 with pgxpool.

## Proposed solution
Bump to v5.11.0. Audit DSN for `+` in query values, backslashes, bracketless IPv6, and timestamptz location (now time.Local or ScanLocation; set explicitly). Keep pgx, no ORM.

## Alternatives
- Bump only to 5.9.2: leaves later fixes.
- ORM: rejected by architecture notes.

## Platform impact
- Migrations: none. Compatibility: timestamptz location change, DSN parsing. Risk: time zone display drift; mitigate with explicit ScanLocation UTC.
- Resource impact: negligible; no additional memory in `labs` (mctl-api runs in `admins`).
