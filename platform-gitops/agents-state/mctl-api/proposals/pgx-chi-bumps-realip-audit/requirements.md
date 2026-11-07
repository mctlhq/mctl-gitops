# Bump pgx to 5.11 and chi to 5.5; audit RealIP and rate-limit keying

## Context
We use pgx 5.8 and chi 5.2.1. pgx 5.11 rejects NUL bytes in startup parameters (parameter injection), redacts passwords in connection-string errors and hardens decoders; a memory-safety vuln in pgx/v5 is also listed (ID unconfirmed). It rewrites the connection-string parser and requires Go 1.25+. chi 5.5 has middleware fixes; reports exist of middleware.RealIP X-Forwarded-For spoofing, which could defeat httprate per-IP limits.

## User stories
- AS a platform operator I WANT patched DB and router libraries SO THAT known memory-safety and injection issues are closed.
- AS a security reviewer I WANT client IP derived only from trusted proxy headers SO THAT rate limits cannot be evaded.

## Acceptance criteria (EARS)
- WHEN the service is built THE SYSTEM SHALL use pgx/v5 v5.11.0 or later and chi/v5 v5.5.0 or later.
- WHEN the Postgres DSN from Vault is parsed THE SYSTEM SHALL connect with identical effective settings as before.
- WHEN a request carries a spoofed X-Forwarded-For header from an untrusted peer THE SYSTEM SHALL NOT use it as the rate-limit key.
- IF a DB error contains the connection string THEN THE SYSTEM SHALL NOT log the password.

## Out of scope
- Connection pool tuning; ORM adoption (rejected in architecture notes).
