# Design: pgx-chi-bumps-realip-audit

## Current state
pgx/v5 5.8 for identities and audit logs; chi 5.2.1 with httprate (context/architecture.md).

## Proposed solution
After the Go toolchain upgrade (go-toolchain-http2-dos-upgrade, since pgx 5.11 needs Go 1.25+), bump pgx and chi. Verify the DSN with the new parser in a test (backslash escaping, duplicate params, ssl alias). Audit use of middleware.RealIP: replace with a trusted-proxy-aware extractor (e.g. chi 5.5 ClientIPFromHeader with the ingress-set header) and key httprate on it. Check date/timestamp scans for behavior changes (timestamptz in time.Local).

## Alternatives
- Bump only pgx: leaves rate-limit evasion open.
- Keep RealIP and rely on ingress to overwrite XFF: fragile, unverified.

## Platform impact
- Migrations: none.
- Backward compatibility: parser and timestamp behavior changes need tests.
- Resource impact: none on `labs`.
- Risks: DSN misparse causing DB outage — mitigated by test against Vault-format DSN and canary.
