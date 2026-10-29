# Upgrade cert-manager v1.20.3 -> v1.20.5 on k3s-preview to drop trust in the compromised eMudhra CA

## Context

Issue #2246 asks which cert-manager version mctl clusters run and whether they can move to v1.20.5. v1.20.5 is a security release from 2026-10-28 that removes trust in the compromised eMudhra CA and carries reachable HTTP/2 dependency fixes.

The repository pin is `local.cert_manager_version = "v1.20.3"` in `infrastructure/k3s-preview/kube.tf`; that file records the pin as the chart running on 2026-10-22. v1.20.3 predates the v1.20.5 fixes. The older `cert-manager-dns-dos-patch` proposal targets v1.20.2 and is therefore obsolete if the v1.20.3 pin reflects reality.

This proposal is deliberately limited to **audit + reviewable PR preparation**. It must not dispatch `terraform.yml` with `apply: true`, approve the `k3s-apply` environment, or otherwise change the live cluster. Production apply remains a separate operator action after the PR, plan and live-version evidence are reviewed.

## User stories

- AS a platform operator I WANT the live and pinned cert-manager versions reconciled SO THAT we do not downgrade a cluster whose live state is already newer than git.
- AS a security reviewer I WANT a one-file, plan-backed PR to v1.20.5 when warranted SO THAT the security update can pass the normal production gate.
- AS the platform owner I WANT the spike to stop before production apply SO THAT investigation approval is not also deployment approval.

## Acceptance criteria (EARS)

- WHEN the spike begins THE SYSTEM SHALL re-observe the live cert-manager HelmChart version, controller/cainjector/webhook image tags, Certificate Ready count and ClusterIssuer status when read-only cluster access is available; unavailable facts SHALL be marked `unknown (not observed)` rather than guessed.
- IF the live HelmChart or controller images are already at v1.20.5 or later, or on a newer line that contains the same fixes, THEN THE SYSTEM SHALL NOT downgrade. It SHALL either prepare a pin-alignment PR to the observed live version or report that no code change is required.
- IF the live state is compatible with the v1.20.3 pin and the upgrade is warranted, WHEN the implementation PR is opened THE SYSTEM SHALL change only `local.cert_manager_version` in `infrastructure/k3s-preview/kube.tf` from `"v1.20.3"` to `"v1.20.5"` and update the adjacent explanatory comment.
- WHEN the version local changes THE SYSTEM SHALL rely on the existing `local.base_kustomization_inputs` hash and SHALL NOT edit the module argument line, ClusterIssuers, CRDs or `cert-manager-helmchartconfig.yaml.tpl`.
- WHEN the PR plan runs THE SYSTEM SHALL verify that no server, network, SSH-key or node-provisioner replacement is proposed. Any such change SHALL block the PR.
- WHEN the spike completes THE SYSTEM SHALL leave a production handoff containing: observed/pinned versions, the PR, plan evidence, expected post-apply checks, and rollback instructions.
- WHILE this spike is being implemented THE SYSTEM SHALL NOT dispatch `terraform.yml` with `apply: true`, SHALL NOT approve `k3s-apply`, and SHALL NOT mutate the live cert-manager installation.

## Out of scope

- Production apply or any live cluster mutation.
- Upgrading to a new cert-manager minor line such as 1.21.x.
- Changing CRDs, ClusterIssuers or chart values.
- Deploying trust-manager.
- Auditing CA trust stores of unrelated workloads.
- Implementing the separate `cert-manager-acme-rbac-bypass` proposal.

## Open questions

- The live cluster state was not observed by the investigator. The repository pin and its 2026-10-22 comment are evidence, but not a substitute for live readback.
- The `cert-manager-acme-rbac-bypass` proposal contains an unverified claim that a 1.21.2 fleet was observed. If live state confirms that, this proposal must not create a downgrade.
- Whether kube-hetzner 2.19.1 changes any generated CRD/install behavior between these patch versions should be checked from the plan/render evidence; no live apply is required to answer the spike.
- The stale `cert-manager-dns-dos-patch` proposal should be marked superseded once the version audit confirms the current baseline.