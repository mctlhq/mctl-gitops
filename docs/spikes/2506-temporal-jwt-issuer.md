# Spike 2506: ZITADEL versus Vault as the Temporal workload JWT issuer

STATUS: DOCUMENT_ONLY. Direction verdict, conditional. Licenses no TLS,
credential, Vault, ZITADEL, ESO or authorizer change. Spike #2469 is
`BLOCKED` (`docs/runbooks/temporal-client-auth.md`) and stays the gate.
ADR 0003 stays `Proposed`; the amendment in section 9 is "proposed, not
adopted". #2457 release blockers are unchanged.

Issue: mctlhq/mctl-gitops#2506. Repo state read: `main` at `8c5dc6b`.

## 0. Labels

Same vocabulary as `docs/runbooks/temporal-client-auth.md`:

- `VERIFIED_SOURCE`: Git or upstream source at a pinned commit or tag.
- `VERIFIED_LIVE`: dated operator command output. This spike has none.
- `NOT_OBSERVED`: no read-only path in this run. It never means "absent".
  Each such row names the command that would observe it.

Temporal server facts are not re-derived here. They are cited from
`docs/runbooks/temporal-authz-role-matrix.md` (server `v1.31.0`) and
`docs/runbooks/temporal-client-auth.md`. No #2469 row is presented as new live
proof.

## 1. Evidence

### 1.1 Temporal (by reference to #2469)

| Fact | Source | Label |
|---|---|---|
| Claim `permissions` must be a JSON array of `<namespace>:<role>` strings; `sub` a string; RS256/ES256 only, `kid` required | matrix doc, JWT section | VERIFIED_SOURCE (#2469) |
| `iss` is not validated; no issuer config key | matrix doc | VERIFIED_SOURCE (#2469) |
| `aud` enforced only when `global.authorization.audience` is non-empty; aud-less tokens then rejected | matrix doc | VERIFIED_SOURCE (#2469); runtime proof is canary S6 |
| JWKS fetched with `http.Get`, system trust roots, no CA file, no `file://`, no inline key; failed refresh keeps old keys | matrix doc | VERIFIED_SOURCE (#2469) |
| `worker` alone grants nothing; no task-queue dimension; `temporal-system:*` ORs into every namespace | matrix doc | VERIFIED_SOURCE (#2469) |
| No `global.tls`, no `global.authorization`; boundary is `allow-temporal-ingress` | `platform-gitops/bootstrap/templates/data/temporal.yaml`; `platform-gitops/infra-components/data/temporal/networkpolicy.yaml` | VERIFIED_SOURCE (desired state); running config NOT_OBSERVED: `kubectl -n temporal get cm temporal-config -o yaml` |
| No egress policy in the `temporal` namespace directory (only `externalsecret.yaml`, `networkpolicy.yaml`, `tenant-namespace-job.yaml`) | `platform-gitops/infra-components/data/temporal/` | VERIFIED_SOURCE (desired state); live egress NOT_OBSERVED: `kubectl get netpol -n temporal` plus a curl from the frontend pod |
| Clients carry `TEMPORAL_ADDRESS` / `TEMPORAL_NAMESPACE` only | `platform-gitops/services/admins/mctl-agents-worker/values.yaml:101-102`; `platform-gitops/services/labs/kuptsi-app/values.yaml:37-38` | VERIFIED_SOURCE (desired state) |
| kuptsi-app deployed tag 0.2.27 | `mctl_get_service_config labs/kuptsi-app` (this run) | agrees with the #2469 inventory; says nothing about Temporal auth |

### 1.2 Vault and ESO

| Fact | Source | Label |
|---|---|---|
| Listener `tls_disable = 1`, chart 0.28.1; edge TLS at Traefik for `secrets.mctl.ai` (`letsencrypt-prod`) | `platform-gitops/bootstrap/templates/core-infra/vault.yaml:31-35,122-134` | VERIFIED_SOURCE (desired state) |
| `allow-vault-ingress` admits ESO, Traefik, mctl-api, argo-workflows; `temporal` is not a peer | `platform-gitops/bootstrap/templates/core-infra/vault-netpol.yaml` | VERIFIED_SOURCE (desired state) |
| mctl-api uses in-cluster `http://vault-active.vault.svc.cluster.local:8200` because Cloudflare-fronted `secrets.mctl.ai` timed out from inside the cluster on 2026-10-09 | `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml:146-156` | VERIFIED_SOURCE (comment); the outage itself was not re-observed here |
| No Vault identity OIDC key or role and no `VaultDynamicSecret` in `platform-gitops/` or `infrastructure/` | repository grep, this run | VERIFIED_SOURCE (desired state); live Vault state NOT_OBSERVED: `vault list identity/oidc/key` |
| Vault identity OIDC semantics: named key, `allowed_client_ids`, `rotation_period`, `verification_ttl`, role template, and which keys `/v1/identity/oidc/.well-known/keys` serves | Vault docs at the deployed server version | NOT_OBSERVED: server version unknown (`vault status`); the claim that the endpoint serves every named key of the Vault namespace must be proven on the canary (T2b) before it is relied on |
| ESO `VaultDynamicSecret` GET method and refresh behaviour | ESO docs at the deployed version | NOT_OBSERVED: `kubectl -n external-secrets get deploy -o jsonpath='{..image}'` |
| Vault audit device in use | design assumption | NOT_OBSERVED: `vault audit list` |

### 1.3 ZITADEL

| Fact | Source | Label |
|---|---|---|
| v4.19.2 via chart 10.3.0; public HTTPS `auth.mctl.ai`, `letsencrypt-prod`; issuer `https://auth.mctl.ai` | `platform-gitops/bootstrap/templates/core-infra/zitadel.yaml:31-33,147-154`; `docs/runbooks/zitadel.md` | VERIFIED_SOURCE (desired state) |
| Configuration is OpenTofu applied by the `zitadel-iac` PostSync Job (System API `iac` key) | `platform-gitops/helm-charts/zitadel-iac/iac/` | VERIFIED_SOURCE |
| Audience semantics: ZITADEL puts the client ids of every application of a project into `aud`, hence one project per relying party | comment in `mctl-api.tf` | VERIFIED_SOURCE (repo comment, not upstream source) |
| Role claim is ZITADEL's `urn:zitadel:iam:org:project:roles` object, not a `permissions` array | `mctl-api.tf` and ZITADEL docs | repo comment VERIFIED_SOURCE; upstream emit format at v4.19.2 NOT_OBSERVED: read `internal/api/oidc` at tag `v4.19.2` in `zitadel/zitadel` |
| Custom claims come only from Actions v2 `preuserinfo` / `preaccesstoken` executions routed to an mctl-api target; the target does not interrupt, so a failing hook leaves `mctl:*` claims out | `customers.tf:228`, `customers_executions.tf:1-23,60-65` | VERIFIED_SOURCE (desired state); execution state NOT_OBSERVED (toggle `identity_hook_token_functions_enabled` is desired state only) |
| Whether Actions v2 `preaccesstoken` may append a top-level `permissions` array (reserved-name collisions, size limits) | ZITADEL docs / source at `v4.19.2` | NOT_OBSERVED (not cited in this run); gap, and a precondition of option B |
| Web-key algorithm (RSA versus ECDSA) and rotation of the instance access-token signing key | not declared in `zitadel.yaml` or the IaC | NOT_OBSERVED: `curl -s https://auth.mctl.ai/oauth/v2/keys` (read `kty`, `alg`, `kid` set) and ZITADEL web-key admin API |
| Client-credentials, private-key-JWT and token-exchange behaviour at v4.19.2 (workload federation without a static secret) | ZITADEL docs / source | NOT_OBSERVED |
| JWKS at `auth.mctl.ai` is instance-wide: one key set for every token ZITADEL signs | consequence of one issuer per instance; uses by Argo CD, Vault, Grafana, Cloudflare Access, mctl-api, customers | VERIFIED_SOURCE (inventory below); key-set contents NOT_OBSERVED |
| mctl-api tokens are EdDSA (`OAUTH_JWT_SIGNING_ALG: "EdDSA"`), which the stock Temporal provider cannot verify | `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml:264` | VERIFIED_SOURCE; mctl-api is not a candidate issuer |

### 1.4 ZITADEL IaC inventory and reuse for Temporal

From `platform-gitops/helm-charts/zitadel-iac/iac/`. "Reusable" means usable
as a Temporal identity or boundary object. All desired state; live NOT_OBSERVED.

| Object | Where | Token type / checks | Reusable for Temporal |
|---|---|---|---|
| Projects `platform`, `argocd`, `vault`, `workflows`, `grafana`, `kubernetes`, `anthropic`, `cloudflare_access`, `portal`, `labs_app`, `mctl_api`, `mctl_api_dev`, `mctl_web`, `mctl_web_dev`, `customer_lifecycle`, `erpact_frappe` | `forgejo.tf`, `argocd.tf`, `vault.tf`, `workflows.tf`, `grafana.tf`, `kubernetes.tf`, `anthropic.tf`, `cloudflare-access.tf`, `portal.tf`, `labs-apps.tf`, `mctl-api.tf`, `customers.tf`, `erpact.tf` | `has_project_check = true` set on every listed project except `platform`, where `forgejo.tf` sets none in the resource block (default not checked here) | No. None targets Temporal; each is bound to its own relying party. A Temporal project would be new |
| Applications with JWT access tokens | `mctl_api`, `mctl_web`, `mctl_web_dev` | `OIDC_TOKEN_TYPE_JWT` | No. These are human or customer tokens; their `aud` must never include a Temporal audience |
| Applications with bearer (opaque) access tokens | argocd, grafana, cloudflare_access, kubernetes, anthropic, labs_app, erpact | `OIDC_TOKEN_TYPE_BEARER` | No. Opaque tokens cannot be verified by Temporal |
| Machine user `customer_lifecycle` | `customers.tf:297-304` | `ACCESS_TOKEN_TYPE_JWT`, `with_secret = true` (static client secret), `ORG_USER_MANAGER` on `customers`; consumer pins project id via the reserved `urn:zitadel:iam:org:project:id:{id}:aud` scope and the exact subject (`customers.tf:310-321`) | Pattern only. The user itself is not reusable (customer account deletion authority). It is the only M2M pattern, and it uses a long-lived static secret |
| Actions v2 targets and executions | `customers.tf:210-228`; `customers_executions.tf:60-77` | target `identity_token_claims` routes `preuserinfo` / `preaccesstoken` to mctl-api; non-interrupting | Would be the only way to emit a `permissions` array, and would put mctl-api in the Temporal trusted computing base. Not reused |
| Actions v1 `argocd_groups`, `erpact_verified_email`, `github_login` | `argocd.tf:133`, `erpact.tf:165`, `github-login.tf:101` | claim and login shaping for humans | No |

## 2. Research questions

RQ1. Can ZITADEL produce tokens the stock claim mapper accepts, without a
custom build, and without a claim the workload or its org can influence?
Not demonstrated. The role claim is an object the stock mapper ignores
(source: repo comment, upstream NOT_OBSERVED). The remaining route is an
Actions v2 `preaccesstoken` target appending a `permissions` array. Whether
ZITADEL v4.19.2 allows that is NOT_OBSERVED. If it does, the target today is
mctl-api and is non-interrupting: mctl-api and the hook enter the Temporal
trusted computing base, and a hook failure yields a token without
`permissions` (fail closed, but couples Temporal to an mctl-api outage). Under
Vault the role template is evaluated by Vault from entity metadata that only an
admin writes (ADR 0003 decision 1 design; template behaviour on the deployed
version NOT_OBSERVED, canary T8).

RQ2. What does the server actually enforce on each issuer? Only signature
against the configured key set and `aud` when audience is configured (#2469).
With ZITADEL the key set is the instance-wide JWKS: every ZITADEL JWT access
token with the Temporal audience and a `permissions` claim would be accepted,
so `aud` becomes the sole issuer boundary, protected only by
`has_project_check` and grants. With Vault, a dedicated named key limits
accepted tokens to that key provided the JWKS endpoint serves no other key
(NOT_OBSERVED, canary T2b). ZITADEL's public HTTPS endpoint satisfies the
system-roots constraint but through the public Cloudflare-fronted path (2026-10-09
failure mode). Vault's trust path stays the #2469 node C list (HTTPS with CA in
the trust store, a reviewed pinned-key JWKS server, or `secrets.mctl.ai` with
the same public-path failure mode). Reachability of the Vault JWKS from the
`temporal` namespace is NOT_OBSERVED and is decided by node C, not here.

RQ3. Operational burden. Vault: TTL per role, ESO refresh, rotation of the
dedicated key with `verification_ttl`, an emergency stop by rotating only that
key, audit through the Vault audit device (NOT_OBSERVED whether enabled).
ZITADEL: TTL is an instance or project setting; the client secret or machine
key is long-lived and itself has to be stored in Vault and delivered by ESO;
the workload (or a new sidecar) must call the token endpoint, which needs
egress from every client namespace; an emergency key rotation invalidates
every human sign-in on the platform. JWKS outage in both cases: the stock
provider keeps old keys after a failed refresh, and a frontend restart during
an outage starts with no keys and denies every client (canary T9c).

RQ4. Is a split issuer simpler? Yes. Human and business identity already live
in ZITADEL. Moving Temporal workloads there adds a second trusted computing
base (ZITADEL plus Vault, since the M2M secret lives in Vault anyway) instead
of reusing the one that already holds every secret. The answer would change if
Temporal gains an `iss` check or a custom mapper is accepted; ZITADEL gets a
per-relying-party signing key; workload federation (Kubernetes ServiceAccount
token to ZITADEL token without a static secret) is shown to work at v4.19.2; or
Vault's JWKS trust path proves impossible while ZITADEL's public path is
accepted.

## 3. Decision matrix

Options: A Vault workload JWT; B ZITADEL M2M JWT; C hybrid (ZITADEL for humans
and business, Vault for Temporal workloads); D no-go pending a custom mapper or
a better JWKS trust path. A and C differ only in a stated boundary on ZITADEL,
so their technical cells are shared and the C column records the boundary.

| Criterion | A Vault | B ZITADEL M2M | C Hybrid | D No-go |
|---|---|---|---|---|
| Claim compatibility with stock mapper | Template can emit `permissions` array (version behaviour NOT_OBSERVED, canary T8) | Needs Actions v2 append (NOT_OBSERVED); roles claim is an object | As A | n/a; fixes it with a custom mapper |
| Issuer enforcement | None server side; only the key set | None server side; key set is instance-wide | As A, plus a rule that ZITADEL never issues the Temporal audience | Custom mapper could check `iss` |
| Audience enforcement | Non-empty `aud: temporal-frontend` (S6) | Same, but `aud` is the only separator from human tokens | As A | Mapper-defined |
| JWKS trust path | Open: node C. Listener is plaintext | Public HTTPS, system roots OK, public-path failure mode | As A (node C) | Blocked until a path exists |
| Signing-key sharing | Dedicated named key, if the endpoint serves only it (NOT_OBSERVED) | Shared with all human sessions | Dedicated | n/a |
| Trusted computing base | Vault, ESO | ZITADEL, mctl-api hook, Vault (secret), ESO | Vault, ESO; ZITADEL excluded | Adds custom code |
| TTL and refresh | Role TTL <= 1h, ESO refresh | Instance/project TTL, token endpoint call by workload or sidecar | As A | n/a |
| Rotation | Named key `rotation_period` + `verification_ttl`, Temporal-only blast radius | Instance key rotation hits all humans | As A | n/a |
| Revocation | Disable role, wait one TTL, or rotate key | Disable machine user, wait one TTL; key rotation global | As A | n/a |
| JWKS outage | Old keys kept; restart denies all | Same | Same | Same |
| Audit provenance | Vault audit device (NOT_OBSERVED) | ZITADEL events plus Vault for the secret | Vault | n/a |
| Platform cost | No new pods; Vault and ESO reuse | Actions target or sidecar, M2M users, egress from every client namespace | As A | Build and maintain a mapper |
| Migration | Nothing enabled, no-op today | No-op today | No-op today | Nothing to migrate yet |
| Rollback | Delete roles and ExternalSecrets (node D) | Delete machine users and targets | As A | Revert decision |
| Incident recovery | Rotate Temporal key only; ESO re-delivers | Global key rotation or hook disablement | As A | n/a |

Option B is not selected. Rule from the requirements: B may be chosen only if
the `permissions` array is shown to be produced without a custom server build
and without a claim the workload or its organization can influence. That is
NOT_OBSERVED (section 1.3), so B fails the rule.

## 4. Threat model

| Threat | Under C (Vault issuer) | Residual / test |
|---|---|---|
| Tenant or provider token replay into another namespace | Token carries only `<its namespace>:<role>`; stock authorizer checks namespace. Replay of a stolen token within its own namespace is bounded by TTL | T3-T5, T9a |
| Replay of a ZITADEL human token | ZITADEL JWKS is never a key source and no ZITADEL token has the Temporal audience | T2c |
| Self-asserted permissions | Permissions come from Vault role template and entity metadata written by admins; the workload only receives the signed result | T8 |
| Issuer compromise (Vault) | Attacker can mint any permission. Mitigated by Vault's existing controls and audit; blast radius is every Temporal namespace | Accepted risk; the TCB already holds every secret |
| Signing-key compromise | Rotate the Temporal named key only; `verification_ttl` bounds the overlap | T9b |
| JWKS spoofing | Stock fetch uses system trust roots; plain `http://` is refused (S8). A spoofed JWKS means full authorizer bypass | Node C must supply an authenticated path |
| JWKS outage | Old keys kept; restart denies all clients | T9c |
| Credential theft from a pod | Token file readable by that pod, valid for one TTL, scoped to its namespace role | T9a, T11 |
| Cross-namespace control calls | `EnableCrossNamespaceCommands` and child workflows from `kuptsi` | S17 |

Boundary between Temporal namespace authorization and mctl-api principal and
tenant authorization: provider tokens never carry a `mctl-agents:*` or
`mctl-assistants:*` permission. Only mctl-api starts, signals, queries, lists
or terminates DevLoop and assistant-control workflows on behalf of a
principal. Temporal authorization gives mctl-api its own identity; it does not
replace the principal and tenant checks inside mctl-api.

## 5. Verdict

VERDICT: `HYBRID_WITH_BOUNDARIES`

Reading of the issue wording: the issue asks for one explicit verdict or
`BLOCKED`. While #2469 is `BLOCKED`, the stricter reading would be
`BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH`. This spike keeps the issuer direction
(option C) as the verdict because #2469 node D needs the issuer decision, and
states the blocked reading as the explicit fallback below. A reviewer who
prefers the blocked label can substitute it without changing any other section.

Boundaries:

1. ZITADEL issues human and business identity only. It never issues a token
   carrying a `permissions` claim or a Temporal audience.
2. Vault issues Temporal workload JWTs from a dedicated named key whose JWKS
   contains no other key.
3. No TLS, credential or authorizer enablement is licensed by this verdict
   while #2469 is `BLOCKED`.

Preconditions (each is `NOT_OBSERVED` today and must be proven before the
verdict is relied on): Vault identity OIDC template and `aud` behaviour on the
deployed version; `.well-known/keys` serves only the Temporal key; ESO
`VaultDynamicSecret` GET and refresh; an authenticated JWKS path for the
`temporal` namespace (node C).

Fallback: if node C finds no authenticated JWKS path for Vault, the outcome
becomes `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH` (option D), not option B.

Conditions that would change the verdict: Temporal gains an issuer check or a
custom mapper is accepted; ZITADEL offers a per-relying-party signing key;
workload federation without a static secret is shown to work at v4.19.2 and
the `permissions` array is shown to be producible without a hook the workload
or its organization can influence. The rejected outcome `UNIFY_ZITADEL_M2M`
requires all of the RQ1 and RQ2 conditions to be disproved by cited source.

## 6. Role and claim mapping

`permissions` values are from the #2469 matrix re-check (`write`, not `worker`
alone). Binding objects are proposals for node D, not existing objects. No
workload can assert its own role: the value is rendered by Vault from entity
metadata an admin writes.

| ADR 0003 identity | `permissions` | Vault role and entity (proposed) | ServiceAccount |
|---|---|---|---|
| temporal-mctl-api | `mctl-agents:write` | role `temporal-mctl-api`, entity metadata admin-written | mctl-api SA |
| temporal-mctl-agents-control | `mctl-agents:write` | role `temporal-mctl-agents-control` | `admins-mctl-agents-worker` SA |
| temporal-mctl-agents-exec | `mctl-agents:write` | role `temporal-mctl-agents-exec` | `admins-mctl-agents-worker-exec` SA |
| temporal-mctl-agents-implement | `mctl-agents:write` | role `temporal-mctl-agents-implement` | `admins-mctl-agents-worker-implement` SA |
| temporal-kuptsi | `kuptsi:write` | role `temporal-kuptsi` | `labs-kuptsi-app` SA |
| temporal-bootstrap (Job only) | `temporal-system:admin` | role `temporal-bootstrap`, never mounted in a long-lived pod | Job SA |
| future assistants control | `mctl-assistants:write` | role `temporal-mctl-assistants-control` | future |
| future provider `<name>` | `mctl-assistants-provider-<name>:write` only | role per provider; never holds `mctl-agents:*` or `mctl-assistants:*` | future |

ServiceAccount names are taken from the NetworkPolicy peers and values files and
must be re-checked in node D. Whether `write` is the narrowest role that works
for worker polling is already settled by #2469 (`worker` grants nothing alone).

## 7. Issuer-specific negative-test contract (for #2469 node F)

Not executed by this issue. It adds to `docs/runbooks/temporal-auth-canary.md`
S1-S17 and to ADR 0003 T1-T11; "new" means not in the existing steps.

| ID | Step | ADR | Canary | Expected |
|---|---|---|---|---|
| T1 | No token, StartWorkflowExecution on `canary-control` | T1 | S1 | PermissionDenied |
| T2a | Token from the Temporal Vault key with wrong `aud`, and with no `aud` | T2 | S6 | Denied |
| T2b | Valid-signature token from a second Vault named key in the same Vault namespace | T2 | new | Denied. If allowed, JWKS exclusivity fails: stop |
| T2c | ZITADEL human access token (JWT type), any project, replayed at the canary | T2 | new | Denied; ZITADEL JWKS is never a key source |
| T2d | Expired, unknown `kid`, forged signature, HS256, EdDSA | T2 | S2-S4 | Denied |
| T2e | Wrong `iss`, valid key | T2 | S5 | Record; expected allowed (key is the only issuer control) |
| T3/T4 | `canary-kuptsi` and `canary-provider-a` against `canary-control`: start, signal, query, list, terminate, poll `mctl-dev-loop` | T3, T4 | S9, S10 | Denied |
| T5 | `canary-control` against `canary-kuptsi` | T5 | S11 | Denied |
| T6 | Non-admin identities on namespace and cluster APIs | T6 | S12 | Denied |
| T7 | Web identity, if enabled: writes | T7 | S13 | Denied |
| T8 | Provider entity metadata edited by a non-admin path | T8 | new | Cannot gain a control permission; token `permissions` equal admin-written metadata only |
| T9a | Disable the Vault role, wait one TTL | T9 | S14 | New tokens fail; old token rejected after `exp` |
| T9b | Rotate the Temporal named key with `verification_ttl` set | T9 | new | No validation gap; no ZITADEL or other Vault consumer affected |
| T9c | JWKS unreachable during refresh, then frontend restart during the outage | T9 | new | Old keys kept; after restart all clients denied; record time to recovery |
| T9d | Stop ESO | T9 | S14 | Workers run until expiry and recover after ESO returns |
| T10 | Synthetic long workflows through every phase | T10 | S15 | All complete |
| T11 | Search logs, Loki, histories for token material | T11 | S16 | No hits |

Stop conditions added by this spike: T2b or T2c allowed; T8 self-assertion
possible; T9b affects a non-Temporal consumer; T9c recovery not bounded.

## 8. Migration, rollback, operator cost

Migration and rollback are no-ops today: nothing is enabled. A later issuer
change is a key-source plus credential-delivery swap. Two `keySourceURIs`
accept both issuers during a cut-over, which is itself a widening and must be
time-boxed. Rollback of option A/C plumbing is node D's: delete the Vault roles
and ExternalSecrets.

At 03:00: for A/C the recovery action is to rotate or disable one Vault key or
role, with no effect on human sign-in. For B it is a ZITADEL key or hook
action that touches every relying party, plus a dependency on mctl-api for the
claim. Platform cost: A/C add no pods. B adds an Actions target or sidecar,
machine users and token-endpoint egress from every client namespace.

## 9. Proposed ADR 0003 amendment (proposed, not adopted)

This text is a deliverable only. `docs/adr/0003-temporal-client-authz.md` is
not edited by this spike.

- Decision 1, append: "ZITADEL is not a Temporal issuer. Temporal workload JWTs
  are signed by a dedicated Vault identity named key. ZITADEL never issues a
  token containing a `permissions` claim or the Temporal audience."
- Decision 5, replace "a stable `iss`" with: "The server does not validate
  `iss` (v1.31.0). The key set is the only issuer control, so the JWKS the
  frontend fetches must contain only the Temporal key. `aud` is pinned and
  non-empty."
- Known limits, add: "On a frontend restart during a JWKS outage no keys are
  loaded and every client is denied until the JWKS is reachable."

## 10. Handoff into the #2469 DAG

No new node and no new DAG.

| Node | Finding fed |
|---|---|
| A client support | Clients need only a token file (`TEMPORAL_TOKEN_FILE`); no OAuth client code, no token-endpoint egress |
| C JWKS trust path | JWKS exclusivity (only the Temporal key), authenticated path for the `temporal` namespace; the Cloudflare-fronted public path has a recorded failure mode |
| D shadow credential plumbing | Dedicated Vault named key, `allowed_client_ids`, one role per identity per section 6 |
| F disposable canary | The new steps T2b, T2c, T8, T9b, T9c and the added stop conditions |
| I assistants namespaces | Provider permission rule: provider tokens never hold `mctl-agents:*` or `mctl-assistants:*` |
