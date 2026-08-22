# Escalate pgx/v5 upgrade to 5.9.2 — critical memory-safety CVEs + SQL injection

## Context
mctl-api v4.14.0 depends on `github.com/jackc/pgx/v5` at 5.8.x, the sole Postgres driver used for
tenant identities and audit logs. Two new critical memory-safety CVEs have been disclosed:
CVE-2026-33815 and CVE-2026-33816 (CVSS 9.8, improper array index validation / incorrect
comparison), affecting all pgx/v5 versions before 5.9.0. A third issue, CVE-2026-41889 (SQL
injection via placeholder confusion with dollar-quoted string literals under the simple protocol),
is fixed only in 5.9.2. All three affect our pinned 5.8.x.

A proposal covering the first two CVEs already exists at `proposals/pgx-upgrade-v592` from a prior
cycle but has no `.status.yaml`, i.e. it was never merged. This is not a fresh discovery — it is an
escalation: the fix is still outstanding, the severity has not decreased, and CVE-2026-41889 (SQL
injection, narrower trigger conditions but still a confidentiality/integrity risk on the audit-log
and identity tables) must be folded into the same fix rather than tracked separately, since both
land on the identical 5.9.2 target version.

## User stories
- AS a platform security engineer I WANT pgx/v5 upgraded to 5.9.2 SO THAT the CVSS 9.8
  memory-safety flaws (CVE-2026-33815, CVE-2026-33816) are eliminated from the production
  Postgres driver.
- AS a security auditor I WANT confirmation that CVE-2026-41889 (SQL injection via dollar-quoted
  placeholder confusion) does not apply, or is remediated, SO THAT the audit trail can state the
  driver layer is not a SQL-injection vector.
- AS an on-call engineer I WANT this escalated above the stalled `pgx-upgrade-v592` proposal SO
  THAT it actually merges this cycle instead of remaining open indefinitely.

## Acceptance criteria (EARS)
- WHEN mctl-api is built THE SYSTEM SHALL depend on `github.com/jackc/pgx/v5` version 5.9.2 or
  later, as verified in `go.mod`/`go.sum`.
- WHEN the CI security scan runs (`govulncheck ./...`) THE SYSTEM SHALL report zero findings for
  CVE-2026-33815, CVE-2026-33816, and CVE-2026-41889.
- IF mctl-api's Postgres connection configuration uses the simple query protocol anywhere THEN THE
  SYSTEM SHALL either confirm it does not combine this with attacker-controlled dollar-quoted
  literals, or switch the affected call-sites to the extended protocol, before the upgrade is
  considered fully remediating CVE-2026-41889.
- WHILE the service is running post-upgrade THE SYSTEM SHALL preserve existing connection-pool
  behaviour and query semantics with no regressions (verified by the existing integration test
  suite against Postgres).
- IF pgx 5.9.2 introduces any breaking API changes relative to 5.8 THEN THE SYSTEM SHALL compile
  cleanly with all call-sites updated before merge.

## Out of scope
- Upgrading to pgx v6 or switching drivers (explicitly rejected per `context/architecture.md`,
  "What NOT to do" — no ORM replacement of pgx).
- Connection-pool re-tuning (separate, unrelated concern).
- Re-opening `proposals/pgx-upgrade-v592` as a duplicate track; this proposal supersedes it in
  scope and should be merged in its place, with the older one closed as superseded.
