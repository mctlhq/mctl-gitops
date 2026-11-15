# Tasks: techdocs-markdown-extensions-allowlist

- [ ] 1. Inventory markdown_extensions across mkdocs.yml files — DoD: list of non-allowlisted names.
- [ ] 2. Replace or drop them (depends on 1) — DoD: docs render the same.
- [ ] 3. Bump to 1.56.5 (depends on 2, coordinate with security bundle) — DoD: TechDocs build has no allowlist warnings.

## Tests
- [ ] T1. Build TechDocs for each component; no warnings.
- [ ] T2. Config check that dangerouslyAllowAdditionalExtensions is unset.

## Rollback
Revert the change PR and redeploy the previous image tag via ArgoCD.
