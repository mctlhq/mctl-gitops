# Upgrade cert-manager v1.20.3 -> v1.20.5 on k3s-preview to drop trust in the compromised eMudhra CA

## Context

Issue #2246 (a scout spike) asks two things: which cert-manager version mctl
clusters run, and whether they can move to cert-manager v1.20.5. v1.20.5 is a
security release from 2026-10-28, and its release notes say "all users should
upgrade". It makes these changes:

- It removes trust in the compromised eMudhra CA.
- It moves the base images to Debian 13, which drops the "emSign ECC Root CA - G3"
  and "AAA Certificate Services" roots.
- It builds with Go 1.26.10, whose `crypto/x509` rejects chains through the
  compromised intermediates (CVE-2026-111943).
- It bumps `golang.org/x/net` to v0.60.0, fixing five HTTP/2 CVEs that
  `govulncheck` flagged as reachable in v1.20.4.
- It bumps `x/crypto`, `go-jose` and the OTLP exporters.

The only breaking-type change affects building from source, which now needs
Go 1.26. Released images are unaffected.

The issue sets a boundary: re-observe the deployed version first, and do not
manufacture an upgrade if the cluster already contains these fixes. mctl runs
one cluster, `infrastructure/k3s-preview`; `infrastructure/k3s-prod` is a
README-only TODO. Its cert-manager is the kube-hetzner module's k3s HelmChart.
The chart is pinned in `infrastructure/k3s-preview/kube.tf` as
`local.cert_manager_version = "v1.20.3"`, and that file's comment records it
as "the charts running on 2026-10-22". v1.20.3 predates v1.20.5, so it lacks
the eMudhra removal and the HTTP/2 fixes. A patch-level upgrade within the
1.20 line is therefore warranted. This proposal also supersedes the older
`cert-manager-dns-dos-patch` proposal, which targets v1.20.2: the cluster is
already past v1.20.2.

## User stories

- AS a platform operator I WANT the cluster's cert-manager pinned to v1.20.5
  SO THAT the ACME controller no longer trusts eMudhra-issued chains and is not
  exposed to the reachable HTTP/2 CVEs.
- AS a security reviewer I WANT a recorded trust/version audit (pinned value,
  live value, and what v1.20.5 changes) SO THAT the decision to upgrade, or not,
  is backed by evidence.
- AS a service owner on the `admins` / `labs` tenants I WANT certificate
  issuance and renewal to keep working through the upgrade SO THAT my
  ingress hosts never serve an expired or missing certificate.

## Acceptance criteria (EARS)

- WHEN the upgrade PR is opened THE SYSTEM SHALL change only
  `local.cert_manager_version` in `infrastructure/k3s-preview/kube.tf` from
  `"v1.20.3"` to `"v1.20.5"`, and update the adjacent comment to record why
  and when the version was bumped.
- WHEN the version local changes THE SYSTEM SHALL change
  `local.base_kustomization_inputs`, because that value already hashes
  `local.cert_manager_version`. The `terraform.yml` plan job SHALL then show
  `terraform_data.kustomization` being replaced, plus the dependent
  kured/system-upgrade-controller user manifests re-rendering, and no
  server, network, SSH-key or node-provisioner replacement.
- WHEN the change is applied through `terraform.yml` with `apply: true` and
  the `k3s-apply` reviewer gate THE SYSTEM SHALL leave the `cert-manager`
  HelmChart in `kube-system` at chart version `v1.20.5`. The controller,
  cainjector and webhook Deployments SHALL run `v1.20.5` images.
- WHILE the upgrade rolls out THE SYSTEM SHALL keep the existing
  `letsencrypt-prod`, `letsencrypt-staging` and `letsencrypt-http01`
  ClusterIssuers Ready, and the resource values in
  `extra-manifests/cert-manager-helmchartconfig.yaml.tpl` SHALL stay
  unchanged and applied.
- WHEN the upgrade has been applied THE SYSTEM SHALL record a trust/version
  audit in the PR, or in a follow-up issue comment on #2246. The audit SHALL
  give the pinned version, the live HelmChart version, the live controller
  image tags, the Certificate Ready count before and after, and the v1.20.5
  trust changes.
- IF the live HelmChart or controller image is already at v1.20.5 or later,
  or on a newer line that contains the same eMudhra removal and x/net v0.60.0
  fixes, THEN THE SYSTEM SHALL NOT downgrade it. The implementer SHALL instead
  align `local.cert_manager_version` with the live version, or close #2246 with
  the audit evidence when the pin already matches.
- IF any Certificate goes not-Ready, or the webhook rejects admissions after
  the upgrade, THEN THE SYSTEM SHALL be rolled back by reverting the version
  local to `"v1.20.3"` and re-applying.

## Out of scope

- Upgrading to a new cert-manager minor line (1.21.x), or changing CRDs,
  ClusterIssuers or chart values.
- Deploying trust-manager. No trust-manager exists in the repo; grep for
  `trust-manager`/`emudhra` finds nothing.
- Auditing the CA trust stores of other workloads: node OS `ca-certificates`,
  Alpine-based Argo workflow steps (`apk add ca-certificates`), and tenant
  service images. These are recorded as follow-up candidates only.
- Any change to `k3s-prod`, which does not exist yet.
- Implementing the `cert-manager-acme-rbac-bypass` RBAC tightening. v1.20.3
  already contains its CVE-2026-62290 code fix.

## Open questions

- The live cluster state was not observed. The mctl MCP tools only expose
  tenant services, and cert-manager runs in `kube-system` outside any tenant.
  The pinned `v1.20.3` and the 2026-10-22 comment in `kube.tf` are the only
  evidence. The implementer or the reviewer must confirm the live HelmChart
  version and the controller image before applying; the rule for a newer live
  version is above.
- The `cert-manager-acme-rbac-bypass` proposal claims "our fleet's most
  recently observed release is 1.21.2". That contradicts the `v1.20.3` pin and
  has no evidence behind it. If 1.21.x really is live, the pin is wrong. The
  task would then become aligning the pin and checking whether that 1.21 patch
  carries the eMudhra removal; it would not be this downgrade.
- The proposal assumes the kube-hetzner 2.19.1 HelmChart installs CRDs with the
  chart (`crds.enabled`), so a chart bump updates them. v1.20.3 to v1.20.5 is a
  patch release, so no CRD schema change is expected. Confirm this in the plan
  output and the helm-install job log.
- Should the stale `cert-manager-dns-dos-patch` proposal (target v1.20.2) be
  closed as superseded? This proposal recommends yes.
