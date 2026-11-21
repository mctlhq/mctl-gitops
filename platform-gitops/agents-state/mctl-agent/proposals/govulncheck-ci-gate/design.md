# Design: govulncheck-ci-gate

## Current state
No automated vulnerability gate; bumps are manual (see context/architecture.md, Go 1.24 stack).

## Proposed solution
Add a CI job (GitHub Actions) installing a pinned `govulncheck` version and running `govulncheck ./...` on PRs, plus a weekly cron workflow on main. Findings on cron open a labelled GitHub issue. Exclusions live in `.govulncheck-ignore.md` with an expiry date and reviewer.

## Alternatives
- Trivy/Grype only: not reachability-aware, noisier.
- Per-bump manual govulncheck: status quo, inconsistent.

## Platform impact
- Migrations: none. Backward compatibility: may block PRs until existing findings are fixed.
- Resource impact: CI only, no runtime change; no effect on `labs`.
- Risks: initial red builds; mitigated by the exclusion list.
