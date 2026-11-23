# Automate dependency update PRs with grouping

## Context
Go module versions are bumped manually, producing repeated bump proposals (chi, go-github, sqlite, anthropic SDK). go-github is at v68 while v93 exists; chi at 5.2.1 vs 5.5.0.

## User stories
- AS a maintainer I WANT automatic grouped update PRs SO THAT dependencies stay current with little toil.

## Acceptance criteria (EARS)
- WHEN a new minor or patch release of a Go module is published THE SYSTEM SHALL open a grouped update PR within one week.
- WHEN a major version update is available THE SYSTEM SHALL open a separate, labelled PR that is never auto-merged.
- WHEN an update PR fails CI THE SYSTEM SHALL leave it open and not merge it.
- IF a security update is available THEN THE SYSTEM SHALL open it immediately, outside the weekly grouping.

## Out of scope
- Auto-merging; GitHub Actions or Docker base image updates beyond the Go modules (may follow later).
