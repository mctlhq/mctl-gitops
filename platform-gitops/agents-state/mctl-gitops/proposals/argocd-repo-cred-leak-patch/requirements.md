# ArgoCD CVE-2025-55190 — Project API Token Exposes Repository Credentials

## Context
CVE-2025-55190 (CVSS 10.0, Critical) affects ArgoCD v2.13.0 through v3.1.1. Any API token that
carries project-level `get` permissions can call `/api/v1/projects/{project}/detailed` and receive
all repository credentials in the response — including GitHub deploy-key passwords and bot
credentials — regardless of whether secret-access was explicitly granted to that token. No further
privilege escalation is required to exploit this.

ArgoCD at `ops.mctl.ai` is the central synchronisation engine for the entire platform. A credential
leak from this endpoint would expose every tenant's workload repositories. The patch is available in
v3.1.2, v3.0.14, v2.14.16, and v2.13.9. Because v3.3.9 (released 2026-04-30) also fixes
ApplicationSet generator panics, Redis cache issues, and UI crashes, it is the designated upgrade
target.

## User stories
- AS a platform security engineer I WANT ArgoCD upgraded to a version that does not expose
  repository credentials via the project details endpoint SO THAT tenant deploy keys and bot
  credentials cannot be exfiltrated through a low-privilege API token.
- AS a platform operator I WANT the upgrade to include all stability fixes shipped in v3.3.9
  SO THAT ApplicationSet generator panics and Redis cache regressions are also resolved in
  the same change window.
- AS an auditor I WANT the remediation committed to git and traceable to a specific CVE
  SO THAT compliance evidence exists for the critical-severity finding.

## Acceptance criteria (EARS)
- WHEN the ArgoCD server version is v3.3.9, THE SYSTEM SHALL respond to
  `/api/v1/projects/{project}/detailed` requests that carry only a project-scoped `get` token
  with a response that does not include repository credential fields (username, password, SSH key).
- WHEN a project-scoped API token calls `/api/v1/projects/{project}/detailed`, THE SYSTEM SHALL
  enforce the existing secret-access grant check before including any credential material.
- WHILE ArgoCD is running v3.3.9, THE SYSTEM SHALL continue to synchronise all ApplicationSet-
  generated Applications without panics or cache inconsistencies.
- IF the ArgoCD version running in the cluster is below v3.1.2, THEN THE SYSTEM SHALL fail a
  blocking CI gate that prevents the affected branch from being merged.
- WHEN the upgrade is complete, THE SYSTEM SHALL emit a Health=Healthy / Sync=Synced status
  for all ArgoCD Applications within 10 minutes of the rollout finishing.

## Out of scope
- Rotation of existing repository credentials (tracked separately; rotation is recommended but not
  part of this patch proposal).
- Changes to ArgoCD RBAC policy beyond what is required for the upgrade.
- Upgrading any Argo component other than ArgoCD (Argo Workflows, Argo Rollouts are separate
  proposals).
- Migration from ArgoCD to any alternative GitOps engine.
