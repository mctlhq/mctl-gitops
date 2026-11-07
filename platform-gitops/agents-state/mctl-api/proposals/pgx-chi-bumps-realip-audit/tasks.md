# Tasks: pgx-chi-bumps-realip-audit

- [ ] 1. Confirm go-toolchain-http2-dos-upgrade is merged — DoD: Go >= 1.25 in build.
- [ ] 2. Bump pgx to 5.11.0 and chi to 5.5.0 (depends on 1) — DoD: build and tests green.
- [ ] 3. Add DSN parsing test with production-shaped DSN (depends on 2) — DoD: effective config identical.
- [ ] 4. Audit RealIP usage and switch to trusted-header extractor for httprate keying (depends on 2) — DoD: spoofed XFF test passes.
- [ ] 5. Check timestamptz/date scans in audit-log queries (depends on 2) — DoD: no behavior diffs in tests.

## Tests
- [ ] T1. Spoofed X-Forwarded-For does not change the rate-limit bucket.
- [ ] T2. DB connect and audit-log round trip.
- [ ] T3. Error path does not leak password.

## Rollback
Revert go.mod/go.sum and the middleware change; redeploy the previous image.
