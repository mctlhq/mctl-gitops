# Design: argocd-repo-credential-rotation

## Current state
Secrets come from Vault via ExternalSecrets (`vault-backend`); the deploy key is `mctl-gitops-deploy-key`.

## Proposed solution
Inventory, reduce to read-only scopes, rotate in Vault, let ESO refresh, restart repo-server. Depends on the patch proposal landing first.

## Alternatives
- Rotate only on confirmed compromise: rejected, detection is weak.
- Move to GitHub App tokens only: larger change, later.

## Platform impact
- Migrations: brief auth failures if rotation is mis-sequenced; rotate with overlap.
- Resources: none; no labs impact.
- Risks: typo in Vault path locks out sync; mitigate by staging a test repo first.
