# ADR 0003: Temporal client authentication and authorization

**Status:** Proposed (requires human review plus a claude-review pass; no
runtime change follows from merging it)

Issue: mctlhq/mctl-gitops#2456. Inventory and open evidence:
`docs/runbooks/temporal-client-auth.md`. Rubric: `docs/adr/0003-rubric.yaml`.

## Context

The shared Temporal frontend has no client authentication and no authorizer.
The NetworkPolicy allowlist decides who may connect, not what a connected
client may do: kuptsi-app (`labs`) can today terminate `mctl-agents` DevLoop
workflows. A shared `mctl-assistants` runtime with low-trust provider workers
must not be onboarded on that footing.

## Decision (candidate, gated by live evidence)

1. **Identity:** short-lived (TTL <= 1h) JWTs signed by Vault's identity
   engine, delivered to a file by ESO `VaultDynamicSecret` (clients never
   call Vault; the Vault NetworkPolicy stays unchanged). Each client has its
   own Vault role and ServiceAccount; the permission list lives in Vault
   entity metadata, not in anything the client asserts.
2. **Authorizer:** stock `claimMapper: default` and `authorizer: default`
   (no custom server build). Claim roles are `read`, `write`, `worker`,
   `admin`; cluster scope is `temporal-system:<role>`.
3. **Transport:** TLS on frontend 7233 before any authorizer, so bearer
   tokens never cross the wire in plaintext. `requireClientAuth: false`;
   identity comes from the JWT.
4. **JWKS:** only over authenticated transport (HTTPS with an explicit CA, or
   a separately reviewed pinned-key distribution). A plaintext
   `http://vault-active...` JWKS URI is not approved.
5. **Issuer/audience:** a stable `iss` and an exactly pinned, non-empty
   `aud: temporal-frontend`. The server's actual enforcement of both must be
   proven by negative tests; setting `aud` on a token is not proof. If it
   cannot be demonstrated, STOP: no enablement.
6. **Canary:** a disposable Temporal release with the same authorization
   values and a throwaway database, running negative issuer/audience/role/
   JWKS/TLS tests, is REQUIRED before authorizer enablement. A maintenance
   window is a rollout aid, not a substitute.
7. **temporal-web:** deferred, no assumed token. The stock UI needs
   `temporal-system:read`, which grants read across all namespaces. Either
   explicitly accept an admin-only read-all UI or separately review a
   narrower design. `TEMPORAL_DISABLE_WRITE_ACTIONS` is a UI control only,
   not server-side proof of read-only.
8. **Trust-domain layout:** one Temporal namespace per trust domain.
   Candidate permission map (names are candidates until the role/RPC matrix
   is source-backed):

   | Identity | permissions |
   |---|---|
   | temporal-mctl-api | `mctl-agents:write` |
   | temporal-mctl-agents-{control,exec,implement} | `mctl-agents:write` (narrow to `worker` only if proven) |
   | temporal-kuptsi | `kuptsi:write` |
   | temporal-bootstrap (Job only) | `temporal-system:admin` |
   | future assistants control | `mctl-assistants:write` |
   | future provider `<name>` | `mctl-assistants-provider-<name>:write` only |

## Known limits

- Queue-level authorization is NOT enforced: the default authorizer has no
  task-queue dimension. A writer on a namespace can poll any queue in it and
  start, signal or terminate any workflow in it. Isolation comes from
  separate Temporal namespaces plus the NetworkPolicy.
- Temporal machine/namespace authorization (this ADR) is separate from
  mctl-api principal/tenant authorization, which remains the only place that
  distinguishes tenant A's workflow from tenant B's inside a namespace.
- Credentials never reach an LLM: the token is mounted only into long-running
  worker Deployments and mctl-api, never into CWFT/agent pods.

## Alternatives considered

1. NetworkPolicy only: cannot separate two allowed clients. Rejected.
2. mTLS client certs with a custom ClaimMapper: needs a custom server build.
   Fallback only; frontend TLS is reused either way.
3. Projected SA tokens with a custom ClaimMapper: same custom-build cost, no
   `permissions` claim. Rejected.
4. Authorizing gateway (Envoy ext_authz): namespace is inside protobuf
   bodies; bypass risk; hot-path component. Rejected.
5. Separate Temporal clusters per trust domain: strongest, but about 1.5Gi
   requests each. Revisit for a high-risk provider.

## Rollout and rollback

Each phase is a separate DevLoop issue (see the runbook). Rollback per
phase is one revert, but is not considered proven until rehearsed on the
canary: authorizer (revert `global.authorization`; NetworkPolicy remains),
TLS (revert server TLS and client env together), credential plumbing (unset
`TEMPORAL_TOKEN_FILE`). Emergency revocation: disable the client's Vault
role (effect within 1 TTL); global stop by rotating the signing key with a
short `verification_ttl` (effective only while the authorizer is on).
Never delete `allow-temporal-ingress`.

## Required negative tests (canary, then production)

T1 no token denied; T2 expired/unknown-key/wrong-issuer/wrong-aud denied;
T3 kuptsi denied everything on mctl-agents; T4 kuptsi cannot poll
`mctl-dev-loop`; T5 agents workers denied on kuptsi; T6 non-admin denied
namespace and cluster APIs; T7 web identity (if enabled) denied writes
server-side; T8 synthetic provider identity isolated from control
namespaces; T9 credential lifecycle (revocation, key rotation, pod
replacement, ESO outage); T10 in-flight DevLoop and kuptsi workflows survive
each phase; T11 no token (`eyJ`) in logs, Loki or histories.

## Open items

Live evidence in the runbook is entirely "not observed" at the time of
writing; this ADR must not move beyond Proposed until it is filled.

Spike #2469 evidence: `docs/runbooks/temporal-authz-role-matrix.md` and
`docs/runbooks/temporal-auth-canary.md`; verdict in `docs/runbooks/temporal-client-auth.md`. Status stays `Proposed`.
