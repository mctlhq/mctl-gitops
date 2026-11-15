# Temporal authorization canary contract

Spike #2469. This is a contract for a future, separately approved canary
(node F in `docs/runbooks/temporal-client-auth.md`). Nothing here is deployed,
no namespace, key or role is created by this document, and nothing in it
touches the production release.

Evidence the canary must settle is listed in
`docs/runbooks/temporal-authz-role-matrix.md`.

## Isolation

- Separate Helm release in a separate Kubernetes namespace (name proposed
  only: `temporal-canary`). It never shares `temporal` with production.
- Own throwaway database and role (own CNPG database or an ephemeral
  Postgres). It must not use `temporal` or `temporal_visibility` on `shared-pg`.
- Own NetworkPolicy: default deny, ingress on 7233 only from canary test pods.
  No egress to `temporal-frontend.temporal.svc.cluster.local`.
- Synthetic Temporal namespaces `canary-control`, `canary-provider-a` and
  `canary-kuptsi`; synthetic identities only (`canary-control`,
  `canary-provider-a`, `canary-kuptsi`, `canary-web`, `canary-bootstrap`).
- Canary-only signing key and Vault role, created by a downstream issue. No
  production credential, token, signing key or endpoint is used or copied.
- Version pin: chart 1.2.0 and server 1.31.0, with the same
  `server.config.tls` and `server.config.authorization` values production
  would get. A different version voids the results.
- JWKS is served only over HTTPS with an explicit CA (or the pinned-key
  option chosen in node C). A plaintext JWKS URI is not a valid canary
  configuration.

## Test steps and expected codes

The stock server returns `PermissionDenied` for every denial, including
missing and invalid tokens (matrix doc, consequence 6). `Unauthenticated`
is accepted only if a TLS or proxy layer produces it, and must be recorded.

| Step | ADR test | Action | Expected |
|---|---|---|---|
| S1 | T1 | Call StartWorkflowExecution on `canary-control` with no token | PermissionDenied; `GetSystemInfo` still succeeds |
| S2 | T2 | Expired token | PermissionDenied |
| S3 | T2 | Token with unknown `kid` | PermissionDenied |
| S4 | T2 | Token signed by a different key, forged signature | PermissionDenied |
| S5 | T2 | Token with a wrong `iss` but valid signature | Expected to be ALLOWED by stock code (no `iss` check). Record the result; if allowed, the issuer control is the key only |
| S6 | T2 | Token with wrong `aud`, and with no `aud`, with audience configured | PermissionDenied both |
| S7 | T2 | Same token with `audience` config empty | Allowed (proves the empty setting disables the check); never enable this |
| S8 | T1, T2 | Review check: reject any configuration with a plaintext `keySourceURIs` entry | Review fails; plaintext JWKS is refused before apply |
| S9 | T3, T8 | `canary-provider-a` identity starts, signals, polls on `canary-control` | PermissionDenied |
| S10 | T3, T4 | `canary-kuptsi` identity starts, signals, terminates, polls a workflow and queue named `mctl-dev-loop` in `canary-control` | PermissionDenied for each |
| S11 | T5 | `canary-control` identity calls `canary-kuptsi` | PermissionDenied |
| S12 | T6 | Non-admin identities call RegisterNamespace, UpdateNamespace, AddSearchAttributes, ListNamespaces, GetSearchAttributes | PermissionDenied |
| S13 | T7 | `canary-web` identity (read-only role) attempts every write RPC in the matrix | PermissionDenied; reads succeed across namespaces (confirms read-all) |
| S14 | T9 | Revoke by removing the key and waiting one `refreshInterval`; rotate the key with `verification_ttl` set; replace a pod; stop ESO | Old token rejected within one TTL plus refresh; rotation has no gap; workers recover after ESO returns |
| S15 | T10 | Run synthetic long workflows in each canary namespace through every phase | All complete |
| S16 | T11 | Search canary logs, Loki and workflow histories for the string `eyJ` | No hits |
| S17 | n/a | Test `EnableCrossNamespaceCommands` on and off: child workflow from `canary-kuptsi` to `canary-control` | Denied when on; record behaviour when off |

Every step is run twice, from clean state, by a different operator or session.

## Gates

- **Entry:** matrix has no unresolved cell for any permission used by the map;
  the node C decision is approved; the canary namespace, database and
  NetworkPolicy are approved by an admin; no production credential is mounted.
- **Exit:** all steps pass twice, the rollback rehearsal below succeeds, and
  the unresolved items in the runbook are either closed or accepted by an admin.
- **Rollback rehearsal:** with the authorizer enabled, revert
  `server.config.authorization`, then `server.config.tls`, roll the pods, and
  confirm unauthenticated clients work again within the time recorded in the
  issue (N minutes, to be set by the approver). Then delete the canary release.
- **SLO continuity (before any production phase):** record production DevLoop
  and kuptsi workflow success rate and p95 task latency for 24h before and 24h
  after each phase; the drop tolerance is stated in the phase issue.

## Stop conditions

Stop and do not proceed to production if any of the following holds:
any test fails; audience enforcement is not demonstrated (S6); the issuer
behaviour is not accepted by security (S5); an authenticated JWKS path
cannot be demonstrated (S8); a token appears in a log (S16); the canary
needs a production credential or endpoint; or production SLOs regress.
