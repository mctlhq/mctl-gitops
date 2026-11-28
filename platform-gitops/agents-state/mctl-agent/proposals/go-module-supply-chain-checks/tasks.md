# Tasks: go-module-supply-chain-checks

- [ ] 1. Add `go mod verify` step — DoD: CI fails on tampered cache.
- [ ] 2. Enforce -mod=readonly (depends on 1) — DoD: build passes.
- [ ] 3. Add go.mod diff summary on PRs — DoD: summary appears.

## Tests
Reports on 25 Nov describe malicious Go modules. govulncheck covers known CVEs only; it does not detect tampered or typosquatted modules.0

## Rollback
Revert the change; no data migration is involved.
