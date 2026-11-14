# Tasks: upgrade-pgx-5-11

- [ ] 1. Read release notes and advisories for the target version — DoD: breaking changes listed in the PR.
- [ ] 2. Bump dependency to github.com/jackc/pgx/v5 v5.11.x (depends on 1) — DoD: go.mod/go.sum updated, build green.
- [ ] 3. Fix compile or behavior regressions (depends on 2) — DoD: go test ./... passes.
- [ ] 4. Roll out to staging, then prod (depends on 3) — DoD: ArgoCD healthy, no error-rate increase.

## Tests
- [ ] T1. govulncheck shows none of the listed advisories.
- [ ] T2. pgx-critical-memory-safety-cve, pgx-upgrade-v592

## Rollback
Revert the gitops image tag in ArgoCD to the previous release.
