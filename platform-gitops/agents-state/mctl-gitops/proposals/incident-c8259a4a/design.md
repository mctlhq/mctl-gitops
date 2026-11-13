# Design: incident-c8259a4a

## Diagnosis
The labs-mctl-telegram pod itself is healthy (Running, ready, 0 restarts) and serves real user MCP traffic successfully. The only failure in the logs is the canary CronJob: its step mcp_init gets HTTP 401 because the service rejects its bearer token as "worker token revoked" (reason=token_revoked, sub tg:8745115872). All other canary steps pass. The ArgoCD Degraded state is most likely caused by the failing canary CronJob/Job (failed Job health) in the same application, not by the main workload. No skill matched, so this was not analysed automatically. This is the same root cause as incident-b3602720 (MctlTelegramCanaryFailing).

## Proposed Fix
The canary's long-lived credential (expires 2026-11-29) was revoked server-side, so it must be replaced. This is a secret/runtime change and cannot be fixed by a values edit alone. In mctl-gitops, inspect platform-gitops/services/labs/mctl-telegram/values.yaml for the canary CronJob and the secret reference it uses for the token (do not print or commit any token value). Ensure the canary reads its token from a Vault-backed ExternalSecret and add a note/runbook line that the token must be re-minted when revoked. If the repo shows the canary token is pinned to a specific jti or a static value in values.yaml, replace it with an ExternalSecret reference. Do not modify auth, revocation or egress policy.

## Confidence: LOW
Root cause of the 401 (revoked canary token) is observed directly; that Argo Degraded stems from the canary Job is inferred, and the actual remedy (re-minting the token in Vault) is outside what a gitops PR can do. The implementer should verify before applying and, if no gitops change is applicable, record that a human must re-mint the canary token.

## Scope
Minimal. Only the canary token reference for labs/mctl-telegram.
