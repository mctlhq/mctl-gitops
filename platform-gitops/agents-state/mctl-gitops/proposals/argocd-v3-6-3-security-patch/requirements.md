# Roll Argo CD to v3.6.3 security patch

## Context
Argo CD v3.6.3 (24 Nov) fixes 7 advisories, 4 HIGH: unauthenticated API-server crash, stored XSS via Helm chart home link, repository upsert bypassing update permissions, and ApplicationSet deletes ignoring allowed namespaces. It also includes the regexp2 fix (CVE-2026-77299) and therefore supersedes `argocd-v3-6-2-regexp2-cve-patch`. Advisory IDs and severities must be confirmed against GHSA before rollout.

Argo CD reconciles the whole platform through ApplicationSets (ADR 0001), so these flaws have platform-wide blast radius.

## User stories
- AS a platform operator I WANT Argo CD on v3.6.3 SO THAT the HIGH advisories are closed.
- AS a tenant owner (admins, labs) I WANT ApplicationSet deletes to respect allowed namespaces SO THAT tenants stay isolated.

## Acceptance criteria (EARS)
- WHEN the rollout completes THE SYSTEM SHALL run all Argo CD components at v3.6.3.
- WHEN an unauthenticated malformed request reaches argocd-server THE SYSTEM SHALL NOT crash.
- WHILE the upgrade is in progress THE SYSTEM SHALL keep all Applications Synced/Healthy or restore them within 30 minutes.
- IF the current version is below the 3.6 line THEN THE SYSTEM SHALL use the latest same-line patch from the multi-CVE proposal instead of a major jump.
- IF post-upgrade memory of Argo CD components in `labs` exceeds the pre-upgrade baseline by >10% THEN THE SYSTEM SHALL trigger rollback review.

## Out of scope
- Major Argo CD upgrades beyond the 3.6 line.
- Migration away from ArgoCD.
