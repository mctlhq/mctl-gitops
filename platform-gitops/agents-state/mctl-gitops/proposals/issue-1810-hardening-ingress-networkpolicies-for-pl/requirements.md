# Ingress NetworkPolicies for platform namespaces, Temporal first

## Context

Issue mctlhq/mctl-gitops#1810 reports that several platform namespaces have no
ingress NetworkPolicy, so any pod in the cluster can reach them, tenant pods
included. Every tenant namespace gets `allow-cluster-egress` from
`platform-gitops/helm-charts/tenant/templates/networkpolicy.yaml`, which opens
egress to all of RFC1918, so the only thing that can stop a tenant pod reaching
a platform Service is an ingress policy on the destination namespace. The
Temporal frontend (`temporal-frontend.temporal.svc.cluster.local:7233`) has no
client authentication, so today any tenant pod can start, signal, query,
terminate or reset workflows in any Temporal namespace, including the
`mctl-agents` DevLoop namespace that drives the agent pipeline.

Part of the issue's list is already done in this repo: `vault`
(`bootstrap/templates/core-infra/vault-netpol.yaml`), `platform-db`
(`infra-components/data/cnpg/shared/networkpolicy.yaml`), `argo-workflows`
(`argo-workflows/config/networkpolicy.yaml`), `mctl-api`
(`bootstrap/templates/mctl-platform/mctl-api-netpol.yaml`) and Grafana inside
`monitoring` (`infra-components/observability/grafana-access/networkpolicy.yaml`)
already carry ingress allowlists. This proposal therefore delivers phase 1
(Temporal) completely and fixes the shape, order and test procedure of the
remaining namespaces (`argocd`, `backstage`, `monitoring` / Loki), each as its
own follow-up PR.

## User stories

- AS a platform operator I WANT the Temporal frontend reachable only from its
  real clients SO THAT a tenant workload cannot drive or tamper with DevLoop
  workflows through an unauthenticated gRPC endpoint.
- AS a platform operator I WANT every platform namespace protected by an
  explicit, commented ingress allowlist SO THAT network reachability of the
  control plane is a reviewed decision rather than a default.
- AS the owner of `labs/kuptsi-app` I WANT my Temporal API and worker
  containers to keep working SO THAT hardening does not break a legitimate
  tenant client.
- AS an on-call engineer I WANT a repeatable live probe SO THAT I can prove,
  after each phase, that blocked sources are blocked and listed clients still
  connect.

## Acceptance criteria (EARS)

- WHEN the temporal Application syncs THE SYSTEM SHALL apply a NetworkPolicy
  `allow-temporal-ingress` in namespace `temporal` that selects all pods
  (`podSelector: {}`) with `policyTypes: [Ingress]`.
- WHILE `allow-temporal-ingress` exists THE SYSTEM SHALL accept connections to
  pods in `temporal` from: pods in `temporal` itself (server-internal
  history/matching/worker/frontend traffic, the schema Job, the
  `temporal-namespaces-bootstrap` Job, temporal-web); namespace `mctl-api`;
  namespace `admins` (the `mctl-agents-worker`, `-exec` and `-implement`
  Deployments); namespace `monitoring`; and namespaces `traefik` and
  `kube-system`.
- WHILE `allow-temporal-ingress` exists THE SYSTEM SHALL accept connections
  from namespace `labs` only from pods labelled
  `app.kubernetes.io/instance: labs-kuptsi-app`, and only on TCP 7233.
- IF a pod in any tenant namespace other than the allowlisted `labs`
  kuptsi-app pod opens TCP to `temporal-frontend.temporal.svc:7233` THEN THE
  SYSTEM SHALL drop the connection.
- WHEN the policy is live THE SYSTEM SHALL still complete a DevLoop start
  (mctl-api `use_temporal` path), approve signal and status query
  (`GET /api/v1/agents/dev-loop/{id}`), and the `admins` workers SHALL keep
  polling their task queues (`mctl-dev-loop`, `mctl-dev-loop-exec`,
  `mctl-dev-loop-implement`).
- WHEN the policy is live THE SYSTEM SHALL keep `https://temporal.mctl.ai`
  serving the Temporal UI through Traefik with Backstage forward-auth.
- WHEN a later phase adds an ingress allowlist to `argocd`, `backstage` or
  `monitoring` THE SYSTEM SHALL ship it as one PR per namespace, with every
  peer commented with the evidence for it, and SHALL keep `traefik`,
  `kube-system` and `monitoring` (scrape) on the list.
- IF a new policy is rendered into a namespace labelled `mctl.me/tenant` THEN
  THE SYSTEM SHALL also add its name to `mctl-tenant-networkpolicy-allowlist`
  in `bootstrap/templates/system/admission-policies.yaml` in the same PR
  (#1484); the Temporal policy lives in the non-tenant `temporal` namespace
  and needs no allowlist entry.
- WHEN a phase is merged and synced THE SYSTEM SHALL be verified live with the
  probe in tasks.md (a tenant pod is denied, every listed client is allowed)
  before the next phase's PR is opened.

## Out of scope

- Temporal client authentication (mTLS or a custom authorizer) — issue step 4,
  a separate follow-up.
- Rewriting the existing `vault`, `platform-db`, `argo-workflows` and
  `mctl-api` allowlists; they are only re-verified by the live probe.
- Egress restrictions for platform namespaces.
- Admission control preventing label forgery on tenant pods (#800).
- Implementing the `argocd`, `backstage` and `monitoring` policies in this
  proposal's PR; this proposal specifies them and they land as separate PRs.

## Open questions

- Do any mctl-agents Argo Workflow pods (cwft-mctl-agents-investigate /
  -implement, which receive `temporal_workflow_id` / `temporal_run_id`) dial
  the Temporal frontend themselves? No `TEMPORAL_ADDRESS` appears in
  `platform-gitops/argo-workflows/`, so the design does NOT allow
  `argo-workflows`; task 1 confirms this from live connections before merge,
  and the namespace is added if any connection is seen.
- The Temporal server exposes no scrape today (no VMServiceScrape for the
  `temporal` namespace was found); `monitoring` is allowed anyway so a future
  scrape is not silently broken. Reviewer may prefer to omit it until needed.
- Whether `labs/kuptsi-app` should stay a direct Temporal client long-term, or
  whether Temporal namespace isolation (step 4) is the right boundary between
  the `kuptsi` and `mctl-agents` Temporal namespaces. Until step 4, kuptsi-app
  can still reach the `mctl-agents` Temporal namespace.
- The pod label `app.kubernetes.io/instance` on tenant pods is set by
  base-service but not protected against forgery by another tenant workload in
  `labs` via `podLabels`; the namespace selector bounds this to `labs` only.
