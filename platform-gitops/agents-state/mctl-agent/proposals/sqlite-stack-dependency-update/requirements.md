# Update modernc.org/sqlite stack (1.34 -> 1.57.0) with CVE verification

## Context
`modernc.org/sqlite` is the pure-Go (no CGO) SQLite driver backing the
tickets DB and skill-metrics store in mctl-agent, and is currently
pinned at 1.34 — 20+ minor versions behind the latest 1.57.0 release
(2026-08-19). Two CVE signals motivate this update, with different
confidence levels:

1. **modernc.org/libc CVE-2025-26519 (CVSS 8.1)** — a transitive
   dependency of modernc.org/sqlite. This is an independently sourced
   advisory (separate reporting account/mechanism from the item below)
   and justifies the update on its own merits.
2. **modernc.org/sqlite CVE-2026-50812 (SQLite Session Extension DoS)**
   — should be treated with explicit skepticism: the researcher flagged
   that 54 of 55 recent SQLite advisories from the same reporting
   GitHub account appear fabricated, and this was the sole one flagged
   as possibly real. This proposal does not treat CVE-2026-50812 as
   confirmed; it requires an independent verification step against
   sqlite.org/cves.html (or equivalent authoritative source) before it
   is cited as a driver for urgency, and the update ships regardless
   because of point 1 above.

This does not conflict with any accepted decision — `context/decisions/`
contains no ADR proposing an engine change, and `architecture.md`'s
"What NOT to do" section explicitly says not to propose switching
SQLite to Postgres. This proposal is a pure dependency version bump
with no CGO implications and does not touch the storage engine choice
itself.

## User stories
- AS the mctl-agent maintainer I WANT modernc.org/sqlite and its
  transitive modernc.org/libc dependency updated to current releases
  SO THAT the confirmed CVE-2025-26519 (libc, CVSS 8.1) is closed in
  the tickets DB and skill-metrics store code path.
- AS a security reviewer I WANT CVE-2026-50812 independently verified
  against an authoritative source before it is cited as a fixed
  vulnerability SO THAT the team does not rely on a possibly-fabricated
  advisory to justify or characterize this change.

## Acceptance criteria (EARS)
- WHEN the mctl-agent module is built THE SYSTEM SHALL use
  `modernc.org/sqlite` at version 1.57.0 (or the latest 1.5x.x patch
  available at merge time) as declared in `go.mod`.
- WHEN `go mod tidy` resolves the dependency tree THE SYSTEM SHALL pull
  a `modernc.org/libc` version newer than v1.41.0, i.e. past the
  version affected by CVE-2025-26519.
- WHEN the full tickets-DB and skill-metrics-store test suite is run
  against the upgraded driver THE SYSTEM SHALL pass with no data-layer
  regressions (read/write/migration paths behave identically).
- IF CVE-2026-50812 cannot be independently confirmed against
  sqlite.org/cves.html or another authoritative source by the time this
  proposal is implemented THEN THE SYSTEM's documentation SHALL record
  it as "unconfirmed / treated as unverified" rather than as a
  confirmed fix, and the update SHALL still proceed on the strength of
  CVE-2025-26519 alone.
- WHILE the upgrade is in review THE SYSTEM SHALL keep the tickets DB
  and skill-metrics store schema, query behavior, and file format
  unchanged — this is a driver version bump, not a schema migration.
- IF the mctl-agent codebase uses the SQLite Session Extension
  (referenced by CVE-2026-50812) THEN THE SYSTEM SHALL have that usage
  explicitly identified and documented as part of the CVE verification
  task, since exposure depends on whether that extension is actually
  exercised.

## Out of scope
- Any change to the SQLite storage engine choice (staying on SQLite,
  per architecture.md's explicit guidance not to propose Postgres).
- Any schema migration for the tickets DB or skill-metrics store.
- The Go toolchain upgrade and chi router upgrade (tracked separately).
- Enabling CGO or switching to a CGO-based SQLite driver — this
  remains a pure-Go dependency.
