# Remediate Grafana Memory Exhaustion DoS (CVE-2026-27880)

## Context

CVE-2026-27880 (CVSS 7.5 High) is a memory exhaustion denial-of-service vulnerability
affecting Grafana v12.1.0 and later. An attacker — potentially unauthenticated or holding
only low-privilege access — can trigger excessive memory consumption in the Grafana server
process, crashing the instance. The vulnerability was disclosed alongside CVE-2026-27876
(the RCE covered by `grafana-sql-rce-patch`) and is fixed in the same patched release set:
v12.1.10, v12.2.8, v12.3.6, v12.4.2, and v11.6.14.

The existing proposal `grafana-sql-rce-patch` addresses the RCE attack vector (CVE-2026-27876)
but contains no acceptance criteria for the DoS attack vector. Even after `grafana-sql-rce-patch`
is fully executed, a gap remains: a patched Grafana instance is immune to RCE but, if
the release upgrade was not applied (e.g., only the `sqlExpressions` toggle mitigation was
used), it may still be vulnerable to memory exhaustion. This proposal closes that gap with
dedicated requirements and a verification step scoped to the DoS scenario.

Because Grafana is listed as "if templated" in `context/architecture.md`, this proposal
must first confirm whether a Grafana deployment exists before taking any action. If Grafana
runs in the `labs` tenant, the memory exhaustion attack surface is doubly relevant: a
successful DoS attack on a `labs` Grafana instance would consume memory in a namespace
already near its quota, potentially cascading into Out-of-Memory kills for other `labs`
workloads.

## User stories

- AS a platform operator I WANT to confirm whether Grafana is deployed in this repo SO THAT
  the scope of CVE-2026-27880 exposure is known before action is taken.
- AS a security engineer I WANT Grafana upgraded to a release that patches CVE-2026-27880
  SO THAT an attacker cannot crash the Grafana instance through memory exhaustion.
- AS a platform operator I WANT the patch version selection coordinated with
  `grafana-sql-rce-patch` SO THAT both CVEs are resolved by a single upgrade and there is
  no version churn.
- AS an on-call engineer running `labs` I WANT assurance that a DoS against Grafana cannot
  cascade into OOM kills for other `labs` workloads SO THAT tenant stability is preserved.

## Acceptance criteria (EARS)

- WHEN this proposal is actioned, THE SYSTEM SHALL first confirm whether a Grafana deployment
  exists under `platform-gitops/services/` or `platform-gitops/helm-charts/` in this
  repository.
- IF no Grafana deployment is found in the repository, THE SYSTEM SHALL close this proposal
  as not applicable and document the finding in the PR description.
- IF a Grafana deployment is found and the running image version is v12.1.0 or later and
  earlier than the relevant patched release, THE SYSTEM SHALL upgrade the image tag to the
  appropriate patched version (v12.1.10, v12.2.8, v12.3.6, or v12.4.2 depending on the
  current minor line).
- WHEN the Grafana image tag is updated in the values file, THE SYSTEM SHALL commit the
  change to this repository so that ArgoCD syncs the patched version to the cluster.
- WHEN ArgoCD syncs the patched Grafana image, THE SYSTEM SHALL confirm that the Grafana
  Application shows `Synced` and `Healthy` in ArgoCD after the rolling restart completes.
- WHEN Grafana is running a patched release, THE SYSTEM SHALL confirm that the CVE-2026-27880
  fix is present by verifying the running image digest or version string matches the expected
  patched release.
- IF Grafana is deployed in the `labs` tenant, THE SYSTEM SHALL document the memory delta
  (before and after upgrade) for ArgoCD pods and Grafana pods in `labs` so that the impact
  on the `labs` memory quota is known.
- WHILE Grafana is running a patched version, THE SYSTEM SHALL NOT revert the image tag to
  any version in the vulnerable range (v12.1.0 through v12.1.9 / v12.2.7 / v12.3.5 /
  v12.4.1) without a documented security exemption.
- WHEN this proposal is executed concurrently with `grafana-sql-rce-patch`, THE SYSTEM SHALL
  ensure that both CVEs are addressed by the same image tag update and that no intermediate
  state is committed in which only one CVE is patched.

## Out of scope

- Mitigating CVE-2026-27876 (the RCE vector) — covered by `grafana-sql-rce-patch`.
- Changes to Grafana Loki datasource configuration or log retention policies.
- Changes to existing dashboard definitions or alert rules.
- Grafana RBAC restructuring beyond what is required to close this CVE.
- Adding rate limiting or network policies at the ingress layer to restrict who can reach the
  Grafana HTTP endpoint (useful hardening but not required to close the CVE).
- Any Grafana instance not managed by this repository (e.g., external SaaS Grafana Cloud).
