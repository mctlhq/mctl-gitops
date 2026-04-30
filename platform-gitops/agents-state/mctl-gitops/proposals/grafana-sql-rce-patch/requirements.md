# Grafana RCE via SQL Expressions (CVE-2026-27876)

## Context
CVE-2026-27876 (Critical, CVSS 9.1) affects Grafana v11.6.0 through v12.4.1. When the
`sqlExpressions` feature toggle is enabled, a user with Viewer-level permissions can
overwrite a Sqlyze driver or AWS data source configuration to achieve remote code execution
with SSH-level access on the Grafana host. This is an unauthenticated-adjacent attack
surface: Viewer accounts are commonly granted to broad audiences (developers, on-call
engineers, external stakeholders) and are not considered privileged. Fixed versions are
v12.1.10, v12.2.8, v12.3.6, v12.4.2, and v13.0.0 and later.

Per `context/architecture.md`, Grafana is listed as a dependency "if templated" —
indicating it may be deployed via the platform's templated Helm charts rather than being
a confirmed, always-present service. Regardless of deployment status, a CVSS 9.1 RCE
warrants a pre-emptive proposal. If Grafana is deployed with cluster-level credentials
(as is typical when deployed via `helm-charts/base-service`), host RCE becomes a stepping
stone to broader cluster compromise. The remediation is a version upgrade to a patched
release, or disabling the `sqlExpressions` feature toggle as an interim mitigation that
does not require a full upgrade.

## User stories
- AS a platform operator I WANT Grafana to be upgraded to a patched version or to have
  `sqlExpressions` disabled SO THAT a Viewer-level account cannot achieve RCE on the
  Grafana host.
- AS a security engineer I WANT confirmation that the `sqlExpressions` feature toggle is
  disabled or that Grafana is running a fixed version SO THAT CVE-2026-27876 is closed
  with evidence.
- AS a platform user with Viewer access I WANT assurance that my Viewer credentials cannot
  be exploited to escalate to host-level access SO THAT the principle of least privilege
  is enforced.

## Acceptance criteria (EARS)
- WHEN Grafana is confirmed as deployed on the platform THE SYSTEM SHALL be running a
  version that includes the CVE-2026-27876 fix (v12.1.10+, v12.2.8+, v12.3.6+, v12.4.2+,
  or v13.0.0+) OR have the `sqlExpressions` feature toggle explicitly set to `false`.
- WHEN the `sqlExpressions` feature toggle is disabled THE SYSTEM SHALL return an error
  to any request that attempts to use SQL Expression queries, preventing the exploit
  precondition from being met.
- WHILE Grafana is running the patched version THE SYSTEM SHALL reject attempts by
  Viewer-level accounts to overwrite data source driver configurations via the SQL
  Expressions path.
- IF Grafana is not deployed (the "if templated" condition is false) THEN THE SYSTEM SHALL
  have a documented confirmation of non-deployment committed to the decisions log, and this
  proposal's tasks SHALL be marked as resolved via that confirmation.
- IF Grafana is deployed via the templated Helm chart THEN THE SYSTEM SHALL have the
  Grafana image version pinned to a patched release in the values file under
  `platform-gitops/services/<tenant>/grafana/`.
- WHEN the Grafana upgrade or toggle change is applied via an ArgoCD sync THE SYSTEM SHALL
  complete reconciliation without sync errors or Grafana Pod crash-loops.

## Out of scope
- CVE-2026-21726 (Loki path traversal) — separate CVE, separate proposal if prioritized.
- Changes to Grafana data source configurations beyond disabling the `sqlExpressions` toggle.
- Grafana alerting, dashboard content, or RBAC role definitions beyond what is needed to
  close the CVE.
- Any Loki, Prometheus, or other observability stack components — only the Grafana server
  process is in scope.
- Grafana Enterprise features or Grafana Cloud deployments.
