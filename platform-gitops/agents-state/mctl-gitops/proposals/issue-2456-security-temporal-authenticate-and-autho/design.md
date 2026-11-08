# Design: issue-2456-security-temporal-authenticate-and-autho

## Current state

### Temporal server (GitOps desired state)

- `platform-gitops/bootstrap/templates/data/temporal.yaml` defines an Argo CD Application with two sources:
  - The upstream chart `temporal` 1.2.0 (server 1.31.0) with `replicaCount: 1`, persistence on shared-pg, and the frontend as a `ClusterIP` Service. The values contain no `global.tls`/`server.config.global.tls` block and no `global.authorization` (claim mapper or authorizer). The frontend therefore serves plaintext gRPC on 7233 and authorizes nothing. `web.enabled: false`; `admintools` is enabled (image `temporalio/admin-tools:1.31.0`).
  - The in-repo path `platform-gitops/infra-components/data/temporal/` with three files:
    - `externalsecret.yaml`: DB credentials from Vault `platform/temporal/database` through `ClusterSecretStore vault-backend`.
    - `tenant-namespace-job.yaml`: a PostSync Job that runs `temporal operator namespace create` for `kuptsi` (7d) and `mctl-agents` (30d) and registers search attributes (`LeadId`, `Service`, `IssueNumber`, `AgentVersion`). It connects to the frontend with no credential. Once authorization is enabled it needs an admin identity.
    - `networkpolicy.yaml`: `allow-temporal-ingress`. The header states the threat ("the Temporal frontend has no client authentication ... any tenant pod can start, signal, query or terminate workflows in any Temporal namespace"). Ingress on 7233 is limited to the `mctl-api` namespace, the `admins` pods with instance `admins-mctl-agents-worker{,-exec,-implement}`, and `labs` `labs-kuptsi-app`. Port 9090 (metrics) is open only to `monitoring`, and the header notes "No scrape of the Temporal server today".
- `platform-gitops/bootstrap/templates/data/temporal-web.yaml`: the Temporal UI 2.49.1 on base-service, with `TEMPORAL_ADDRESS` set to the frontend and Backstage forward-auth (`tenant=admins`). Write actions are not disabled, so any user who passes forward-auth can terminate or reset workflows through the UI.

### Clients (GitOps desired state)

| Client | Where | Temporal namespace | Notes |
|---|---|---|---|
| mctl-api | `bootstrap/templates/mctl-platform/mctl-api.yaml` (`TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE: mctl-agents`) | mctl-agents | Go SDK; starts, signals and queries DevLoop; a nil client degrades to 503 |
| mctl-agents-worker (`--role control`) | `services/admins/mctl-agents-worker/values.yaml` | mctl-agents | Python SDK; poller and schedules; already reads `GITHUB_TOKEN_FILE` from a mounted file |
| mctl-agents-worker-exec (`--role execution`) | `services/admins/mctl-agents-worker-exec/values.yaml` | mctl-agents | submits Argo CWFTs |
| mctl-agents-worker-implement (`--role implementation`) | `services/admins/mctl-agents-worker-implement/values.yaml` | mctl-agents | |
| kuptsi-app API + `temporal-worker` sidecar | `services/labs/kuptsi-app/values.yaml` (two env blocks) | kuptsi | tenant workload in `labs` |
| temporal-web | `temporal-web.yaml` | all (default `kuptsi`) | human UI |
| namespaces bootstrap Job, admintools | `tenant-namespace-job.yaml`, chart | system | operator API |

### Supporting infrastructure in the repo

- cert-manager is present (`bootstrap/templates/core-infra/cert-manager-dns01.yaml`; `letsencrypt-prod` is used by ingresses). No in-cluster CA `ClusterIssuer` was found.
- `bootstrap/templates/core-infra/reflector.yaml` can copy a CA-bundle Secret or ConfigMap into client namespaces.
- Vault and ESO are in place (`ClusterSecretStore vault-backend`). `bootstrap/templates/core-infra/vault-netpol.yaml` admits only ESO, traefik, mctl-api and Argo workflow pods. It states that nothing in `admins` addresses Vault. Clients therefore must not call Vault directly: ESO is the delivery path, which keeps the Vault netpol unchanged.
- The worker alert rules in `infra-components/observability/vm-rules/mctl-agents-worker-alerts.yaml` are built on Temporal SDK metrics (`temporal_activity_schedule_to_start_latency`, `temporal_worker_task_slots_available`). These are the SLO guard during rollout.
- Credential-delivery conventions are in `docs/runbooks/agent-credential-delivery.md` (file-mounted tokens, inventory and CI validator). They are referenced in CLAUDE.md.

### Deployed state checked

- `mctl_get_service_status admins/mctl-agents-worker`: Healthy, Synced, image tag 1.117.0.
- `mctl_list_services admins`: complete=true. `mctl-agents-worker`, `-exec` and `-implement` all run `ghcr.io/mctlhq/mctl-agents:1.117.0`, so all three Python worker roles ship in one image.
- `mctl_get_service_config labs/kuptsi-app`: image 0.2.27, port 5000, base-service, has a database.
- Not observed: the live Temporal frontend config, the registered Temporal namespaces, the server image actually running, the SDK versions of connected clients, and whether any TLS is active. This run has no read access to the `temporal` namespace or to the frontend. These values are not assumed to match GitOps; task 1 collects them.
- Not observed: the live mctl-api pod env (it is not a tenant catalogue service). Only GitOps desired state was read.

## Proposed solution

### Principle: two layers, both required

1. **Temporal machine/namespace authorization (this proposal).** It answers which workload may call which Temporal API on which Temporal namespace. It is enforced in the Temporal frontend by a ClaimMapper and an Authorizer.
2. **mctl-api principal/tenant/order authorization (unchanged, separately required).** It answers which human or tenant principal may cause mctl-api to start or signal a given workflow. Temporal never sees end users. Inside one shared namespace, Temporal cannot tell tenant A's workflow from tenant B's, so mctl-api remains the only place that enforces this.

### What Temporal 1.31.0 can and cannot enforce

- It supports pluggable `ClaimMapper` and `Authorizer` interfaces. The stock binary ships `claimMapper: default`, which reads a JWT, verifies it against JWKS from `jwtKeyProvider.keySourceURIs`, and parses a `permissions` claim of the form `<namespace>:<role>`. It also ships `authorizer: default`, which checks the API's required role against the caller's role on the target namespace, plus `system:*` for cluster APIs.
- The granularity is namespace by role (read / write / worker / admin). The default authorizer has no task-queue dimension. A writer on a namespace can poll any queue in it and can start, signal or terminate any workflow in it. **Queue-level isolation is therefore not promised.** Isolation comes from separate Temporal namespaces per trust domain, with the NetworkPolicy allowlist kept as a second layer.
- mTLS alone authenticates the transport, but the stock server has no built-in cert-to-namespace claim mapper. Mapping a certificate SAN to permissions needs a custom ClaimMapper, which means a custom server build.
- With an authorizer configured, the server's own system worker must reach the frontend through `internalFrontend`, or with a system identity. Task 1 confirms that chart 1.2.0 supports `server.internalFrontend.enabled`.

### Selected design (to be ratified by the ADR, task 2)

**AMEND boundary:** this proposal can only research and document the decisions below. All Vault, ESO, SDK, frontend TLS/auth, monitoring and cluster operations are future independently approved slices. No phase 1-5 rollout follows automatically from approving this ADR. The role names below are *candidate claims*, pending a source-backed Temporal 1.31.0 RPC-per-role negative-test matrix.

**Identity (candidate; unverified until live inventory):** short-lived JWTs (TTL <=1h) signed by Vault's identity engine (`identity/oidc/key/temporal`, `identity/oidc/role/temporal-<client>`). Each role template emits `permissions`, a stable expected `iss`, and exactly pinned `aud: temporal-frontend`. Confirm that the stock server 1.31.0 **actually enforces** the chosen non-empty audience/issuer setting and that the Vault token endpoint+ESO generator emit these fields, with canary negative tests; otherwise STOP, no enablement. Do not treat setting `aud` on a token as proof that the server validates it.
- Each client has its own Vault Kubernetes-auth role, bound to its own ServiceAccount. Each role maps to its own entity, whose metadata holds the permission list. The template reads `{{identity.entity.metadata.temporal_permissions}}`, so the permission list is Vault config, not something the client asserts.
- Delivery uses an ESO `VaultDynamicSecret` generator (`GET identity/oidc/token/temporal-<client>`, authenticated with the client's SA through `kubernetes` auth). An `ExternalSecret` in the client's namespace uses `refreshInterval: 20m` and `dataFrom.sourceRef.generatorRef`. The token is mounted as a file at `/var/run/secrets/temporal/token`, following the `GITHUB_TOKEN_FILE` pattern in `services/admins/mctl-agents-worker/values.yaml`.
- Clients re-read the file at least every 5 minutes. The Go SDK uses a `HeadersProvider`/`Credentials` that rereads the file; the Python SDK updates `client.api_key` or `rpc_metadata` from a background task. These are code changes in mctl-api, mctl-agents and kuptsi-app, landed first behind env `TEMPORAL_TOKEN_FILE` (unset means no header), so they are safe to ship before the server enforces anything.
- The frontend must verify JWTs against **authentically delivered JWKS**: prefer an HTTPS issuer/JWKS endpoint with explicit CA verification, or a separately reviewed pinned-key distribution. The previous proposed `http://vault-active.vault.svc.cluster.local:8200/...` URI is **NOT APPROVED**: unsigned/unauthenticated JWKS transport allows trust-key substitution despite the key material itself being public. Task 1/ADR must prove Vault HTTPS support, issuer/JWKS URL, trust roots and refresh/rotation behaviour in the deployed chart before choosing the exact URL; restrict Vault NetworkPolicy ingress to the minimum required path/workloads.
- Vault rotates the signing key on a schedule (`rotation_period: 24h`, `verification_ttl` at least 2x token TTL), so old tokens validate until they expire.
- Revocation: delete or disable the client's Vault role or entity. ESO then cannot mint new tokens, and access ends within at most one TTL (1h). For an emergency stop, rotate the key with `verification_ttl` shortened, which invalidates every token. Document this as a break-glass step.

**Transport:** TLS on frontend 7233.
- A new `ClusterIssuer temporal-internal-ca`, a self-signed bootstrap CA certificate in `cert-manager`, and a `Certificate temporal-frontend-tls` in `temporal` with SANs `temporal-frontend.temporal.svc.cluster.local` and `temporal-frontend.temporal.svc`, and a 90d duration with renewal 30d before expiry.
- The CA bundle (public cert only) is reflected to `mctl-api`, `admins` and `labs` through reflector annotations.
- Chart values: `server.config.tls.frontend.server` (cert and key from the Secret mount) with `requireClientAuth: false`. Client mTLS is not required, because identity comes from the JWT. Clients set `TEMPORAL_TLS_CA_FILE` and the TLS server name.
- Bearer tokens must never cross the wire in plaintext, so TLS is enabled before the authorizer.

**Least-privilege permission map (Vault entity metadata):**

| Identity (Vault role / K8s SA) | permissions claim |
|---|---|
| `temporal-mctl-api` (mctl-api SA) | `["mctl-agents:write"]` |
| `temporal-mctl-agents-control` / `-exec` / `-implement` (one SA each) | `["mctl-agents:write"]` (narrowed to `worker` if task 1 proves the role restricts start/terminate) |
| `temporal-kuptsi` (kuptsi-app SA, shared by both containers) | `["kuptsi:write"]` |
| `temporal-web` | **DEFER / no assumed token in M0.** Stock UI requests cluster read APIs requiring `temporal-system:read` (grants read across **all** namespaces). Either accept an explicitly admin-only read-all UI or separately review a narrower authorizer/proxy; disabling write buttons is NOT sufficient to prove API-side read-only. |
| `temporal-bootstrap` (the Job's SA in `temporal`) | `["temporal-system:admin"]`, mounted only into `temporal-namespaces-bootstrap` |
| Future `temporal-assistants-control` | `["mctl-assistants:write"]` |
| Future `temporal-provider-<name>` (e.g. Glovo) | `["mctl-assistants-provider-<name>:write"]` only. It never gets a role on `mctl-assistants` or `mctl-agents`. Control-to-provider handoff crosses namespaces through mctl-api or Nexus, as the ADR decides. |

Unknown issuer, missing token, expired token, wrong `aud`, or no matching namespace permission: the default authorizer denies.

**Credentials never reach an LLM.** The token Secret is mounted only into the long-running worker Deployments and mctl-api. It is never mounted into Argo CWFT agent pods (`cwft-mctl-agents-investigate`/`-implement`), never passed as a workflow or activity argument, and never logged. The token inventory in `docs/runbooks/agent-credential-delivery.md` gains rows for the Temporal token, and its CI validator checks that the volume appears only on the listed workloads. The UI token stays server-side in temporal-web.

**Observability:**
- A new `VMServiceScrape` for the `temporal` frontend on 9090, which `networkpolicy.yaml` already allows from `monitoring`.
- New rules in `infra-components/observability/vm-rules/temporal-authz-alerts.yaml` with promtool tests under `vm-rules/tests/`:
  - `TemporalAuthzDenials`: frontend `service_error_with_type{error_type=~".*PermissionDenied.*|.*Unauthenticated.*"}` rate above 0 for 10m, by namespace and operation;
  - `TemporalTokenStale`: the ESO `externalsecret_status_condition{condition="Ready",status="False"}` for the `temporal-token-*` ExternalSecrets for 15m;
  - `TemporalFrontendCertExpiring`: cert-manager `certmanager_certificate_expiration_timestamp_seconds` within 14d.

### Phases (each a separate DevLoop proposal, approval and PR; only phase 0 in this proposal)

**Stop condition:** never enable TLS cutover or authorizer based solely on this proposal's approval. Require independently approved per-phase work items; review the actual chart-rendered config, Vault token semantics and SDK client support; fail closed when issuer, audience, role mapping or authenticated JWKS cannot be demonstrated. A disposable canary with actual negative authorization tests is mandatory before phase 3. A written maintenance window alone is not an adequate substitute.

0. **ADR and live inventory.** No runtime change.
1. **Credential plumbing in shadow.** Vault roles and the JWKS key, ESO generators, token files mounted, clients send tokens through `TEMPORAL_TOKEN_FILE`. The server still has no authorizer, so tokens are ignored. Shadow evidence: each client logs a hash of its token's `sub` and expiry (never the token itself), and a one-off `temporal` CLI check with a token validates against **TLS-authenticated JWKS** offline and checks issuer/audience/role mappings.
2. **Frontend TLS cut-over.** Every client and the bootstrap Job switch to TLS in the same sync window as the server values. Plaintext and TLS cannot share 7233, so a short reconnect is expected. Workers and SDK clients retry, and workflows are durable.
3. **Authorizer on (AFTER successful disposable canary).** Set `server.config.global.authorization` with `jwtKeyProvider`, `permissionsClaimName: permissions`, `authorizer: default`, `claimMapper: default`, and `internalFrontend` enabled. This flip is preceded by validation on a disposable canary Temporal release, or a scheduled window (an ADR decision; see Open questions).
4. **Negative proof.** Run the test matrix (tasks.md T-series) against production, store the evidence in the ADR, and close the activation gates.
5. **Later, separately approved, out of this proposal.** Register the `mctl-assistants*` namespaces and identities.

## Alternatives

1. **NetworkPolicy only (status quo, #1810/#1818).** Dropped. It cannot tell apart two clients that are both allowed to connect, and it cannot express per-namespace or per-operation rights. kuptsi can already reach `mctl-agents`, and a shared assistants runtime would put trusted and low-trust workers behind the same reachable port.
2. **mTLS client certificates with a custom ClaimMapper (cert SAN to permissions).** This is strong transport identity, and cert-manager can issue and rotate the certificates. Dropped as the primary choice because the stock server cannot map certificates to namespaces: it needs a custom Temporal server image to build, patch and track on every upgrade. It remains an ADR fallback. Frontend TLS from the selected design is reused either way.
3. **Projected Kubernetes ServiceAccount tokens with a custom ClaimMapper.** No Vault or ESO in the path, and kubelet rotates the tokens. Dropped for the same custom-build reason. SA tokens carry no `permissions` claim, so the mapping would have to live in server code or config outside Vault.
4. **An authorizing gateway in front of the frontend (Envoy ext_authz or a proxy parsing gRPC methods and namespace fields).** Dropped. Namespace lives inside protobuf request bodies, so a gateway would have to decode every Temporal API. It also creates a bypass risk if any client reaches the frontend directly, and it adds a hot-path component to DevLoop.
5. **Separate Temporal clusters per trust domain.** This is the strongest isolation. Dropped for now on resource grounds: each cluster needs about 1.5Gi requests plus its own shared-pg databases on k3s-preview. It can be revisited for a high-risk provider if namespace isolation is judged insufficient.

## Platform impact

- **Backward compatibility:** phases 1 and 2 are NOT automatically additive: plaintext-to-TLS cutover at the single frontend port is a coordinated breaking change. It needs verified client image versions, no-unknown-client inventory, observed continuity, a canary and a rollback drill before separate approval. Phase 3 is breaking for any client without a valid token, including clients not in the inventory. Task 1 checks frontend connection metrics and logs for unexpected callers before phase 3.
- **Cross-repo dependencies:** mctl-api (Go: token file, TLS CA), mctl-agents (Python: token refresh, TLS), kuptsi-app (Python, both containers). Each must release with `TEMPORAL_TOKEN_FILE`/`TEMPORAL_TLS_CA_FILE` support before phase 1 and 2 values are set. Setting the env on an image that ignores it is a no-op, which is safe.
- **Resources:** negligible. ESO refreshes add a few Vault calls per client per hour, the CA and certificates are tiny, and the frontend fetches JWKS every minute. An optional canary Temporal release would add about 1.5Gi memory requests temporarily.
- **Risks and mitigations:**
  - Vault outage. JWKS is cached in the frontend and tokens live 1h with a 20m refresh, so there is about 40m of tolerance. `TemporalTokenStale` alerts.
  - System worker broken by the authorizer. Mitigated by `internalFrontend`, validated in the canary or window first.
  - temporal-web loses write actions. This is intended. Operators use the `temporal` CLI with a short-lived admin token minted on demand from Vault by a human (Vault human auth).
  - Bootstrap Job holds `temporal-system:admin`. The token is scoped to the Job's SA in the `temporal` namespace and lives 1h.
  - Role semantics differ from expectation. The negative matrix (T1–T10) is the gate. Nothing is declared isolated without a recorded denial.
- **Rollback:** each phase is one revertible commit. Reverting the authorizer values restores the current behaviour, and the NetworkPolicy remains as the floor. See tasks.md.
