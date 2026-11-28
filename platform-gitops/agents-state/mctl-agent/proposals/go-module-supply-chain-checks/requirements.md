# Harden Go module supply chain in CI

## Context
Reports on 25 Nov describe malicious Go modules. govulncheck covers known CVEs only; it does not detect tampered or typosquatted modules.

## User stories
- AS an operator I WANT CI to verify module integrity SO THAT unexpected dependencies are caught before release

## Acceptance criteria (EARS)
- WHEN CI runs THE SYSTEM SHALL execute `go mod verify` and fail on mismatch.
- WHEN a PR changes go.mod or go.sum THE SYSTEM SHALL list added modules in the CI summary for review.
- WHILE building THE SYSTEM SHALL use `-mod=readonly`.

## Out of scope
- Vulnerability scanning (see govulncheck-ci-gate).
- Vendoring dependencies.
