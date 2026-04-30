# Grafana RCE via SQL Expressions and Plugin Chaining (CVE-2026-27876)

## Context

CVE-2026-27876 (CVSS 9.1 Critical) is a remote code execution vulnerability in Grafana versions
v11.6.0–v12.4.1. An attacker with only Viewer-level permissions, when the `sqlExpressions`
feature toggle is enabled, can overwrite a Sqlyze driver or AWS data source configuration to
achieve remote code execution with SSH-level access to the Grafana host. Fixed in v12.1.10,
v12.2.8, v12.3.6, v12.4.2, and v13.0.0+.

The mctl platform's `context/architecture.md` lists Grafana/Loki as "if templated" — meaning
Grafana may be deployed as a service via the `base-service` Helm chart under
`platform-gitops/services/<tenant>/grafana/`. If deployed, it runs with cluster-level credentials
in a shared Kubernetes cluster. Host RCE on such a pod is a direct path to cluster-wide
compromise. This proposal must be executed conditionally: first confirm deployment, then remediate.

## User stories

- AS a platform operator I WANT to confirm whether Grafana is deployed via this repo SO THAT the
  scope of CVE-2026-27876 exposure is known before taking action.
- AS a security engineer I WANT the `sqlExpressions` feature toggle disabled immediately SO THAT
  the RCE attack vector is closed without waiting for a full version upgrade.
- AS a platform operator I WANT Grafana upgraded to a patched release (≥v12.1.10) SO THAT the
  underlying vulnerability is eliminated and the toggle restriction can be lifted if needed.

## Acceptance criteria (EARS)

- WHEN this proposal is actioned, THE SYSTEM SHALL first confirm whether a Grafana deployment
  exists under `platform-gitops/services/` in this repository.
- IF no Grafana deployment is found in the repository, THE SYSTEM SHALL close this proposal as
  not applicable and document the finding in the PR description.
- IF a Grafana deployment is found and the image version is in the range v11.6.0–v12.4.1, THE
  SYSTEM SHALL apply `sqlExpressions = false` in `grafana.ini` as an interim mitigation within
  one deploy cycle.
- WHEN the `sqlExpressions` toggle is set to false, THE SYSTEM SHALL confirm that existing
  dashboards that do not use SQL Expressions continue to render correctly.
- WHEN the Grafana image is upgraded to a patched release (≥v12.1.10), THE SYSTEM SHALL confirm
  that the ArgoCD Application shows `Healthy` and `Synced` post-rollout.
- WHILE Grafana is running a patched version, THE SYSTEM SHALL not require `sqlExpressions`
  to remain disabled unless operationally necessary.

## Out of scope

- Changes to Grafana Loki datasource configuration or log retention policies.
- Changes to existing dashboard definitions or alert rules.
- Grafana RBAC restructuring beyond what is required to close this CVE.
- Any Grafana instance not managed by this repository (e.g., external SaaS Grafana Cloud).
