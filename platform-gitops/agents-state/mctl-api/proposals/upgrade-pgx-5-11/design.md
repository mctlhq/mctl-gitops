# Design: upgrade-pgx-5-11

## Current state
See context/architecture.md: mctl-api 4.14.0 on the stack listed there.

## Proposed solution
Bump the module to github.com/jackc/pgx/v5 v5.11.x via `go get`, run `go mod tidy`, fix compile or behavior changes, rebuild the image and roll out through mctl-gitops/ArgoCD (staging first).

## Alternatives
- Stay on the current version and mitigate at the ingress: partial, leaves library flaws.
- Pin an intermediate fixed release: more future churn.

## Platform impact
- Migrations: none.
- Backward compatibility: check release notes for behavior changes.
- Resource impact: negligible; no expected memory increase for labs (the service runs in admins).
- Risks: behavior changes; mitigated by tests and staged rollout.
