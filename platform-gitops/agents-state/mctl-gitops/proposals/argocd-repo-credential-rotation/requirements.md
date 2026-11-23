# Scope and rotate credentials reachable from the Argo CD repo-server

## Context
Two of the recent repo-server CVEs (file read via Jsonnet, command injection via SSH proxy) expose service-account tokens, deploy keys and Git/Helm/OCI credentials. Even once patched, exposure windows may have existed. IDs are unverified.

## User stories
- AS a security owner I WANT repo-server credentials least-privileged and rotated SO THAT leaked secrets have limited value.

## Acceptance criteria (EARS)
- WHEN the patch proposal is complete THE SYSTEM SHALL inventory all credentials mounted into or readable by repo-server.
- WHEN a credential grants more than read access to its repository THEN THE SYSTEM SHALL replace it with a read-only one.
- WHEN rotation occurs THE SYSTEM SHALL source new values from Vault via ExternalSecrets.
- IF no sign of compromise exists THEN THE SYSTEM SHALL still rotate `mctl-gitops-deploy-key` on a schedule.

## Out of scope
- Vault server upgrades; editing ExternalSecret paths without review.
