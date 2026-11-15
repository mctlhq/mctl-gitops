# Design: issue-2469-spike-temporal-live-read-only-client-rba

## Current state

The authorization posture today, from files read in the clone at mctl-gitops
commit `f799c247743979e98c27cbe5d7c1d37753bb9057` (2026-11-08):

- `platform-gitops/bootstrap/templates/data/temporal.yaml`: Argo CD
  Application `temporal`, chart `temporal` from `https://go.temporal.io/helm-charts`
  at `targetRevision: 1.2.0` (comment: server appVersion 1.31.0),
  `server.replicaCount: 1`, frontend `ClusterIP`. Persistence points at
  `shared-pg-rw.platform-db.svc.cluster.local:5432`, databases `temporal` and
  `temporal_visibility`, with `numHistoryShards: 512`. The values contain no
  `global.tls`, `server.config.tls`, `global.authorization` or
  `internalFrontend` keys. Admintools runs image `temporalio/admin-tools:1.31.0`.
  A second source is `platform-gitops/infra-components/data/temporal/`.
- `platform-gitops/infra-components/data/temporal/networkpolicy.yaml`:
  `allow-temporal-ingress` admits port 7233 only from the `mctl-api` namespace,
  from `admins` pods with instance `admins-mctl-agents-worker{,-exec,-implement}`,
  and from `labs` pods with instance `labs-kuptsi-app`. Intra-namespace traffic
  is open. Traefik may reach 8080 and monitoring may reach 9090. Its header
  states plainly: "the network is the only boundary".
- `platform-gitops/infra-components/data/temporal/tenant-namespace-job.yaml`:
  Job `temporal-namespaces-bootstrap` (`admin-tools:1.31.0`) creates the
  Temporal namespaces `kuptsi` and `mctl-agents` and their search attributes.
  This is the only cluster-scope admin caller in Git.
- `platform-gitops/bootstrap/templates/data/temporal-web.yaml`: `temporalio/ui`
  `2.49.1` through base-service, with `TEMPORAL_ADDRESS` set to the frontend
  on 7233 and `TEMPORAL_DEFAULT_NAMESPACE: kuptsi`. It sends no token; Backstage
  forward-auth (tenant `admins`) protects the HTTP edge.
- `platform-gitops/bootstrap/templates/core-infra/vault.yaml`: Vault chart
  `0.28.1`, 3 Raft replicas, listener `tls_disable = 1` (comment: "SOC F15
  accepted residual: east-west Vault is plaintext ... not a contained
  rollback"). `platform-gitops/platform-skills/catalog/mctl-platform/references/vault.md`
  repeats this. **Consequence for this spike:** a JWKS URI on
  `http://vault(-active).vault.svc...` fails ADR 0003 decision 4. No
  in-cluster authenticated JWKS source exists in Git today.
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`:
  `TEMPORAL_ADDRESS` is the frontend on 7233 and `TEMPORAL_NAMESPACE` is
  `mctl-agents`. `VAULT_ADDR` is `http://vault-active.vault.svc.cluster.local:8200`.
  The comment there explains why `https://secrets.mctl.ai` (behind Cloudflare)
  was abandoned after the 2026-10-09 readiness outage.
- `docs/adr/0003-temporal-client-authz.md` (Proposed) and
  `docs/runbooks/temporal-client-auth.md`: these hold the candidate decisions,
  the client inventory, negative tests T1-T11 and downstream items 3-10. Every
  live-evidence row says `not observed`.
- The earlier proposal for #2456 is under
  `platform-gitops/agents-state/mctl-gitops/proposals/issue-2456-security-temporal-authenticate-and-autho/`.
  This spike fills the evidence gaps it left open.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml`:
  image tag `1.117.0`, `TEMPORAL_ADDRESS` set to the frontend on 7233,
  `TEMPORAL_NAMESPACE: mctl-agents`, and entrypoint
  `python -m orchestrator.temporal.worker --role {control,execution,implementation}`.
  None sets a token or TLS env var.
- `$MCTL_GITOPS_ROOT/services/labs/kuptsi-app/values.yaml`: tag `0.2.27`.
  The app and its `temporal-worker` sidecar (`python -m src.temporal.worker`)
  both use `TEMPORAL_NAMESPACE: kuptsi`, with no token or TLS env var.
- `mctl_get_service_config(admins, mctl-agents-worker)`: imageTag `1.117.0`.
- `mctl_get_service_config(labs, kuptsi-app)`: imageTag `0.2.27`, host
  `labs-kuptsi-app.mctl.ai`.
- `mctl_list_services(admins)`: complete=true. The three
  `mctl-agents-worker*` services are Synced, running image
  `ghcr.io/mctlhq/mctl-agents:1.117.0`. temporal-web and temporal are not
  listed: they are platform Applications in the `temporal` namespace, not
  tenant catalogue services.
- **Not observed:** the running Temporal server image, the rendered
  `temporal-config` ConfigMap, the registered namespaces, connected clients and
  frontend metrics. No read-only tool in this run reaches the `temporal`
  Kubernetes namespace. These are `BLOCKED_NO_ACCESS`, not absent.
- **Not observed:** the SDK versions inside mctl-api 4.154.0, mctl-agents
  1.117.0 and kuptsi-app 0.2.27. Those lock files live in other repos and
  were not cloned here.

## Proposed solution

Docs only. The implementer edits or creates Markdown under `docs/` and nothing
else.

1. **Evidence inventory.** Rewrite the "Live evidence" table in
   `docs/runbooks/temporal-client-auth.md` with the columns Item | Source
   (path@commit, URL@tag, or command) | Version | Observed (date, by whom) |
   Status. The status values are `VERIFIED_SOURCE`, `VERIFIED_LIVE`,
   `BLOCKED_NO_ACCESS` and `BLOCKED_JWT_SEMANTICS`. GitOps-desired-state rows
   (chart 1.2.0, server 1.31.0, no TLS/authorizer keys, NetworkPolicy peers,
   client tags, Vault `tls_disable = 1`) become `VERIFIED_SOURCE` at the pinned
   commit. That proves desired state only, not the running state. Live rows keep
   their read-only command and become `VERIFIED_LIVE` only if an operator
   supplies dated output. SDK rows cite the lock file at the deployed tag in
   mctl-api, mctl-agents and kuptsi-app if they can be read, and are
   `BLOCKED_NO_ACCESS` otherwise. Chart capability (`server.config.tls`,
   `internalFrontend`, `global.authorization`) is checked against the chart
   1.2.0 `values.yaml` in `temporalio/helm-charts` at that tag.

2. **Role/RPC matrix:** new `docs/runbooks/temporal-authz-role-matrix.md`.
   The source is `temporalio/temporal` at tag `v1.31.0`: the default
   authorizer, the default JWT claim mapper, the default JWT key provider, and
   the API method metadata table (scope namespace/cluster, access
   read/write/admin), each cited with file and line ranges. The table rows are
   the RPCs listed in requirements.md. The columns are `<ns>:read`,
   `<ns>:write`, `<ns>:worker`, `<ns>:admin`, `temporal-system:read` and
   `temporal-system:admin`. Each cell is allow, deny, or "unclear — canary".
   Explicit statements: there is no task-queue dimension; how
   `temporal-system` scope is matched; what `worker` actually grants. Then
   re-check the ADR candidate permission map against the matrix and flag
   mismatches. ADR 0003 is not edited beyond a pointer.

3. **JWT semantics section** (in the matrix doc). From 1.31.0 source and
   config docs, record: the `permissionsClaimName` and permissions format;
   whether `iss` is validated; whether audience is validated, against which
   config key, and whether an empty setting disables the check; and the key
   source (`keySourceURIs`, refresh interval, supported URI schemes, and
   whether a file or pinned-key option exists). Vault side, from Vault docs
   for the deployed chart's server version: the `identity/oidc/role`
   template, `aud` (client_id) behaviour, `ttl`, the `verification_ttl` of the
   key, and whether the JWKS endpoint `/v1/identity/oidc/.well-known/keys` is
   reachable only over the plaintext listener in-cluster. ESO
   `VaultDynamicSecret` is checked for compatibility with a GET token endpoint
   and a refresh interval. Any point the source cannot settle becomes
   `BLOCKED_JWT_SEMANTICS` with a minimal reproducible canary test.

4. **Canary contract:** new `docs/runbooks/temporal-auth-canary.md`.
   - Isolation: a separate Helm release and Kubernetes namespace (name proposed
     only, e.g. `temporal-canary`, not created). It has its own CNPG
     database/role or an ephemeral Postgres, never `temporal`/`temporal_visibility`.
     It has its own NetworkPolicy allowing only canary test pods. Temporal
     namespaces `canary-control`, `canary-provider-a` and `canary-kuptsi` use
     synthetic identities. The signing key and Vault role are canary-only and
     are created in a downstream issue. Nothing reaches production
     `temporal-frontend:7233`.
   - The same `global.authorization`/TLS values that production would get,
     version-pinned to chart 1.2.0 / server 1.31.0.
   - The test suite maps ADR T1-T11 to steps, each with its expected gRPC code:
     no token; expired; unknown kid; forged signature; wrong `iss`; wrong or
     empty `aud`; a plaintext-HTTP JWKS configuration that must be refused at
     review time; provider->control denial; kuptsi->DevLoop denial
     (start/signal/terminate/poll `mctl-dev-loop`); non-admin namespace/cluster
     APIs; UI identity writes; revocation within 1 TTL; key rotation; no
     `eyJ` in logs.
   - Gates: entry (the matrix has no unresolved cell for a permission the map
     uses); exit (all tests pass twice, and rollback, i.e. reverting
     `global.authorization` and then TLS, is rehearsed and restores
     unauthenticated access within N minutes); SLO continuity, where
     production DevLoop and kuptsi workflow success rate and p95 latency over 24h
     before and after each downstream phase stay within a stated tolerance.
     Stop conditions: any T-test fails; audience or issuer enforcement is not
     demonstrable; the production SLO regresses.

5. **Dependency DAG and downstream issues** (section in the runbook,
   replacing items 3-10 with structured entries). The nodes are: A client
   support (mctl-api, mctl-agents, kuptsi-app; env-gated, inert when unset);
   B frontend metrics plus alerts; C JWKS trust path decision (pinned key vs
   Vault TLS; architecture review); D credential plumbing in shadow (Vault/ESO,
   depends on C); E frontend TLS (depends on A); F disposable canary (depends on
   C, E, matrix); G authorizer enablement (depends on A, B, D, E, F);
   H production negative proof (G); I `mctl-assistants*` namespaces (H); J
   optional temporal-web identity (admin-only risk acceptance). Each node
   lists repo, owner, mandatory reviewers, approval gate, rollback, sequencing
   and stop condition. A text DAG (Mermaid or ASCII) is included.

6. **Recommendation** (top of the runbook). The expected outcome given
   current evidence is `BLOCKED` for any authorizer, TLS or credential phase,
   with labels `BLOCKED_NO_ACCESS` (live server rows) and possibly
   `BLOCKED_JWT_SEMANTICS` (issuer/audience, plus JWKS over plaintext Vault).
   It is also `READY_FOR_SEPARATE_CLIENT_SUPPORT_PROPOSAL` for node A only,
   because env-gated client support is inert in production. The implementer
   writes the final verdict from the evidence actually gathered and lists the
   unresolved unknowns. The web UI note states that `temporal-system:read`
   implies read across all namespaces and stays deferred.

## Alternatives

1. **Run the inventory live from this DevLoop (kubectl in the agent pod).**
   Dropped: agent pods must not hold cluster or Temporal credentials (ADR 0003
   "Known limits"), and the issue forbids new credentials. Live rows are
   operator-supplied or stay `BLOCKED_NO_ACCESS`.
2. **Prove issuer/audience by negative tests on production with a token
   flag.** Dropped: the issue explicitly forbids live negative tests against
   production, and enabling an authorizer on the shared frontend risks
   DevLoop and kuptsi.
3. **Fold the canary design into ADR 0003 itself.** Dropped: the ADR is
   a decision record under review. A separate runbook keeps the ADR stable and
   lets the canary contract be revised per downstream issue.

## Platform impact

- No migration and no runtime, resource or ArgoCD change. Only three
  Markdown files under `docs/runbooks/` change; `validate-manifests.yml` is
  unaffected.
- Backward compatibility: no change.
- Risk: the docs overstate readiness. Mitigation: a status vocabulary in which
  desired state in Git is never `VERIFIED_LIVE`, explicit dated sources, and
  ADR 0003 stays Proposed.
- Risk: matrix errors from reading upstream source. Mitigation: line-cited
  references at tag `v1.31.0`, and every unclear cell routed to a canary test
  instead of an assumption.
- Risk: the JWKS finding (plaintext Vault) could tempt a reviewer to accept
  `http://`. Mitigation: the docs mark it as a hard stop and send it to
  decision node C.
