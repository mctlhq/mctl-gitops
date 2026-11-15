# Design: issue-2506-spike-temporal-evaluate-zitadel-vs-vault

## Current state

### Temporal (desired state, all from #2469 documents)

- Chart `temporal` 1.2.0, server 1.31.0, no `global.tls`, no
  `global.authorization`: plaintext gRPC on 7233 and no authorizer
  (`platform-gitops/bootstrap/templates/data/temporal.yaml`, summarized in
  `docs/runbooks/temporal-client-auth.md`).
- The only boundary is NetworkPolicy `allow-temporal-ingress`
  (`platform-gitops/infra-components/data/temporal/networkpolicy.yaml`):
  7233 from `mctl-api`, `admins-mctl-agents-worker{,-exec,-implement}` and
  `labs-kuptsi-app`. The `temporal` namespace has no egress policy in this
  directory (`externalsecret.yaml`, `networkpolicy.yaml`,
  `tenant-namespace-job.yaml` only), so the frontend can reach a public JWKS
  host today (desired state; live egress `NOT_OBSERVED`).
- Temporal namespaces: `kuptsi`, `mctl-agents`
  (`tenant-namespace-job.yaml`). Clients: `TEMPORAL_ADDRESS` /
  `TEMPORAL_NAMESPACE` only, no token or TLS env
  (`services/admins/mctl-agents-worker/values.yaml:101-102`,
  `services/labs/kuptsi-app/values.yaml:37-38`).
- Stock JWT semantics at v1.31.0 (`docs/runbooks/temporal-authz-role-matrix.md`):
  claim `permissions` must be a JSON array of `<namespace>:<role>` strings;
  `sub` must be a string; RS256/ES256 only with a required `kid`; `iss` is not
  validated and there is no issuer config key; `aud` is enforced only when
  `global.authorization.audience` is non-empty (aud-less tokens then rejected);
  JWKS via `http.Get` with system roots, no CA file, no `file://`, no inline
  key; failed refresh keeps the old keys. `worker` alone grants nothing; there
  is no task-queue dimension; `temporal-system:*` ORs into every namespace.
- ADR 0003 decision 1 (Vault identity JWT via ESO) is a candidate; decisions 4
  and 5 (authenticated JWKS, pinned `iss`/`aud`) are only partly enforceable.
  #2469 verdict: `BLOCKED`; node C (JWKS trust path) undecided.

### Vault

- Listener `tls_disable = 1`, chart 0.28.1; edge TLS at Traefik for
  `secrets.mctl.ai` with `cert-manager.io/cluster-issuer: letsencrypt-prod`
  (`platform-gitops/bootstrap/templates/core-infra/vault.yaml:31-35,122-134`).
- `allow-vault-ingress` admits ESO, Traefik, mctl-api, argo-workflows
  (`bootstrap/templates/core-infra/vault-netpol.yaml`). The `temporal`
  namespace is not a listed peer.
- mctl-api uses in-cluster `http://vault-active...` because the
  Cloudflare-fronted `secrets.mctl.ai` timed out from inside the cluster for
  five hours on 2026-10-09 (`bootstrap/templates/mctl-platform/mctl-api.yaml:146`).
  Any JWKS fetched through a public hostname inherits that failure mode.
- No Vault identity OIDC key or role and no `VaultDynamicSecret` exists in
  `platform-gitops/` or `infrastructure/` (grep; only proposals mention them).

### ZITADEL

- v4.19.2 via chart 10.3.0 (`bootstrap/templates/core-infra/zitadel.yaml:31-33`),
  public HTTPS at `auth.mctl.ai` with a `letsencrypt-prod` certificate
  (`zitadel.yaml:147-154`), issuer `https://auth.mctl.ai`
  (`docs/runbooks/zitadel.md`, First deploy step 4). Configuration is
  OpenTofu in `platform-gitops/helm-charts/zitadel-iac/iac/`, applied by the
  `zitadel-iac` PostSync Job holding the System API `iac` key
  (IAM_OWNER/ORG_OWNER).
- Projects: `platform`, `argocd`, `vault`, `workflows`, `grafana`,
  `kubernetes`, `anthropic`, `cloudflare_access`, `mctl_api`, `mctl_web`,
  `mctl_web_dev`, `customer_lifecycle`, `erpact_frappe` (IaC files of the same
  names). None targets Temporal.
- One machine user: `zitadel_machine_user.customer_lifecycle`
  (`customers.tf:297-304`): `with_secret = true` (static client secret),
  `ACCESS_TOKEN_TYPE_JWT`, scoped by `ORG_USER_MANAGER` on `customers`; the
  consumer pins the project id (via the reserved
  `urn:zitadel:iam:org:project:id:{id}:aud` scope) AND the exact machine
  subject (`customers.tf:310-321`). This is the only existing M2M pattern.
- Audience semantics documented in `mctl-api.tf`: ZITADEL puts the client ids
  of every application of a project into `aud`, which is why each relying
  party has its own project. Role claims are ZITADEL's own
  `urn:zitadel:iam:org:project:roles` map, not a `permissions` array.
- Custom claims come only from Actions v2: `preuserinfo` / `preaccesstoken`
  executions routed to a target in mctl-api, behind
  `identity_hook_token_functions_enabled`; the target "does not interrupt, so a
  failing hook only leaves `mctl:*` claims out" (`customers_executions.tf:1-23,60-65`).
- The JWKS at `auth.mctl.ai` is shared by every token ZITADEL issues (humans
  for Argo CD, Vault, Grafana, Cloudflare Access, mctl-api, customers).
- mctl-api's own tokens are EdDSA (`OAUTH_JWT_SIGNING_ALG: "EdDSA"`,
  `mctl-api.yaml`), which Temporal's stock provider cannot verify; mctl-api is
  therefore not a candidate issuer either.

Deployed state checked:

- `mctl_get_service_config labs/kuptsi-app`: image tag 0.2.27, host
  `labs-kuptsi-app.mctl.ai`, base-service. Agrees with the #2469 inventory.
  It says nothing about Temporal auth.
- Gitops paths read: `platform-gitops/infra-components/data/temporal/`,
  `bootstrap/templates/core-infra/{vault,vault-netpol,zitadel}.yaml`,
  `bootstrap/templates/mctl-platform/mctl-api.yaml`,
  `helm-charts/zitadel-iac/iac/{customers,customers_executions,mctl-api}.tf`,
  `services/{admins/mctl-agents-worker,labs/kuptsi-app}/values.yaml`.
- Not observed (no read-only path in this run): running Temporal config and
  egress, ZITADEL web-key algorithm/rotation state, ZITADEL Actions execution
  state (toggle value in `customers_rollout.auto.tfvars.json` is desired state
  only), Vault server version and identity engine state, ESO version. These
  are recorded as gaps, never as absent.

## Proposed solution

Add one document, `docs/spikes/2506-temporal-jwt-issuer.md`, following the
`docs/spikes/*.md` format (STATUS line, evidence tables with source column,
"not observed is never absent"). It contains, in order:

1. **Evidence table** with `VERIFIED_SOURCE` / `VERIFIED_LIVE` /
   `NOT_OBSERVED` for ZITADEL, Vault/ESO, Temporal (by reference to #2469 rows,
   not copied as live proof) and the clients. Upstream facts needing citation:
   ZITADEL v4.19.2 Actions v2 claim append, web keys, client-credentials and
   private-key-JWT grants, token exchange; Vault identity OIDC key/role
   (`allowed_client_ids`, `verification_ttl`, `rotation_period`, template),
   `/v1/identity/oidc/.well-known/keys` scope (all named keys of the
   namespace); ESO `VaultDynamicSecret` GET method.
2. **Answers to RQ1-RQ4**, expected as follows (the implementer must confirm
   each against cited source; a contradiction changes the verdict per section
   5):
   - RQ1: No. ZITADEL emits roles as `urn:zitadel:iam:org:project:roles`
     (an object), which the stock mapper ignores; `permissionsClaimName`
     can rename the claim but the value must be an array of strings. A
     `permissions` array requires an Actions v2 `preaccesstoken` target, which
     today points at mctl-api and is non-interrupting. That puts mctl-api and
     the action target inside Temporal's trusted computing base, and a hook
     failure yields a token without permissions (fail closed, but a Temporal
     outage coupled to mctl-api). Under Vault, the role template is evaluated
     by Vault from entity metadata that only an admin writes; the workload
     cannot self-assert it.
   - RQ2: The server enforces only signature (key set) and `aud`. Under
     ZITADEL, the key set is the instance-wide JWKS, so every ZITADEL JWT
     access token whose `aud` contains the Temporal audience and carries a
     `permissions` claim is accepted; `aud` becomes the sole issuer boundary,
     protected only by `has_project_check` and project grants. Under Vault, a
     dedicated named key for Temporal limits accepted tokens to that key,
     provided no other named key exists in the namespace JWKS (true in desired
     state; live `NOT_OBSERVED`). ZITADEL's public HTTPS endpoint satisfies
     the system-roots constraint, but via the public, Cloudflare-fronted path
     with the 2026-10-09 failure mode; Vault's options remain the #2469 node C
     list (HTTPS with CA in the trust store, reviewed pinned-key JWKS server,
     or `secrets.mctl.ai`, which has the same public-path failure mode).
   - RQ3: Vault: TTL per role, ESO refresh, dedicated key rotation with
     `verification_ttl`, emergency global stop by rotating only the Temporal
     key, audit via the existing Vault audit device. ZITADEL: TTL is an
     instance/project setting, client secret or machine key is long-lived and
     must itself be stored in Vault and delivered by ESO, the workload (or a
     new sidecar) must call the token endpoint, and an emergency key rotation
     invalidates every human sign-in on the platform. JWKS outage: in both
     cases the stock provider keeps old keys after a failed refresh, but a
     frontend restart during an outage starts with no keys (deny all).
   - RQ4: Yes, split issuer is simpler: human identity already lives in
     ZITADEL; adding the Temporal workload there adds a second TCB
     (ZITADEL + Vault, since the M2M secret lives in Vault anyway) instead of
     reusing the one that already holds every secret. It would change if:
     Temporal gains an issuer check or custom mapper is accepted; ZITADEL gets
     a per-relying-party signing key; workload federation (Kubernetes SA token
     to ZITADEL token exchange without a static secret) is shown to work at
     v4.19.2; or Vault's JWKS trust path proves impossible while ZITADEL's
     public path is accepted.
3. **Four-option decision matrix** (A, B, C, D) over the criteria listed in
   requirements, with platform cost (A/C: no new pods, ESO and Vault reuse;
   B: one Actions target or sidecar, M2M users, token-endpoint egress from
   every client namespace) and operator burden.
4. **Threat model** (tenant/provider token replay, self-asserted permissions,
   issuer compromise, signing-key compromise, JWKS spoofing/outage, pod
   credential theft, cross-namespace commands with
   `EnableCrossNamespaceCommands`), and the boundary between Temporal namespace
   authorization and mctl-api principal/tenant authorization: provider tokens
   never carry a `mctl-agents:*` or `mctl-assistants:*` permission; only
   mctl-api starts, signals, queries, lists or terminates DevLoop and
   assistant-control workflows on behalf of a principal.
5. **Verdict: `HYBRID_WITH_BOUNDARIES`** (option C). Boundaries:
   ZITADEL issues human and business identity only and never a token
   containing a `permissions` claim or a Temporal audience; Vault issues
   Temporal workload JWTs from a dedicated named key whose JWKS contains no
   other key; no Temporal enablement is licensed by this verdict while #2469
   is `BLOCKED`. Fallback: if node C finds no authenticated JWKS path for
   Vault, the verdict becomes `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH` (option
   D), not B. `UNIFY_ZITADEL_M2M` is rejected unless all RQ1/RQ2 conditions in
   section 2 are disproved by cited source.
6. **Role/claim mapping**: each ADR 0003 identity (`temporal-mctl-api`,
   `temporal-mctl-agents-{control,exec,implement}`, `temporal-kuptsi`,
   `temporal-bootstrap`, future `mctl-assistants` control and providers) to
   its `permissions` value (from the #2469 matrix re-check, `write` not
   `worker`), its Vault role and entity, and its Kubernetes ServiceAccount.
7. **Issuer-specific negative-test contract**, added to the canary
   S-steps, mapped to T1-T11 (listed in tasks.md Tests).
8. **Migration and rollback**: both are no-ops today (nothing is enabled).
   Changing issuer later is a key-source plus credential-delivery swap; with
   two `keySourceURIs` both issuers can be accepted during a cut-over, which
   is itself a widening and must be time-boxed.
9. **Proposed ADR 0003 amendment** (text only, "proposed, not adopted"):
   decision 1 adds "ZITADEL is not a Temporal issuer; a dedicated Vault named
   key"; decision 5 replaces "stable `iss`" with "the key set is the only
   issuer control; JWKS must contain only the Temporal key"; a known-limit
   entry for JWKS cold-start outage.
10. **Handoff**: findings feed #2469 node C (trust path, JWKS exclusivity),
    node D (dedicated named key, `allowed_client_ids`), node F (new canary
    steps), node A (no OAuth client code needed in clients), and node I
    (provider permission rule). No new node, no new DAG.

The document is the only file added. A one-line link may be added to the
"Companion documents" line of `docs/runbooks/temporal-client-auth.md`; the ADR
file itself is not edited.

## Alternatives

- **Write the verdict as `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH` outright.**
  Accurate about enablement, but loses the issuer decision that #2469 node D
  needs and would make the next spike redo the comparison. Kept as the
  explicit fallback instead.
- **Choose `UNIFY_ZITADEL_M2M` for its public HTTPS JWKS.** Solves the
  system-roots constraint, but trades it for a shared instance-wide signing
  key, a custom-claim hook in mctl-api inside the Temporal TCB, a long-lived
  client secret, and a public-path outage mode. Rejected unless the RQ1/RQ2
  conditions are disproved.
- **Edit ADR 0003 directly.** The issue forbids automatic adoption; the
  amendment stays a deliverable for a separate owner decision.
- **Run a live ZITADEL token experiment.** Out of scope (no new credentials,
  no configuration mutation); listed as a canary step for node F instead.

## Platform impact

- Documentation only: no manifest, chart, IaC or workflow template changes;
  ArgoCD has nothing to sync; `validate-manifests.yml` and `claude-review.yml`
  run as for any docs PR.
- No resource, cost or compatibility impact. #2457 release blockers and ADR
  0003 status are unchanged.
- Risk: the verdict is mistaken for a release grant. Mitigation: the STATUS
  line and verdict section state that no enablement is licensed while #2469 is
  `BLOCKED`.
- Risk: upstream ZITADEL/Vault facts cannot be cited at pinned versions.
  Mitigation: record `NOT_OBSERVED` and list it as a verdict precondition;
  never fill with a guess.
- Risk: duplicating #2469. Mitigation: reference its rows and S-steps by id;
  add only issuer-specific content.
