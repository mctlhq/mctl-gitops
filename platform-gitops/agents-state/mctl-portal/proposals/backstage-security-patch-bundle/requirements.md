# Patch Backstage packages for Oct–Nov 2026 CVEs

## Context
Multiple Backstage advisories were published Oct 6–26, 2026 against plugins we run: scaffolder (CVE-2026-106501 critical 9.6, CVE-2026-106504), techdocs-node (CVE-2026-106556/106558), kubernetes-backend (CVE-2026-106561), auth-node (CVE-2026-106460) and catalog (CVE-2026-115923). Backstage 1.56.3 (released 02 Nov) is a minor-line bump that should include all fixes.

The scaffolder is tied to mctl-gitops, so credential exposure there is high-impact.

## User stories
- AS a platform admin I WANT patched Backstage packages SO THAT task data, k8s secrets and sessions cannot be exposed.

## Acceptance criteria (EARS)
- WHEN the upgrade is merged THE SYSTEM SHALL run `@backstage/plugin-scaffolder-backend` >= 4.1.0 (or the fixed line matching our current major), `plugin-techdocs-node` >= 2.0.1 (or 1.15.6), `plugin-kubernetes-backend` >= 0.21.9 and the catalog backend with the 115923 fix.
- WHEN `yarn why` is run for each affected package THE SYSTEM SHALL report only fixed versions.
- WHEN the scaffolder onboarding template is run after upgrade THE SYSTEM SHALL still commit to mctl-gitops successfully.
- WHEN a user without ownership requests another user's scaffolder task THE SYSTEM SHALL NOT return internal execution data.
- IF any custom plugin fails to build against 1.56.3 THEN THE SYSTEM SHALL keep the previous release deployed and report the failure.
- WHILE the upgrade is in rollout THE SYSTEM SHALL keep Dex SSO login working.

## Out of scope
- Backstage major upgrade; TechDocs engine change; labs tenant changes.
