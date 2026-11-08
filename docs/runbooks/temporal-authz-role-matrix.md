# Temporal default authorizer: role/RPC matrix and JWT semantics

Spike #2469. Research only; nothing here changes runtime behaviour. Source:
`temporalio/temporal` at tag `v1.31.0` (server appVersion of chart 1.2.0),
read 2026-11-08. Base URL for citations:
`https://github.com/temporalio/temporal/blob/v1.31.0/`. Status vocabulary is
defined in `docs/runbooks/temporal-client-auth.md`.

## How the decision is made

- Role bits (`common/authorization/roles.go:9-14`): `worker`=1, `read`=2,
  `write`=4, `admin`=8. Claims hold a `System` role and a per-namespace role map
  (`roles.go:25-36`).
- `default_authorizer.go:45-65`: look up the method's `Scope` and `Access`
  (`common/api/metadata.go`). For cluster scope the caller's role is
  `claims.System`. For namespace scope it is
  `claims.System | claims.Namespaces[target.Namespace]`. Allow when
  `hasRole >= required`, a numeric comparison. Required is read=2, write=4,
  admin=8 (`default_authorizer.go:68-77`). Unknown scope is denied
  (`default_authorizer.go:55-56`).
- Health checks are allowed to everyone, with or without a token:
  `GetSystemInfo` and gRPC health `Check` (`common/authorization/frontend_api.go:8-11`,
  used at `default_authorizer.go:38-40`).
- No claims (no token) means deny (`default_authorizer.go:41-43`). Only Admin
  service methods are always `cluster` + `admin` (`metadata.go:214-215`).

Consequences, all `VERIFIED_SOURCE`:

1. **`worker` grants nothing by itself.** Its value 1 is below every
   requirement (read=2). Poll and Respond APIs are classified `Write`
   (`metadata.go:79-82`), so a worker needs `write`. The ADR candidate
   "narrow to `worker` only if proven" is disproved for 1.31.0.
2. **No task-queue dimension.** `CallTarget` carries namespace, API name and
   the request, and the default authorizer reads only the namespace and API
   (`default_authorizer.go:35-65`). Authorization is never decided per task
   queue. Task-queue isolation must be done with separate Temporal namespaces.
   This document does not claim queue-level RBAC.
3. **`temporal-system` scope.** A permission whose namespace part is
   `temporal-system` (`primitives.SystemLocalNamespace`,
   `default_jwt_claim_mapper.go:20,135-136`) sets `claims.System`. System bits
   OR into every namespace lookup, so `temporal-system:read` is read in every
   namespace, plus the cluster-scope read APIs; `temporal-system:admin` is
   everything including the Admin service.
4. **Namespace roles never satisfy cluster scope**, so `<ns>:admin` cannot call
   `ListNamespaces` or Admin-service methods.
5. **Cross-namespace commands.** `interceptor.go:287-352` re-authorizes child
   workflow starts, external signals and external cancels against the target
   namespace, only when dynamic config `EnableCrossNamespaceCommands` is true
   (`interceptor.go:294`; wired at `service/frontend/fx.go:185`). Whether it is
   on in the running server is `BLOCKED_NO_ACCESS`; canary must test both.
6. **Denial code.** Every denial from the stock interceptor is gRPC
   `PermissionDenied` (`interceptor.go:44,51,148,256-264`), including a bad or
   missing token. The stock server never returns `Unauthenticated`; an
   `Unauthenticated` code would come only from a TLS or proxy layer.

## Matrix

Cells: A = allow, D = deny. Columns are the identity's permission string.
"sys" is the `temporal-system` scope. Scope/Access are from
`common/api/metadata.go` at the line given. All cells are derived by the
`>=` rule above, so none is "unclear"; runtime confirmation is canary T3-T6.

| RPC | Scope / Access (line) | ns:read | ns:write | ns:worker | ns:admin | sys:read | sys:admin |
|---|---|---|---|---|---|---|---|
| PollWorkflowTaskQueue | ns / write (79) | D | A | D | A | D | A |
| PollActivityTaskQueue | ns / write (82) | D | A | D | A | D | A |
| RespondWorkflowTaskCompleted | ns / write (80) | D | A | D | A | D | A |
| StartWorkflowExecution | ns / write (76) | D | A | D | A | D | A |
| SignalWorkflowExecution | ns / write (103) | D | A | D | A | D | A |
| SignalWithStartWorkflowExecution | ns / write (104) | D | A | D | A | D | A |
| TerminateWorkflowExecution | ns / write (106) | D | A | D | A | D | A |
| RequestCancelWorkflowExecution | ns / write (102) | D | A | D | A | D | A |
| QueryWorkflow | ns / read (119) | A | A | D | A | A | A |
| DescribeWorkflowExecution | ns / read (120) | A | A | D | A | A | A |
| ListWorkflowExecutions | ns / read (110) | A | A | D | A | A | A |
| GetWorkflowExecutionHistory | ns / read (77) | A | A | D | A | A | A |
| DescribeNamespace | ns / read (72) | A | A | D | A | A | A |
| RegisterNamespace | ns / admin (71) | D | D | D | A | D | A |
| UpdateNamespace | ns / admin (74) | D | D | D | A | D | A |
| ListNamespaces | cluster / read (73) | D | D | D | D | A | A |
| OperatorService ListSearchAttributes | ns / read (184) | A | A | D | A | A | A |
| OperatorService AddSearchAttributes | ns / admin (182) | D | D | D | A | D | A |
| OperatorService RemoveSearchAttributes | ns / admin (183) | D | D | D | A | D | A |
| OperatorService DeleteNamespace | ns / admin (185) | D | D | D | A | D | A |
| GetSearchAttributes | cluster / read (114) | D | D | D | D | A | A |
| GetClusterInfo | cluster / read (122) | D | D | D | D | A | A |
| GetSystemInfo | cluster / read (123); health-exempt | A | A | A | A | A | A |
| Any AdminService method | cluster / admin (215) | D | D | D | D | D | A |

A caller holding no token is denied everything except `GetSystemInfo` and
gRPC health `Check`. Combined permissions OR together (for example
`ns:worker` plus `ns:read` is 3, which allows read but not write).

## ADR 0003 candidate permission map re-check

| Identity (ADR) | Candidate | Result |
|---|---|---|
| temporal-mctl-api | `mctl-agents:write` | Sufficient for start, signal, query, list, describe, terminate. No narrower role exists. |
| temporal-mctl-agents-{control,exec,implement} | `mctl-agents:write`, "narrow to worker only if proven" | Narrowing is disproved: `worker` alone cannot poll. Keep `write`. |
| temporal-kuptsi | `kuptsi:write` | Correct isolation by namespace. Inside `kuptsi` it can still terminate any workflow; no queue-level restriction exists. |
| temporal-bootstrap (Job) | `temporal-system:admin` | Works. Could be narrowed to `<ns>:admin` per target namespace for namespace and search-attribute calls; not for Admin-service calls. |
| future assistants control / provider | `<ns>:write` | Works. Provider isolation relies on separate namespaces only. |
| temporal-web | not set | Needs `temporal-system:read` (namespace list is cluster scope). Deferred, node J. |

## JWT semantics (1.31.0)

| Point | Finding | Status |
|---|---|---|
| Permissions claim | Default claim name `permissions` (`default_jwt_claim_mapper.go:17,38-41`, override `permissionsClaimName`). Value must be a JSON array of strings `<namespace>:<role>`, split on the first `:` (`:128`); optional `permissionsRegex` with named groups `namespace` and `role` (`:44-63`). Non-string or malformed entries are ignored with a warning (`:114-132`); unknown role names map to no role (`:203-215`). `sub` must be a string or the call is denied (`:97-100`). | VERIFIED_SOURCE |
| Header and format | Reads `authorization` (configurable `authHeaderName`); must be `Bearer <jwt>` (`:86-92`). | VERIFIED_SOURCE |
| Algorithms | RS256 and ES256 only; HMAC is rejected (`default_token_key_provider.go:90-92,168-170`). A `kid` header is required and must match a loaded key (`default_jwt_claim_mapper.go:166-170`, `default_token_key_provider.go:62-88`). | VERIFIED_SOURCE |
| `iss` validation | Not validated. Validity is `claims.Valid()` (exp, nbf, iat only; `default_jwt_claim_mapper.go:194`) and signature. No issuer config key exists (`common/config/config.go:626-643`). The signing key and JWKS source are the only issuer control. ADR decision 5 "pinned `iss`" cannot be enforced by the server. | VERIFIED_SOURCE |
| Audience | `global.authorization.audience` (`config.go:642`) is turned into a static mapper (`common/authorization/audience_mapper.go:25-29`, wired in `cmd/server/main.go:213-229`). If non-empty after trimming, a token whose `aud` does not include it is rejected as "audience mismatch", and a token without `aud` is also rejected (`VerifyAudience(aud, true)`, `default_jwt_claim_mapper.go:197-199`). An empty config disables the check. | VERIFIED_SOURCE; runtime proof BLOCKED_JWT_SEMANTICS until canary T2 |
| Key source | `jwtKeyProvider.keySourceURIs` and `refreshInterval` (`config.go:647-650`). Fetched with Go `http.Get(uri)` and parsed as a JWKS (`default_token_key_provider.go:141-153`): `http` and `https` only, system trust roots only; no CA-file option, no `file://`, no inline pinned key. Refresh is on a timer when `refreshInterval > 0` (`:49-53,94-108`); a failed refresh keeps the old keys and logs an error. If `refreshInterval` is 0 the keys load once at start. | VERIFIED_SOURCE |
| Plaintext in-cluster JWKS | Vault listener is `tls_disable = 1` (`platform-gitops/bootstrap/templates/core-infra/vault.yaml`). A JWKS URI of the form `http://` on Vault is REJECTED by ADR decision 4. HTTPS with an explicit CA needs the CA added to the Temporal image trust store (for example via `SSL_CERT_FILE`/`SSL_CERT_DIR`), because the provider has no CA option. A pinned-key option needs a separately reviewed sidecar or ConfigMap-served JWKS over HTTPS. Decision is node C. | VERIFIED_SOURCE (constraint) |
| Vault identity OIDC role and key | Role `key`, `template` (for the `permissions` array), `client_id` (becomes `aud`), `ttl`; key `verification_ttl` controls how long the old public key stays in the JWKS after rotation. Repro: on the canary Vault only, create key, role with template `{"permissions": ["canary-ns:write"]}` and client_id `temporal-frontend`, read `identity/oidc/token/<role>`, decode the payload, check `iss`, `aud`, `exp`, `permissions`, then rotate the key and confirm the old `kid` validates until `verification_ttl` expires. | BLOCKED_JWT_SEMANTICS |
| TTL and revocation | Server-side check is stateless: a token is valid until `exp` (plus key lifetime). Revocation therefore means TTL expiry or removing the key from JWKS and waiting one `refreshInterval`. Canary T9 measures it. | VERIFIED_SOURCE for the server side; Vault side BLOCKED_JWT_SEMANTICS |
| ESO `VaultDynamicSecret` | Canary repro: a `VaultDynamicSecret` generator with `method: GET` and path `identity/oidc/token/<role>`, `refreshInterval` less than half the role TTL, writing a Secret that is mounted as a file; confirm the Secret updates and that the generator returns the `token` field. Not run. | BLOCKED_JWT_SEMANTICS |

## Reproducing the citations

All files above are at `temporalio/temporal` tag `v1.31.0`:
`common/authorization/{default_authorizer,roles,default_jwt_claim_mapper,default_token_key_provider,audience_mapper,frontend_api,interceptor}.go`,
`common/api/metadata.go`, `common/config/config.go`, `cmd/server/main.go`,
`service/frontend/fx.go`. Re-read them if the server version changes; the
matrix is valid for 1.31.0 only.
