# Verify ArgoCD Deployment Is Not Exposed to CVE-2025-47933 (Critical XSS)

## Context

CVE-2025-47933 (GHSA-2hj5-g64g-fp6p) is a Critical CVSS 9.0 stored Cross-Site Scripting
vulnerability affecting ArgoCD versions v1.2.0-rc1 through v3.0.3. The vulnerability allows
an attacker to inject malicious scripts via the ArgoCD UI, potentially leading to session
hijacking, credential theft, or unauthorized cluster operations.

The platform currently runs ArgoCD v3.3.9, which falls outside the affected range. However,
no audit record exists in this repository confirming the running version, and no version-floor
constraint prevents a future accidental downgrade into the vulnerable range. A lightweight
proposal to formally verify the running version, record the evidence, and add a downgrade guard
closes this gap without any operational disruption.

## User stories

- AS a platform security engineer I WANT documented evidence that the running ArgoCD version
  is not affected by CVE-2025-47933 SO THAT I can satisfy security audit requirements without
  a manual cluster inspection.
- AS a platform engineer I WANT a version-floor guard in the ArgoCD Application manifest SO
  THAT an accidental downgrade to a vulnerable version is surfaced and blocked before it reaches
  production.

## Acceptance criteria (EARS)

- WHEN the ArgoCD server version is queried THE SYSTEM SHALL confirm the running version is
  v3.0.4 or later, confirming it is outside the CVE-2025-47933 affected range (v1.2.0-rc1
  through v3.0.3).
- WHEN a version check artifact is produced THE SYSTEM SHALL commit the artifact to
  `platform-gitops/agents-state/argocd-xss-version-verify/` as a permanent audit record.
- WHEN the ArgoCD Application manifest is updated THE SYSTEM SHALL include a version-floor
  annotation or comment that documents v3.0.4 as the minimum safe version.
- IF the queried running version is lower than v3.0.4 THEN THE SYSTEM SHALL create a
  high-priority incident record and halt further GitOps reconciliation changes until the
  version is patched.
- WHILE the version-floor annotation is present THE SYSTEM SHALL surface a clear human-readable
  comment in `platform-gitops/apps/` referencing CVE-2025-47933 and the minimum safe version.

## Out of scope

- Automated continuous CVE scanning of the ArgoCD image (addressed by a separate scanning
  pipeline proposal).
- Any change to the ArgoCD version currently deployed (v3.3.9 is safe; no upgrade or downgrade
  is needed).
- Remediation of other CVEs not related to CVE-2025-47933.
- Changes to tenant `labs` workloads or memory allocation.
