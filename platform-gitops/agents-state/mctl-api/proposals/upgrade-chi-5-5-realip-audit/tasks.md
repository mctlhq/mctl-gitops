# Tasks: upgrade-chi-5-5-realip-audit

- [ ] 1. Read release notes and advisories for the target version — DoD: breaking changes listed in the PR.
- [ ] 2. Bump dependency to github.com/go-chi/chi/v5 v5.5.0 (depends on 1) — DoD: go.mod/go.sum updated, build green.
- [ ] 3. Fix compile or behavior regressions (depends on 2) — DoD: go test ./... passes.
- [ ] 4. Roll out to staging, then prod (depends on 3) — DoD: ArgoCD healthy, no error-rate increase.

## Tests
- [ ] T1. govulncheck shows none of the listed advisories.
- [ ] T2. pgx-chi-bumps-realip-audit, chi-upgrade-v525

## Rollback
Revert the gitops image tag in ArgoCD to the previous release.
