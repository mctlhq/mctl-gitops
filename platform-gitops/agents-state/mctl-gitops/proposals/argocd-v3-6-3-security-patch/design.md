# Design: argocd-v3-6-3-security-patch

## Current state
Argo CD is the sync engine (`ops.mctl.ai`) driving App-of-Apps and ApplicationSets (see context/architecture.md, ADR 0001). The deployed version is not known from this run (MCP unavailable); an earlier proposal targets 3.6.2 and another a multi-CVE patch on 3.3/3.4/3.5 lines.

## Proposed solution
Bump the Argo CD image/chart tag in the bootstrap definition to v3.6.3 via a single git commit. Pre-checks: confirm the current version, apply the helm release-name audit (`argocd-helm-release-name-validation`) first, and read the 3.6.3 upgrade notes. Roll out admins first, observe, then rely on the single control plane for labs. Replaces the 3.6.2 proposal; if the cluster is on an older line, take that line's patch instead.

## Alternatives
- Stay on 3.6.2: leaves 7 advisories open. Rejected.
- Hotfix only the HIGH issues by config (disable features): partial and fragile.
- Jump to a newer minor: violates the no-major-on-patch-day rule.

## Platform impact
- Migrations: none expected besides Helm release-name validation.
- Backward compatibility: invalid/over-53-char release names fail; audit first.
- Resource impact: patch release; expect no change for `labs`, verify memory post-rollout.
- Risks: sync disruption (mitigate with git revert); unverified CVE IDs (verify against GHSA).
