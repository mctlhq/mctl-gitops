# Glovo P1 Temporal control isolation: route decision and evidence gate

## Context

Glovo M1 (plan mctlhq/mctl-gitops#2457) needs a trusted control worker
(`GlovoControlWorkflow`, mctl-agents#1044) and mctl-api to use Temporal. The
shared Temporal cluster in the `temporal` namespace has these properties:
- It runs server 1.31.0 from chart 1.2.0 (`platform-gitops/bootstrap/templates/data/temporal.yaml`).
- It serves plaintext gRPC on 7233 and has no authorizer. Live read-only
  evidence dated 2026-11-09 is in `docs/runbooks/temporal-client-auth.md`,
  and the finding is #2538.
- Its only boundary is the NetworkPolicy `allow-temporal-ingress`. That
  policy decides who may connect, not what a connected client may do. Today,
  any admitted caller can act on every Temporal namespace, including the
  `mctl-agents` DevLoop namespace.

Issue #2568 asks for a Glovo-specific P1 readiness decision built on the
existing #2469 inventory and authorization DAG (nodes A to J), without
duplicating that investigation. The decision must:
- choose route A (secure the shared frontend) or route B (an isolated
  Temporal deployment with no new nodes), or declare BLOCKED;
- pin the caller/issuer/audience/JWKS and role-to-RPC policy;
- define the negative evidence;
- list the dependency chain and the missing proofs;
- end in a P1 security approval request.

No production Temporal change, namespace, secret, approval or deployment is
made under this issue. The deliverable is a version-controlled decision
record that keeps P1 BLOCKED until every listed proof exists.

## User stories

- AS the Glovo M1 owner I WANT one documented route (A or B) with its
  critical path and approval gates SO THAT P1 work is sequenced against a
  single, reviewable plan.
- AS a security reviewer I WANT an exact, version-pinned caller/issuer/
  audience/JWKS and namespace-permission policy with default-deny cases SO
  THAT I can approve or reject P1 against concrete evidence, not intent.
- AS the platform operator I WANT desired GitOps state and live state kept
  apart, with every unobserved item marked NOT_OBSERVED, SO THAT a missing
  read is never mistaken for a safe answer.
- AS a DevLoop and kuptsi user I WANT the chosen route to state its impact
  on existing workflows, history and rollback SO THAT P1 does not break the
  workloads that already use the shared cluster.

## Acceptance criteria (EARS)

- WHEN the decision record is merged THE SYSTEM SHALL contain
  `docs/runbooks/glovo-p1-temporal-isolation.md` with a single verdict line
  of the form `VERDICT: ROUTE_A_SELECTED; P1: BLOCKED`.
- THE SYSTEM SHALL record in the decision record a read-only inventory with:
  - frontend TLS, authorizer and claim-mapper settings;
  - Temporal namespaces and client identities;
  - release and rollback safety;
  - node capacity.
  Each row SHALL be labelled `VERIFIED_SOURCE`, `VERIFIED_LIVE` (dated
  operator output only) or `NOT_OBSERVED`, and SHALL keep desired GitOps
  state and live state in separate columns.
- THE SYSTEM SHALL record in the decision record an A versus B matrix
  comparing:
  - critical path (which #2469 DAG nodes each route needs);
  - scope of changes;
  - feasibility with no new nodes;
  - impact on DevLoop and kuptsi;
  - independent owner approval gates.
- THE SYSTEM SHALL state the reason route B is not selected.
- THE SYSTEM SHALL record a version-pinned policy table covering:
  - versions: server 1.31.0, chart 1.2.0, Go SDK 1.50.0, Python SDK 1.34.0;
  - caller identity, issuer source, `aud` value and JWKS trust path for each
    caller;
  - the exact `<namespace>:<role>` permission strings for each caller.
  Any value not yet decided SHALL be marked as an unresolved gate, not
  filled in.
- THE SYSTEM SHALL state that the fake provider (mctl-telegram#1262) holds
  no Temporal credential and is not admitted on port 7233, and SHALL list
  provider-to-control and provider-to-DevLoop denial as required negative
  tests.
- THE SYSTEM SHALL map each required default-deny case to a canary step
  (S1-S17) in `docs/runbooks/temporal-auth-canary.md` and to a
  production-proof step (node H). The required cases are:
  - missing, expired, forged and wrong-audience tokens;
  - cross-namespace start, signal, query, list and terminate.
- THE SYSTEM SHALL list the dependency chain to P1. For each node it SHALL
  give the owner, the filed issue or PR (or "not filed"), the missing proof
  and the stop condition.
- THE SYSTEM SHALL close the decision record with a P1 security approval
  request that states which evidence is still missing.
- WHILE any node of the chain lacks its proof THE SYSTEM SHALL keep P1 marked
  BLOCKED in:
  - the decision record;
  - `docs/runbooks/glovo-m1.md`;
  - `deploy/staged/glovo-m1/gate.yaml`, which keeps `p1.state: blocked`.
- IF a fact cannot be observed read-only (for example the registered
  Temporal namespaces, connected clients, live node allocatable, or the
  mctl-api#934 release hold) THEN THE SYSTEM SHALL record it as
  `NOT_OBSERVED` and as blocking, never as absent.
- IF any change in this proposal touches a reconciled path under
  `platform-gitops/` (other than `agents-state/`), the Temporal Helm values,
  `allow-temporal-ingress` or the namespace bootstrap Job THEN review SHALL
  reject it as out of scope.
- WHEN `docs/runbooks/glovo-m1.md` and `deploy/staged/glovo-m1/CROSSWALK.md`
  are updated THE SYSTEM SHALL link them to the decision record, and the
  `glovo-m1` CI job (`scripts/validate-glovo-m1-staging.py`) SHALL still pass.

## Out of scope

- Any production Temporal change. This includes TLS, authorizer, dynamic
  config, NetworkPolicy, namespace registration and Helm values.
- Creating nodes, Kubernetes namespaces, Temporal namespaces, Vault roles,
  signing keys, ExternalSecrets or any secret.
- Deploying the disposable canary (node F). Only its entry and exit criteria
  are referenced here.
- Approving P1, any release, or any digest. This proposal produces an
  approval request, not an approval.
- Re-running the #2469 investigation, or changing ADR 0003's status
  (it stays `Proposed`).
- Replacing the obsolete staged provider artifacts (CROSSWALK M14-M16). That
  belongs to the P1 prep PR.

## Open questions

- The live registered Temporal namespaces, the connected clients and the
  live node allocatable are not observable with read-only `get` access. They
  remain NOT_OBSERVED and blocking until an operator supplies dated output.
- The status of the mctl-api#934 release hold is not recorded anywhere in
  this repository. The decision record will list it as an unverified
  dependency that node G must re-check.
- The final name of the control Temporal namespace is undecided
  (`mctl-assistants` is the staged proposal), and so is whether mctl-api
  gets `mctl-assistants:write` on the same identity as its
  `mctl-agents:write`. The decision record proposes one mctl-api identity
  holding both permissions; node I decides.
- Node C (the JWKS trust path, #2540) is unresolved. The stock key provider
  supports only `http.Get` with system roots, and Vault listens in plaintext.
  Until node C is decided the policy table's JWKS column stays an
  unresolved gate.
- The issue does not say who the "independent owner" approver is. The
  decision record names the role (platform security admin), not a person.
- The default of `system.enableCrossNamespaceCommands` in v1.31.0 has not
  been read from source. Whether node G must set it explicitly is recorded
  as a question for node G.
