# Spike: Temporal read-only client/RBAC inventory and isolated auth canary contract

## Context

Issue mctlhq/mctl-gitops#2469 follows ADR 0003 (`docs/adr/0003-temporal-client-authz.md`,
status Proposed) and its runbook (`docs/runbooks/temporal-client-auth.md`). The
runbook's "Live evidence" table marks every item `not observed`: the running
server image, rendered frontend config, client SDK versions, the default
authorizer's role-to-RPC mapping, issuer and non-empty audience enforcement,
Vault/ESO token delivery, and JWKS/TLS trust. Until those are filled, the
shared Temporal frontend (chart `temporal` 1.2.0, server 1.31.0, no
`global.tls` and no `global.authorization` in
`platform-gitops/bootstrap/templates/data/temporal.yaml`) has no client
authentication. The NetworkPolicy `allow-temporal-ingress` is the only
boundary, and that boundary lets the `labs` kuptsi-app terminate
`mctl-agents` DevLoop workflows. New `mctl-assistants*` namespaces are
release-blocked until this is resolved.

This proposal is a **docs/research-only spike**. It produces source-backed
evidence, a role/RPC matrix, a disposable canary contract with negative tests
and rollback gates, a dependency DAG of separately approval-gated downstream
issues, and an explicit recommendation. It changes no runtime, values,
credentials, DNS/TLS, Vault/ESO, SDK or namespace. It does not confuse an ADR
merge with security readiness.

## User stories

- AS a platform security reviewer I WANT every Temporal auth claim tied to a
  source link, version and observation date SO THAT readiness is proven, not
  assumed from an ADR merge.
- AS a DevLoop operator I WANT a canary contract that never touches the
  production Temporal release, its database or DevLoop/kuptsi workflows SO THAT
  the investigation cannot break running loops.
- AS the owner of future `mctl-assistants*` provider workers I WANT a
  method-by-method positive/negative matrix SO THAT I know exactly what a
  `<ns>:write` or `<ns>:worker` identity can and cannot do.
- AS an approver I WANT each future write phase split into its own issue with
  owner, repo, rollback and stop conditions SO THAT nothing is enabled
  without its own review and approval.

## Acceptance criteria (EARS)

- WHEN the spike documents are produced THE SYSTEM SHALL include an evidence
  inventory table in which every row has a source (file path at a pinned
  mctl-gitops commit, an upstream URL at a pinned tag, or a dated read-only
  command result), a version, an observation date, and one status:
  `VERIFIED_SOURCE`, `VERIFIED_LIVE`, `BLOCKED_NO_ACCESS` or
  `BLOCKED_JWT_SEMANTICS`.
- IF an item could not be observed THEN THE SYSTEM SHALL record it as
  `BLOCKED_NO_ACCESS` with the exact read-only command an operator would run.
  It SHALL NOT record such an item as absent, disabled or default.
- WHEN the role/RPC matrix is written THE SYSTEM SHALL derive it from Temporal
  server source at tag `v1.31.0` (`common/authorization/default_authorizer.go`,
  `common/authorization/default_jwt_claim_mapper.go`, `common/api/metadata.go`
  or their 1.31.0 equivalents), cite file and line ranges, and give, for each
  of `read`, `write`, `worker`, `admin` at namespace scope and
  `temporal-system:<role>` at cluster scope, allow/deny for at least:
  PollWorkflowTaskQueue, PollActivityTaskQueue, RespondWorkflowTaskCompleted,
  StartWorkflowExecution, SignalWorkflowExecution,
  SignalWithStartWorkflowExecution, TerminateWorkflowExecution,
  RequestCancelWorkflowExecution, QueryWorkflow, DescribeWorkflowExecution,
  ListWorkflowExecutions, GetWorkflowExecutionHistory, DescribeNamespace,
  RegisterNamespace, UpdateNamespace, ListNamespaces, the OperatorService
  search-attribute APIs, and GetSystemInfo/GetClusterInfo.
- WHILE documenting authorization THE SYSTEM SHALL state that the default
  authorizer has no task-queue dimension, and SHALL NOT claim queue-level RBAC.
- WHEN issuer and audience behaviour is documented THE SYSTEM SHALL state, from
  1.31.0 source, whether the stock claim mapper/key provider validates `iss`,
  whether and how it validates a configured non-empty audience, and which
  config key controls it. If the source does not establish enforcement, THE
  SYSTEM SHALL mark the item `BLOCKED_JWT_SEMANTICS` and require canary proof.
- WHEN JWKS trust is documented THE SYSTEM SHALL record that the in-cluster
  Vault listener is plaintext (`tls_disable = 1` in
  `platform-gitops/bootstrap/templates/core-infra/vault.yaml`). It SHALL
  reject any `http://` JWKS URI. It SHALL list only authenticated options:
  HTTPS with an explicit CA, or a separately reviewed pinned-key distribution.
- WHEN the canary contract is written THE SYSTEM SHALL require a separate Helm
  release in a separate Kubernetes namespace with its own throwaway database
  (not `temporal`/`temporal_visibility` on `shared-pg`), synthetic Temporal
  namespaces, synthetic identities and a canary-only signing key. It SHALL
  require no production credential and no connection to
  `temporal-frontend.temporal.svc.cluster.local`.
- WHEN the negative test suite is written THE SYSTEM SHALL map ADR tests T1-T11
  to concrete steps, each with an expected gRPC status (`Unauthenticated` or
  `PermissionDenied`), covering: missing, expired, unknown-key, forged,
  wrong-issuer and wrong-audience tokens; provider->control denial;
  kuptsi->DevLoop denial; and plaintext JWKS refusal.
- WHEN rollback gates are written THE SYSTEM SHALL define, for each future
  phase, a measurable SLO continuity check (production DevLoop and kuptsi
  workflow success and latency before/after) and a stop condition.
- WHEN downstream work is listed THE SYSTEM SHALL present a dependency DAG.
  Each node SHALL carry repo, owner, mandatory review, approval gate,
  rollback, deployment sequencing and stop condition, and SHALL be a
  separate DevLoop proposal.
- WHEN the web UI is discussed THE SYSTEM SHALL state whether stock
  temporal-web needs `temporal-system:read`, and what visibility that grants
  across namespaces. It SHALL defer enabling it until an explicit admin-only
  risk acceptance.
- WHEN the spike concludes THE SYSTEM SHALL give exactly one recommendation,
  `GO_TO_SEPARATE_IMPLEMENTATION_PROPOSAL` or `BLOCKED`, plus the issue outcome
  label(s) (`VERIFIED_INVENTORY`, `BLOCKED_NO_ACCESS`, `BLOCKED_JWT_SEMANTICS`,
  `READY_FOR_SEPARATE_CLIENT_SUPPORT_PROPOSAL`) and an explicit list of
  unresolved unknowns.
- WHILE this proposal is implemented THE SYSTEM SHALL change only Markdown files
  under `docs/`. It SHALL change nothing under `platform-gitops/`,
  `infrastructure/` or `cli/`, and SHALL NOT move ADR 0003 beyond `Proposed`.

## Out of scope

- Any GitOps values or runtime change, including `global.tls`,
  `global.authorization` or NetworkPolicy edits.
- DNS, TLS, certificates, Vault (OIDC keys/roles, listener TLS), ESO, and SDK
  or client code changes.
- New credentials, Vault roles or signing keys, including canary keys. The
  canary is designed here, not deployed.
- Creating any Kubernetes namespace or Temporal namespace.
- Production rollout or cutover, and live negative tests against the
  production frontend or current DevLoop/kuptsi workflows.
- Any use of a Glovo account (mctlhq/mctl-telegram#1227).
- Auto-approval of this or any downstream proposal.

## Open questions

- Live access: this investigation run had no read path into the `temporal`
  Kubernetes namespace. The mctl MCP tools cover tenant services
  (`admins`, `labs`), not the `temporal` platform Application. Can an operator
  run the listed read-only `kubectl`/`temporal operator` commands? If not, those
  rows stay `BLOCKED_NO_ACCESS` and the recommendation stays `BLOCKED` for any
  authorizer phase.
- JWKS transport: in-cluster Vault is plaintext (an accepted residual, SOC
  F15). The public `https://secrets.mctl.ai` path depends on Cloudflare, and
  mctl-api moved away from it after the 2026-10-09 readiness outage
  (`mctl-api.yaml` comment). Is a pinned-key distribution acceptable, or is a
  Vault TLS listener a prerequisite? This proposal records both options and
  picks neither.
- Whether the 1.31.0 stock claim mapper validates `iss` at all. If it does
  not, issuer pinning reduces to "only this issuer's keys are in the key set".
  This must be stated, not assumed.
- Whether `worker` alone is enough for a polling worker that also needs to
  start child workflows or signal. This decides whether the ADR's "narrow to
  `worker` only if proven" can ever apply.
- Canary cluster placement: the same k3s cluster with a separate namespace and
  database, or the preprod `infrastructure/k3s-preview` cluster. This is
  recorded as a downstream decision.
