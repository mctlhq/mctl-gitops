# Move Argo CD to a patched release within its current minor line

## Context
The inbox lists a family of Argo CD ServerSideDiff Secret-disclosure issues: CVE-2026-45737 (fixed in 3.2.12, 3.3.10, 3.4.2), CVE-2026-42880 (CVSS 9.6, fixed in 3.3.9 and 3.2.11) and CVE-2026-43824 (disclosed May 1). All come from third-party aggregators and none has been verified against NVD or the Argo CD GHSA. The running Argo CD version is not in `context/`.

The fix is a patch bump within the current minor line, never a major or minor jump (see "What NOT to do" in `context/architecture.md`). The first step is to determine whether ServerSideDiff is enabled at all; if it is not, urgency drops and the proposal can be downgraded. Argo CD v3.6.1 (latest) is only a UI/rootpath fix and is not a reason to upgrade. Existing proposals (`argocd-serversidediff-secret-leak`, `argocd-serversidediff-secret-exposure`, `argocd-secret-leakage-patch`) overlap; the implementer must check their status and supersede or reuse them.

## User stories
- AS a platform operator I WANT Argo CD on a patched release of its current minor line SO THAT ServerSideDiff cannot disclose Secret values.
- AS a platform operator I WANT the upgrade staged and reversible SO THAT sync for all tenants is not put at risk.
- AS a security reviewer I WANT each CVE ID and fixed version verified SO THAT the target version is correct.

## Acceptance criteria (EARS)
- WHEN the proposal is started THE SYSTEM SHALL determine the running Argo CD version and whether ServerSideDiff is enabled (controller flag, `argocd-cmd-params-cm`, or per-App annotation).
- IF ServerSideDiff is not enabled anywhere THEN THE SYSTEM SHALL downgrade the priority and still record the target patch version for the next maintenance window.
- WHEN CVE-2026-45737, CVE-2026-42880 and CVE-2026-43824 are cited THE SYSTEM SHALL have first confirmed each ID and the fixed-version list against NVD and the Argo CD GHSA.
- WHEN the target version is chosen THE SYSTEM SHALL select the latest verified patch release in the same minor line as the running version (for example 3.2.x to at least 3.2.12, 3.3.x to at least 3.3.10, 3.4.x to at least 3.4.2).
- IF the running version is in a minor line with no verified fix THEN THE SYSTEM SHALL stop and raise it for an ADR instead of performing a minor or major jump.
- WHEN the upgrade is applied THE SYSTEM SHALL do it on `admins` first, with the previous image tag recorded for rollback.
- WHILE the rolling restart runs THE SYSTEM SHALL keep resource requests within the namespace quota, and the quota (including `labs` interactions) SHALL be checked before rollout.
- WHEN the upgrade completes THE SYSTEM SHALL show all Apps Synced/Healthy and no ServerSideDiff Secret values visible in diffs or logs.

## Out of scope
- Argo CD minor or major upgrades, and upgrading to v3.6.1 for its UI fixes.
- Repo-server NetworkPolicy and Kustomize changes (see `argocd-repo-server-hardening`).
- Argo Workflows and Argo Rollouts upgrades.
