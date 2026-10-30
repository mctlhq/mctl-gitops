# Design: incident-b7550bef

## Confidence: LOW

## Diagnosis
The SharedPgBackupFailed alert fired for the shared-pg CNPG cluster in the platform-db tenant. mctl-agent has no skill for this alert, so no analysis was done. No service logs were available (empty result), so the root cause is unknown. Likely candidates for a CNPG backup failure: object-store credentials or endpoint misconfiguration in the Barman/ObjectStore settings, a missing or expired backup secret, bucket permissions, or a WAL archiving problem. None of these is confirmed.

## Proposed Fix
Do not guess a value change. The implementer should inspect the shared-pg Cluster/ScheduledBackup/ObjectStore manifests in mctl-gitops (platform-db), verify the backup destination, credentials secret reference (ExternalSecret/Vault path), retention and schedule, and correct any evident misconfiguration. If nothing is evidently wrong in the manifests, make no change and report that the failure needs runtime inspection (kubectl describe backup / cluster status) by a human.

## Scope
Minimal. Only touch the single field or rule that causes this specific alert.
