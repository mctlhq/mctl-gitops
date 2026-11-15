# Design: issue-2568-security-glovo-canary-choose-and-prove-t

## Current state

### Temporal desired state (this repository)

- `platform-gitops/bootstrap/templates/data/temporal.yaml` defines the Argo CD
  Application `temporal`:
  - chart `temporal` 1.2.0 (server appVersion 1.31.0), `replicaCount: 1`;
  - persistence on `shared-pg-rw.platform-db` (databases `temporal` and
    `temporal_visibility`, `numHistoryShards: 512`);
  - frontend Service of type `ClusterIP`;
  - no `server.config.tls` and no `server.config.authorization`;
  - `admintools` 1.31.0, Web UI disabled (it is shipped separately in
    `temporal-web.yaml`);
  - the second source is `platform-gitops/infra-components/data/temporal/`.
- The server's resource requests in that file come to about 1.5Gi memory and
  400m CPU:
  - frontend: 100m / 256Mi;
  - history: 100m / 768Mi;
  - matching: 100m / 256Mi;
  - worker: 100m / 256Mi;
  - admintools adds 50m / 64Mi.
  This is the real price of a second, isolated cluster (route B). It matches
  ADR 0003 alternative 5 ("about 1.5Gi requests each").
- `platform-gitops/infra-components/data/temporal/networkpolicy.yaml`
  (`allow-temporal-ingress`) admits port 7233 only from:
  - the `mctl-api` namespace;
  - `admins` pods `admins-mctl-agents-worker{,-exec,-implement}`;
  - `labs` pod `labs-kuptsi-app`.
  Its header states that the network is the only boundary until client auth
  exists.
- `platform-gitops/infra-components/data/temporal/tenant-namespace-job.yaml`
  registers the Temporal namespaces `kuptsi` and `mctl-agents`.
- `infrastructure/k3s-preview/kube.tf` (desired, Terraform) declares 1 node of
  `cx33` and 3 nodes of `cx43`. The live allocatable is not in Git.

### Existing security work this issue builds on (not duplicated)

- `docs/adr/0003-temporal-client-authz.md` (Proposed) contains:
  - the identity design: Vault identity JWT, TTL <= 1h, delivered by ESO;
  - the stock `default` claim mapper and authorizer;
  - TLS before the authorizer;
  - authenticated JWKS only;
  - `aud: temporal-frontend`;
  - a disposable canary that is required before enablement;
  - one Temporal namespace per trust domain;
  - the candidate permission map, which already lists
    `mctl-assistants:write` for "future assistants control";
  - negative tests T1-T11.
- `docs/runbooks/temporal-client-auth.md`:
  - verdict `BLOCKED`;
  - VERIFIED_LIVE rows from 2026-11-09 (plaintext gRPC, no
    `authorization:` block, empty dynamic config, NetworkPolicy matches
    desired state);
  - NOT_OBSERVED rows for registered namespaces and connected clients;
  - the DAG of nodes A-J, each with owner, gate, rollback and stop condition.
- `docs/runbooks/temporal-authz-role-matrix.md` records these source facts
  at v1.31.0:
  - `iss` is not validated;
  - `aud` is enforced only when configured non-empty;
  - JWKS is fetched via `http.Get` with system roots;
  - `worker` grants nothing;
  - there is no task-queue dimension.
- `docs/runbooks/temporal-auth-canary.md` is the canary contract:
  - release `temporal-canary` with a throwaway database and synthetic
    namespaces;
  - steps S1-S17 with their expected codes;
  - a rollback rehearsal and stop conditions.
- `docs/spikes/2506-temporal-jwt-issuer.md` gives the verdict
  `HYBRID_WITH_BOUNDARIES`: ZITADEL is not a Temporal issuer, and Vault
  identity remains the issuer candidate.

### Glovo M1 staging

- `docs/runbooks/glovo-m1.md` has a P1 checklist whose first item is "#2469
  live evidence filled (Temporal client authentication proven)".
- `deploy/staged/glovo-m1/gate.yaml` sets `p1.state: blocked`. CI ignores it
  as approval.
- `deploy/staged/glovo-m1/CROSSWALK.md`:
  - §4 "Minimal Temporal security path for P1" says that with
    mctl-telegram#1262 the provider holds no Temporal credential, so the
    only new Temporal clients are the control worker (#1044) and mctl-api;
  - nodes A (mctl-api#983, mctl-agents#1057), B (#2539) and C (#2540) are
    filed;
  - nodes D-I are not filed;
  - §5 lists the ordered gates to P1.
- `deploy/staged/glovo-m1/control-worker/values.yaml` has
  `TEMPORAL_NAMESPACE: mctl-assistants` and a credential from
  `teams/admins/assistants-control/temporal`.
- `deploy/staged/glovo-m1/provider-worker/values.yaml` and
  `netpol/worker-to-temporal.yaml` still assume a provider Temporal client.
  `README.md` and CROSSWALK M15 mark them obsolete.
- CI: the `glovo-m1` job in `.github/workflows/validate-manifests.yml` runs
  `scripts/validate-glovo-m1-staging.py`. It refuses Glovo references in
  `platform-gitops/**` outside `agents-state/`.

### Deployed state checked

- `mctl_get_service_config labs/kuptsi-app`: imageTag `0.2.27`, componentType
  `base-service`, hasDatabase true. This agrees with the #2469 inventory. It
  says nothing about Temporal auth.
- `mctl_get_resource_usage labs`:
  - requests.memory 4544Mi of 7Gi; requests.cpu 2250m of 4;
  - pods 19 of 30;
  - limits.cpu 10200m of 20; limits.memory 9984Mi of 16Gi.
  This is tenant quota only. It is not node allocatable.
- `mctl_list_incidents service=temporal`: no active incidents.
- Temporal server TLS and authorizer live state: not re-observed in this run.
  The tools are read-only and expose no `kubectl` access to the `temporal`
  namespace. The proposal relies on the dated VERIFIED_LIVE rows of
  2026-11-09 in `docs/runbooks/temporal-client-auth.md` and labels them as
  such.
- Registered Temporal namespaces, connected clients and live node
  allocatable: NOT_OBSERVED, as they are in the #2469 runbook. They stay
  blocking.
- mctl-api#934 release hold: NOT_OBSERVED. It is not referenced anywhere in
  this repository, and no read-only tool here reads mctl-api issues.

## Proposed solution

Add one decision record, `docs/runbooks/glovo-p1-temporal-isolation.md`. It
is the Glovo-specific P1 readiness view over the #2469 DAG and contains no
new investigation. Two existing docs get small cross-link edits. Nothing
under a reconciled `platform-gitops/` path changes.

### Decision record contents

1. **Verdict line.** `VERDICT: ROUTE_A_SELECTED; P1: BLOCKED`, with a
   pinned gitops commit and the date.

2. **Inventory.** Columns are item / desired (Git) / live / label / source.
   Rows are copied by reference from `temporal-client-auth.md`:
   - frontend TLS: none desired, none live (2026-11-09);
   - authorizer and claim mapper: none and none;
   - dynamic config: empty;
   - Temporal namespaces: desired `kuptsi` and `mctl-agents`; live
     NOT_OBSERVED;
   - clients: the 7 rows of the #2469 client inventory; live connections
     NOT_OBSERVED;
   - release and rollback: Argo CD automated sync with prune and selfHeal,
     `ServerSideApply`, and schema Job as a Sync hook. Rolling back a values
     change is a git revert; `numHistoryShards` can never change;
   - node capacity: desired 1 x cx33 plus 3 x cx43 from `kube.tf`; live
     allocatable NOT_OBSERVED; labs quota usage as read above.

   A new row covers Glovo itself: the provider holds no Temporal credential
   (mctl-telegram#1262, CROSSWALK §4). Its staged
   `netpol/worker-to-temporal.yaml` is obsolete and must not be activated.

3. **Decision matrix A vs B.**

   | Criterion | A: secure the shared frontend | B: isolated Temporal |
   |---|---|---|
   | DAG nodes needed for P1 | A, B, C, D, E, F, G, H, I (control namespace only) | C, D, E', F, G', H', plus new: separate release, DB, netpol, and a second Temporal client in mctl-api. A is still needed for mctl-api and the control worker |
   | Removes need for TLS/JWT/authorizer? | no | no. The issue forbids an unprotected separate frontend, so B repeats E/G on its own frontend |
   | No-new-nodes feasibility | yes (no new server pods) | unproven: about +1.5Gi / 400m requests plus admintools, a new CNPG DB on `shared-pg` and new connections; node allocatable NOT_OBSERVED |
   | DevLoop/kuptsi impact | high: G changes auth for live clients. Mitigated by A first (inert), the F canary, a maintenance window and the 24h SLO check | none on the shared cluster. But mctl-api still talks to the shared cluster, and #1044 needs mctl-api to signal into B |
   | Approval gates | per node A-I (existing DAG) | all of A's gates plus capacity, storage and network approval for a new platform component |
   | Ends the shared-cluster exposure (#2538)? | yes | no. DevLoop and kuptsi stay allow-all |

   Route A is selected. Route B shortens no node on the critical path: it
   needs its own E/F/G/H, and it adds work in mctl-api and capacity risk.
   Route B also leaves #2538 open. Per the issue, B stays a fallback only if
   A is materially slower *and* independently justified. The record lists
   what would trigger re-evaluation: node G is refused, or the canary shows
   the shared rollout cannot be done without DevLoop or kuptsi loss.

4. **Version-pinned policy.**
   - Pins: server 1.31.0; chart 1.2.0; mctl-api Go SDK 1.50.0 (tag 4.154.0);
     mctl-agents Python SDK 1.34.0 (tag 1.117.0); kuptsi SDK
     BLOCKED_NO_ACCESS.
   - Issuer: Vault identity (spike #2506). The server does not check `iss`,
     so issuer control is the signing key in the configured JWKS only.
   - Audience: `temporal-frontend`, configured non-empty.
   - JWKS: unresolved gate (node C, #2540). An `http://` URI is refused.
   - Caller table:

     | Caller | Permissions |
     |---|---|
     | mctl-api | `mctl-agents:write`, `mctl-assistants:write` |
     | mctl-agents-worker{,-exec,-implement} | `mctl-agents:write` |
     | Glovo control worker (#1044) | `mctl-assistants:write` |
     | kuptsi-app | `kuptsi:write` |
     | bootstrap Job | `temporal-system:admin` |
     | fake provider (#1262) | none, no token, not admitted on 7233 |
     | temporal-web | deferred (node J) |

   - Role-to-RPC: references `temporal-authz-role-matrix.md`. The record
     notes that the default authorizer has no task-queue dimension, so the
     control worker's isolation from DevLoop depends on its separate
     namespace.
   - Default deny:
     - missing, expired, unknown-kid, forged and wrong-aud or no-aud tokens
       (S1-S4, S6);
     - cross-namespace start, signal, query, list and terminate (S9-S12,
       S17);
     - provider to control or DevLoop: a NetworkPolicy timeout from the
       provider namespace, plus S9 with a synthetic provider identity.
     - Known accepted gap: the wrong-`iss` case (S5) is allowed by stock
       code. Security must accept that or STOP.

5. **Negative canary evidence.** The canary itself is
   `temporal-auth-canary.md` and is not restated. The record adds one Glovo
   synthetic namespace mapping: `canary-control` stands in for
   `mctl-assistants`, and `canary-provider-a` stands in for the
   provider-has-no-credential case. Evidence slots are dated, recorded twice
   and empty. Before any production change, two more checks are required:
   - production DevLoop and kuptsi SLO and history continuity (S15 and the
     24h SLO rule);
   - the mctl-api#934 release hold, re-checked.

6. **Dependency chain and missing proofs.** A table of nodes A-I. For each:
   owner, issue or PR (A: mctl-api#983 and mctl-agents#1057, with kuptsi-app
   not filed; B: #2539; C: #2540; D-I: not filed), missing proof and stop
   condition. Then the Glovo gates from CROSSWALK §5: the #1044 AMEND, the
   P1 issue under #2457, and `gate.yaml`, which stays blocked. Unknown
   remains blocking.

7. **P1 security approval request.** A closing section addressed to the
   platform security admin. It lists the exact evidence still missing and
   says no approval is granted by merging this document.

### Cross-link edits

- `docs/runbooks/glovo-m1.md`: in "P1 checklist", add the item "Route and
  evidence in `glovo-p1-temporal-isolation.md` complete (verdict no longer
  BLOCKED)". Change no other gate.
- `deploy/staged/glovo-m1/CROSSWALK.md`: below the §4 table, add one line:
  "Route decision: A (shared frontend), see
  `docs/runbooks/glovo-p1-temporal-isolation.md` (#2568)."
- `deploy/staged/glovo-m1/README.md`: add the related issue `#2568`.

The validator is unchanged. These paths are already outside the
CI-refused `platform-gitops/**` scope, and the new doc is under `docs/`.

## Alternatives

1. **Select route B now (isolated Temporal).** Dropped:
   - It does not remove nodes C-H, because an unprotected separate frontend
     is forbidden.
   - It adds a capacity, storage and network component whose no-new-nodes
     feasibility cannot be shown (allocatable NOT_OBSERVED).
   - It requires a second Temporal client in mctl-api.
   - It leaves the shared DevLoop and kuptsi exposure (#2538) in place.

   It is kept as a documented fallback with explicit re-evaluation triggers.
2. **Declare plain BLOCKED with no route.** Dropped: the evidence is enough
   to pick A on critical-path grounds. Not picking a route would stall
   filing nodes D-I. P1 still stays BLOCKED; only the route is chosen.
3. **Put the decision in the #2469 runbook or ADR 0003.** Dropped:
   - ADR 0003 must stay `Proposed`, and the #2469 runbook is the
     cluster-wide view.
   - A Glovo-specific readiness record keeps Glovo gates such as the
     provider-without-credential case and `gate.yaml` out of the general
     docs, and avoids rewriting their reviewed content.
4. **Add a CI check that pins the verdict string.** Deferred: `gate.yaml`
   is already not treated as approval, and a doc-string check gives no
   security guarantee. It can be revisited by the P1-policy PR that
   CROSSWALK §5 requires.

## Platform impact

- Migrations: none. Backward compatibility: documentation only. No reconciled
  manifest, Helm value, NetworkPolicy, namespace or secret changes.
- Resources: none.
- Risks and mitigations:
  - **A reader treats the record as approval.** The verdict line says
    `P1: BLOCKED`, the closing section says merge grants nothing, and
    `gate.yaml` is unchanged.
  - **The record drifts from the #2469 runbook.** Rows are cited by
    reference with their dates, not copied as new evidence.
  - **Unobserved facts are read as absent.** The NOT_OBSERVED label is
    used, and those rows are listed as blocking.
  - **The `glovo-m1` CI job breaks.** Only `docs/` and `deploy/staged/`
    markdown are edited, and the validator is run locally before the PR.
