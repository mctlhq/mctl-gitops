# Tasks: argocd-repo-credential-rotation

- [ ] 1. Inventory credentials reachable from repo-server — DoD: list with scopes.
- [ ] 2. Downscope to read-only where possible (depends 1) — DoD: documented diff.
- [ ] 3. Rotate in Vault with overlap (depends 2) — DoD: ESO synced, Apps healthy.
- [ ] 4. Document schedule (depends 3) — DoD: runbook note.

## Tests
- [ ] T1. Repo fetch works with the new credentials.
- [ ] T2. Old credentials are rejected.

## Rollback
Restore the previous Vault secret version and force ESO refresh.
