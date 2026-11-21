# Review external-secrets chart 2.15.0 before next bump

## Context
external-secrets helm-chart-2.15.0 was released 10 Nov. The release page lists no details. ESO syncs all Vault secrets, so bumps need a changelog review.

## User stories
- AS a platform operator I WANT a reviewed ESO upgrade path SO THAT secret sync is not disrupted.

## Acceptance criteria (EARS)
- WHEN a bump to 2.15.0 is proposed THE SYSTEM SHALL have the changelog and CRD diffs reviewed first.
- IF the review finds CRD or API changes THEN THE SYSTEM SHALL require a staged rollout.
- WHILE the bump rolls out THE SYSTEM SHALL keep the `vault-backend` ClusterSecretStore Valid and ExternalSecrets Ready.

## Out of scope
- Changing the secret backend; rotation work.
