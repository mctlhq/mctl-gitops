# Design: incident-b3602720

## Diagnosis
The alert MctlTelegramCanaryFailing is driven by metrics the labs/mctl-telegram canary CronJob pushes to prometheus-pushgateway. The pushgateway is working (metrics pushed OK). The canary fails at step mcp_init with HTTP 401 because the service rejects its token: "worker token revoked" (reason=token_revoked, sub tg:8745115872). All other steps pass and real user traffic is healthy, so the service is up; only the canary's credential is bad. No skill matched. Same root cause as incident-c8259a4a.

## Proposed Fix
Replace the revoked canary credential. In mctl-gitops, inspect platform-gitops/services/labs/mctl-telegram/values.yaml for the canary CronJob and its token secret reference (never print or commit token values). If the token is sourced from Vault through an ExternalSecret, the fix is a human re-mint of the token for the canary Telegram user; if it is hardcoded in values, move it to an ExternalSecret reference. Do not change the alert rule threshold to silence it, and do not change auth or revocation behavior.

## Confidence: LOW
The 401 cause is directly observed; whether a gitops change can resolve it is uncertain because the credential lives in Vault. The implementer should verify and, if nothing applies, document that a human must re-mint the canary token.

## Scope
Minimal. Only the canary token reference for labs/mctl-telegram.
