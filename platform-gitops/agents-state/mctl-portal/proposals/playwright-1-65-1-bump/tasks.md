# Tasks: playwright-1-65-1-bump

- [ ] 1. Record currently resolved versions of the target packages from yarn.lock — DoD: versions listed in the PR description.
- [ ] 2. Apply the change described in design.md (depends on 1) — DoD: package.json/yarn.lock updated, `yarn install --immutable` passes.
- [ ] 3. Run lint, tsc, build and tests (depends on 2) — DoD: CI green.
- [ ] 4. Deploy via mctl-gitops/ArgoCD and smoke test (depends on 3) — DoD: login, catalog, scaffolder dry-run, kubernetes and observability views work.

## Tests
- [ ] T1. `yarn why` confirms the target versions only.
- [ ] T2. Playwright e2e suite passes.

## Rollback
Revert the PR and let ArgoCD redeploy the previous image.
