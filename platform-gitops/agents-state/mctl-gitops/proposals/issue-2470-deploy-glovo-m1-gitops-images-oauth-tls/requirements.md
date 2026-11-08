# Glovo M1: inert GitOps deployment package for the gated multi-tenant fake Glovo MCP (P0), with P1/P2 activation boundaries

## Context

Issue mctlhq/mctl-gitops#2470 is the GitOps deployment slice of the fake Glovo
MCP planned in #2457 and owned by mctlhq/.github#324. The target is a
multi-tenant, OAuth-protected, allowlisted fake Glovo MCP at
`https://glovo.mctl.ai/mcp`. It is built from three separately built images: an
`mctl-telegram` MCP facade, a private fake Glovo provider worker, and a trusted
`mctl-agents` control worker. The issue splits the work into hard phases. P0 is
documentation plus inert manifests checked by render-only CI. P1 is the runtime
deployment, with its own approval. P2 is DNS, TLS, OAuth and allowlist
activation, with its own approval. P3, the real Glovo provider, is out of scope.

This proposal implements **P0 only**. It also writes the gates, checklists and
rollback runbooks that P1 and P2 must pass, but it never enables them. In this
repository "inert" is hard to get right. Two facts drive the design:
- The `apps` ApplicationSet
  (`platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml`)
  auto-syncs every directory matching `platform-gitops/services/*/*`, with
  `prune` and `selfHeal`.
- `*.mctl.ai` has a proxied wildcard DNS record
  (`infrastructure/cloudflare/zones/mctl-ai/dns.tf`, resource
  `cloudflare_dns_record.wildcard`).

As a result, any values file placed in a reconciled path deploys within about
30 seconds. Any Ingress claiming `glovo.mctl.ai` is publicly reachable with no
DNS change at all. P0 has to make that impossible, not just unlikely.

## AMEND 2026-11-08 — no self-authorized GitOps deployment gate

**Independent review P1:** the current `gate.yaml` may contain `p1: approved` plus an arbitrary GitHub issue URL, but it lives in the same PR-controlled repository tree as the manifests. This is **self-attestation**, NOT an authenticated human release grant. A PR could otherwise bypass the CI leak guard while activating ArgoCD resources on merge.

- Under this P0 proposal, the CI guard MUST **unconditionally refuse** Glovo host/Ingress, provider/control Deployments, Temporal namespaces and provider K8s namespace resources in every reconciled GitOps path — **even if `gate.yaml` claims P1/P2 approved**. No P0 self-override.
- `gate.yaml` is only a human-facing phase/evidence index and must be labelled "not authorization". A later P1/P2 proposal/PR requires an independently controlled release approval source **outside PR-modifiable files** bound to phase, environment, exact Git/manifest and immutable image digest, explicit owner, rollout/rollback; the verifier is itself separately reviewed and enforced as a required check. If unavailable, fail closed; do not count a pasted issue URL, GitHub comment or local YAML bit as approval.
- Add negative test with fake `gate.yaml` containing `p1: approved, p2: approved` and forged approval URL plus a valid reconciled Glovo Deployment; guard MUST fail. All prior network, JWT, bridge, tenant, OAuth and rollout gates remain.
- P0 merge must change only staged assets, validator and CI (non-reconciled), zero live workloads/DNS/credentials/Temporal changes; no activation authority is inherited from it.

## User stories

- AS the platform owner I WANT the full Glovo M1 deployment package reviewed
  as inert files SO THAT approving P0 cannot start a workload, change DNS or
  expose a host.
- AS a security reviewer I WANT each image pinned by immutable GHCR digest
  with SBOM and source commit linked SO THAT I know exactly what P1 would run.
- AS a P1 approver I WANT a written enablement checklist tied to #2469,
  mctl-agents#1043 and the JWT/TLS/authorizer slices SO THAT runtime
  deployment can only start after its dependencies are proven.
- AS an on-call engineer I WANT a rollback runbook and a kill switch defined
  before anything is live SO THAT P1/P2 can be reversed without improvising.
- AS an operator of mctl-agents DevLoop and kuptsi-app I WANT the existing
  Temporal namespaces and labs services untouched SO THAT nothing currently
  running is interrupted.

## Acceptance criteria (EARS)

- WHEN the P0 PR is merged THE SYSTEM SHALL create no Kubernetes object, no
  Argo CD Application, no Temporal namespace, no Vault path, no Cloudflare
  record and no Ingress (proven by CI guard and by `mctl_list_services labs`
  showing no new app after merge).
- WHILE P1 is not approved THE SYSTEM SHALL keep every Glovo M1 values file
  outside every path reconciled by Argo CD (`platform-gitops/services/*/*`,
  `platform-gitops/tenants/*`, `platform-gitops/infra-components/**`,
  `platform-gitops/bootstrap/**`, `platform-gitops/argo-workflows/**`).
- WHEN a PR adds the host `glovo.mctl.ai`, a Glovo worker image, the Temporal namespace names `mctl-assistants` / `mctl-assistants-provider-glovo`, or the provider Kubernetes tenant/namespace to any reconciled path **under P0** THE SYSTEM SHALL always fail CI regardless of any self-written `gate.yaml` phase or issue URL; a later P1/P2 verifier requires a separate reviewed owner approval bound to immutable artifacts,
  independently verified by a trusted external phase approval; a mutable `gate.yaml` never defines the grant.
- WHEN CI runs on the staged package THE SYSTEM SHALL render every staged
  component with `platform-gitops/helm-charts/base-service`, pass
  `kubeconform -strict`, and pass the reserved-hosts and Argo CD project-scope
  validators against the rendered output, without applying anything.
- IF a staged component's `image.tag` is not an `@sha256:` digest, or its
  provenance record lacks a source repo, commit SHA and SBOM reference, THEN
  THE SYSTEM SHALL fail CI.
- IF the staged provider-worker render contains an Ingress, a Service of type
  LoadBalancer/NodePort, or any ingress-allowing NetworkPolicy beyond what is
  explicitly listed, THEN THE SYSTEM SHALL fail CI (no public worker ingress).
- WHEN the staged facade render is produced THE SYSTEM SHALL expose only
  `glovo.mctl.ai` with path `/mcp` and the OAuth protected-resource metadata
  path, with the MCTL OAuth issuer, audience/resource `https://glovo.mctl.ai/mcp`
  and allowlist configuration declared, and with no worker or admin path routed.
- WHILE any phase is unapproved THE SYSTEM SHALL declare the facade's
  kill-switch and allowlist values fail-closed (feature disabled, empty
  allowlist, no team fallback).
- WHEN P1 or P2 is later requested THE SYSTEM SHALL require a separate PR that
  copies the staged files into reconciled paths, references its own approval
  issue, and passes the enablement checklist written in P0.

## Out of scope

- P1 runtime deployment: Temporal namespaces `mctl-assistants` and
  `mctl-assistants-provider-glovo`, the provider Kubernetes namespace, client
  identities, Vault/ESO secrets, NetworkPolicies applied to the cluster.
- P2 activation: DNS/TLS/Cloudflare changes, an Ingress for `glovo.mctl.ai`,
  pilot allowlist entries, the selected team tenant, MCP portal registration
  (`infrastructure/cloudflare/portal/mcp-servers.tf`).
- P3 real Glovo provider: no Glovo credentials, login, cookies, real basket
  API, order placement or checkout.
- Application code in `mctl-telegram`, `mctl-agents`, `mctl-api` (#953/#954).
- Changes to the shared Temporal server auth (#2456/#2469 own that work).
- Any change to existing labs services, kuptsi-app or mctl-agents workflows.

## Open questions

- Image coordinates: the facade, provider and control images and their GHCR
  repositories do not exist yet. P0 uses placeholders that CI requires to be
  replaced by real digests before P1 (`<digest-pending>` fails the P1 gate,
  not the P0 gate). Should P0 merge with placeholders, or wait for the first
  digests? Assumed: merge with placeholders, and the P1 gate refuses them.
- Whether the facade runs as a new `mctl-telegram` deployment (for example
  `labs/glovo-mcp`) or as a mode of the existing `labs/mctl-telegram`. Assumed:
  a separate deployment, so the `tg.mctl.ai` OAuth issuer and sessions are
  untouched. The issue rejects using `tg.mctl.ai` as the Glovo endpoint.
- Where the provider worker runs. The issue says "isolated Kubernetes workload
  namespace", but the platform only creates namespaces through tenants
  (`platform-gitops/tenants/*`), and `labs` is a hosting workspace. Assumed: a
  dedicated non-customer tenant/namespace `mctl-assistants-provider-glovo`
  created in P1 via the tenant chart with `allowInternetEgress: false`. This
  needs P1 confirmation.
- Where the trusted control worker runs (the `admins` namespace next to the
  mctl-agents workers, or its own namespace). Assumed: `admins`, decided in P1.
- Whether reserving `glovo.mctl.ai: []` (owned by nobody) in
  `reservedPlatformHosts` may land in P0. It is a live admission change, but
  purely restrictive. Assumed: proposed as an optional, separately approvable
  P0 hardening task (task 7). It is not required for P0 acceptance.
- OAuth issuer for `glovo.mctl.ai`: the MCTL authorization server (mctl-api)
  or a facade-local issuer, as `tg.mctl.ai` uses today (`OAUTH_ISSUER_URL`).
  The issue says "MCTL OAuth issuer". Assumed: the mctl-api issuer, with
  audience/resource `https://glovo.mctl.ai/mcp`. The exact issuer URL is
  pending mctl-api#953.
