# Temporal client authentication and authorization (issue #2456)

Status: inventory and decision record only. Nothing in this document changes
runtime behaviour. Every credential, SDK, Vault, ESO, TLS, authorizer,
namespace and observability change is a separate, independently approved
DevLoop issue (see "Downstream issue breakdown"). Decision: `docs/adr/0003-temporal-client-authz.md`.

## Desired state (from this repository)

- Server: chart `temporal` 1.2.0, server 1.31.0, `replicaCount: 1`
  (`platform-gitops/bootstrap/templates/data/temporal.yaml`). No
  `global.tls` and no `global.authorization` in the values: plaintext gRPC on
  7233, no authorizer.
- Boundary today: NetworkPolicy `allow-temporal-ingress`
  (`infra-components/data/temporal/networkpolicy.yaml`) only. It limits who
  can connect, not what a connected client may do.
- Temporal namespaces registered by `tenant-namespace-job.yaml`: `kuptsi`
  (7d), `mctl-agents` (30d).

### Client inventory

| Client | Source of truth | Temporal namespace |
|---|---|---|
| mctl-api | `bootstrap/templates/mctl-platform/mctl-api.yaml` | mctl-agents |
| mctl-agents-worker (control) | `services/admins/mctl-agents-worker/values.yaml` | mctl-agents |
| mctl-agents-worker-exec | `services/admins/mctl-agents-worker-exec/values.yaml` | mctl-agents |
| mctl-agents-worker-implement | `services/admins/mctl-agents-worker-implement/values.yaml` | mctl-agents |
| kuptsi-app + `temporal-worker` sidecar | `services/labs/kuptsi-app/values.yaml` | kuptsi |
| temporal-web | `bootstrap/templates/data/temporal-web.yaml` | all (default kuptsi) |
| namespaces bootstrap Job, admintools | `tenant-namespace-job.yaml`, chart | system |

Any caller not in this table is a finding. Absence of evidence below means
"not observed", never "absent".

## Live evidence (to be collected, read-only)

Collected by an operator with read access to the `temporal` namespace and
recorded here with a date. This implementation run had no cluster access, so
every item is **not observed**.

| Item | Command / source | Result |
|---|---|---|
| Running server image | `kubectl -n temporal get deploy -o wide` | not observed |
| Rendered frontend config | `kubectl -n temporal get cm temporal-config -o yaml` | not observed |
| Registered namespaces | `temporal operator namespace list` | not observed |
| Connected clients | frontend logs / `temporal_request` metrics (no scrape exists today) | not observed |
| SDK versions: mctl-api, mctl-agents 1.117.0, kuptsi-app 0.2.27 | go.mod / pyproject.toml / lock files in each repo at the deployed tag | not observed |
| Chart 1.2.0 supports `server.internalFrontend` and `server.config.tls` | `helm show values temporal/temporal --version 1.2.0` | not observed |
| Default-authorizer role per API (poll, start, signal, terminate, list, query) | Temporal 1.31.0 source: `common/authorization/default_authorizer.go` and the `api` annotations in the proto/`api.go` method tables | not observed; to be filled as a source-backed role/RPC matrix |
| Issuer, JWT `aud` enforcement with a non-empty trusted audience | server config `jwtKeyProvider` / claim mapper in 1.31.0 | not observed; unknown until proven on a canary |
| Vault/ESO token template and refresh API compatibility | `identity/oidc/role` template, ESO `VaultDynamicSecret` | not observed |
| JWKS fetch with trusted TLS or a pinned key | Vault HTTPS listener / CA trust | not observed |
| Effect of `temporal-system:read` for the UI | role matrix above | not observed |

Valid claim role strings in the stock default claim mapper: `read`, `write`,
`worker`, `admin`; cluster scope is `temporal-system:<role>`. These are NOT
`reader`/`writer`/`system:admin`. Candidate names in the ADR stay candidates
until the matrix above is source-backed.

## Downstream issue breakdown (each needs its own issue, review, approval)

3. Client support in mctl-api, mctl-agents, kuptsi-app: `TEMPORAL_TOKEN_FILE`
   (re-read at least every 5 min, `authorization: Bearer`),
   `TEMPORAL_TLS_CA_FILE`, `TEMPORAL_TLS_SERVER_NAME`; unchanged when unset;
   never log the token.
4. Credential plumbing in shadow (Vault OIDC key and roles, ESO generators,
   mounts, inventory rows in `agent-credential-delivery.md`, CI validator).
5. Frontend metrics scrape and `temporal-authz-alerts.yaml` with promtool tests.
6. Frontend TLS (internal CA, certificate, client CA distribution).
7. Disposable canary with negative tests T1-T11 (mandatory before 8).
8. Authorizer enablement.
9. Production negative proof; update the NetworkPolicy header.
10. `mctl-assistants*` namespaces and identities.

Rollback expectations per phase are in the ADR. Never remove
`allow-temporal-ingress`; it stays as defense in depth.
