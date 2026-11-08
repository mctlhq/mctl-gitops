# Authenticate and authorize Temporal frontend clients before the shared assistants rollout

## Context

The shared Temporal cluster (`platform-gitops/bootstrap/templates/data/temporal.yaml`, chart 1.2.0, server 1.31.0) runs with no client authentication and no authorizer. The header of `platform-gitops/infra-components/data/temporal/networkpolicy.yaml` says so directly: any pod that can reach `temporal-frontend.temporal.svc.cluster.local:7233` can start, signal, query, list or terminate workflows in every Temporal namespace (`kuptsi` and `mctl-agents`, registered by `infra-components/data/temporal/tenant-namespace-job.yaml`). Today the NetworkPolicy allowlist from #1810 and #1818 is the only boundary. It decides who may connect, but not what a connected client may do once it is in. As a result, the one tenant client (kuptsi-app in `labs`) can terminate `mctl-agents` DevLoop workflows. A future low-trust provider worker in a shared `mctl-assistants` runtime could do the same to control-plane workflows.

Issue #2456 asks for three things before any shared multi-tenant assistant runtime is onboarded:
- an authenticated machine identity for every Temporal client;
- a server-side authorizer that limits each identity to its own Temporal namespaces and operations;
- a phased rollout with evidence: inventory, an ADR, negative tests, rotation, alarms and rollback.

**Approval boundary (AMEND 2026-11-08): only live read-only inventory, a reviewed security ADR, permission/issuer/audience proof and a *plan* for follow-up issues are authorized by this proposal. Tasks 3-10 are specifications for distinct future DevLoop issues/PRs, not executable work under this approval. No Vault, ESO, SDK, TLS, authorizer, namespace or deployed-config writes, and no in-cluster test that alters behaviour.** Every phase that changes live behaviour needs an independently reviewed proposal, human approval, immutable image pin, verified canary evidence and rollback gate. Initial state remains `proposed / blocked for deployment`.

## User stories

- AS a platform operator I WANT every Temporal frontend call to carry a verifiable machine identity SO THAT a reachable socket is no longer enough to control workflows.
- AS the mctl-agents DevLoop owner I WANT only mctl-api and the mctl-agents workers to be able to touch the `mctl-agents` namespace SO THAT a tenant or provider worker cannot terminate, signal or forge DevLoop workflows.
- AS a tenant (kuptsi) owner I WANT my workers to keep running through the rollout SO THAT the security change does not break my SLO.
- AS a security reviewer I WANT a written ADR and a live negative test matrix SO THAT the isolation claims are proven, not assumed.
- AS the future shared-assistants owner I WANT trust domains split into separate Temporal namespaces SO THAT a low-trust provider worker cannot mutate trusted control workflows, even though Temporal cannot isolate task queues inside one namespace.
- AS an on-call engineer I WANT alarms on authorization denials and credential expiry, plus a one-commit rollback, SO THAT a broken rollout is found and reverted in minutes.

## Acceptance criteria (EARS)

Design and decision:
- WHEN the proposal is accepted THE SYSTEM SHALL have a security ADR under `docs/adr/` that selects one Temporal-supported client-authentication mechanism and one authorizer configuration, records the alternatives that were rejected, and has an independent review recorded on its PR.
- THE SYSTEM SHALL document which controls Temporal server 1.31.0 actually enforces: namespace-level roles. It SHALL state explicitly that task-queue-level authorization is NOT enforced by the stock authorizer and SHALL use separate Temporal namespaces (trust domains) wherever queue isolation would otherwise be needed.
- WHEN the inventory task runs THE SYSTEM SHALL record live evidence, kept separate from GitOps desired state, of the server version, the registered namespaces, the connected clients (SDK and version), the TLS state and the current frontend config.

Identity and least privilege:
- WHILE the authorizer is enabled THE SYSTEM SHALL map each client identity to exactly these Temporal permissions:
  - mctl-api: `mctl-agents:write`;
  - the mctl-agents control/exec/implement workers: `mctl-agents:write`;
  - kuptsi-app (API and temporal-worker): `kuptsi:write`;
  - temporal-web: read-only on the namespaces the ADR names;
  - the namespace bootstrap Job: system admin, delivered only to that Job.
- IF a request carries no credential, an expired credential, a credential from an unknown issuer, or a credential with no permission for the target namespace THEN THE SYSTEM SHALL reject it with PermissionDenied/Unauthenticated. This SHALL cover start, signal, query, describe, list, terminate, reset, poll, and namespace or schedule operations.
- IF a client authorized only for namespace A calls any API against namespace B THEN THE SYSTEM SHALL deny the call.
- WHERE a shared assistants runtime is later added THE SYSTEM SHALL place the trusted assistant control worker and each low-trust provider worker in separate Temporal namespaces. No provider identity SHALL hold any role on the control namespace or on `mctl-agents`.
- THE SYSTEM SHALL NOT expose any Temporal credential to LLM-driven processes. That covers Argo CWFT agent pods, Claude CLI subprocesses, MCP tools, logs, workflow inputs and histories, and user-controlled ingress.

Credentials and lifecycle:
- WHILE a client runs THE SYSTEM SHALL deliver its Temporal credential as a short-lived token (TTL no longer than 1h). The token SHALL be refreshed from Vault before expiry and read from a mounted file on every connection or refresh, never baked into env or images.
- WHEN a client identity is revoked in Vault THE SYSTEM SHALL stop that client from obtaining new tokens. Access SHALL end within one token TTL.
- WHEN the frontend TLS phase is enabled THE SYSTEM SHALL serve TLS on 7233 with a certificate from an in-cluster CA issued by cert-manager and rotated by cert-manager. Clients SHALL verify the certificate against the distributed CA bundle.

Rollout, observability, continuity:
- In later separately approved issues (NOT this proposal), THE SYSTEM SHALL roll out in independently approved phases:
  0. ADR and inventory;
  1. credential issuance, with clients sending tokens that the server ignores;
  2. frontend TLS cut-over;
  3. authorizer enablement;
  4. negative test proof.
  Each phase SHALL be a separate PR with its own rollback.
- WHILE any phase is rolling out THE SYSTEM SHALL keep existing `mctl-agents` DevLoop workflows and `kuptsi` workflows progressing. The existing `MctlAgents*` worker alerts in `infra-components/observability/vm-rules/mctl-agents-worker-alerts.yaml` SHALL NOT fire because of the rollout.
- WHEN the authorizer is enabled THE SYSTEM SHALL scrape Temporal frontend metrics and alert on a sustained rate of authorization failures per namespace. It SHALL also alert when a client token file is older than its refresh deadline.
- IF the authorizer phase causes legitimate client failures THEN THE SYSTEM SHALL be revertible by reverting a single commit to `bootstrap/templates/data/temporal.yaml`, which restores the previous unauthenticated behaviour while the NetworkPolicy allowlist stays in place.
- THE SYSTEM SHALL keep the NetworkPolicy `allow-temporal-ingress` as defense in depth after authorization is enabled.
- BEFORE any JWT/authorizer change THE SYSTEM SHALL verify in Temporal **server 1.31.0** the exact JWT syntax, role-to-RPC matrix, configured accepted issuer and non-empty exact JWT audience, plus negative cases (wrong `aud`, `iss`, `exp`, missing token). The stock role values MUST be `read`, `write`, `worker`, `admin`, and system scope MUST be `temporal-system:<role>`; `reader`, `writer` and `system:admin` are not accepted spellings. Source: https://docs.temporal.io/production-deployment/self-hosted-guide/security .
- BEFORE a frontend reads Vault JWKS THE SYSTEM SHALL validate that its issuer key set is obtained over authenticated TLS (or an independently pinned trusted key distribution); plain `http://` JWKS from another pod is not acceptable, even if it returns public material.
- Temporal Web UI requires cluster-level list/get-cluster calls: `temporal-system:read` grants **read to every namespace**, not just the named `kuptsi`/`mctl-agents` namespaces. The ADR MUST decide explicitly whether privileged admin-only UI read-all is acceptable; otherwise keep the UI disabled until a restricted authorizer/UI proxy is separately approved. Hiding write buttons never substitutes for a server-side denial.

Separation of concerns:
- THE SYSTEM SHALL document that Temporal authorization is machine and namespace authorization only. Per-user, per-tenant and per-order authorization inside a shared namespace remains the responsibility of mctl-api and SHALL be enforced there separately. Both layers are required.

## Out of scope

- Creating the `mctl-assistants` namespace(s), a Glovo production runtime, payments or live orders. This proposal only designs the trust-domain layout they would use.
- Bypassing or replacing connector #1048.
- A new scheduler, or any automatic rollout. Every live phase is triggered by a human-approved PR.
- Internode (history/matching/worker) TLS inside the `temporal` namespace. The ADR may list it as a follow-up.
- Code changes inside mctl-api, mctl-agents and kuptsi-app. They are tracked as cross-repo dependencies: this repo provides the config, credentials and env, and those repos must read the token file and the CA bundle.
- Per-task-queue authorization, which the stock Temporal server does not enforce.

## Open questions

- Credential mechanism. The ADR must confirm the recommended option: stock server, default JWT claim mapper and default authorizer, with JWTs minted by Vault's identity OIDC token endpoint through the ESO `VaultDynamicSecret` generator. The main alternative is a custom ClaimMapper that accepts projected Kubernetes ServiceAccount tokens. That alternative removes Vault from the hot path but requires maintaining a custom Temporal server build.
- Temporal 1.31.0 role semantics. Does the default authorizer let a `worker`-role identity poll without being able to start or terminate? This must be checked against the server source. Until it is proven, workers are planned as `writer`, with isolation provided by namespaces.
- Does chart 1.2.0 expose `server.internalFrontend` so that the server's own system worker keeps working once the authorizer is on? This must be confirmed during the inventory task.
- temporal-web identity. Option one: forward the user's OIDC token via the UI's auth settings, which requires a permissions claim from Zitadel. Option two: run the UI on a read-only machine token with `TEMPORAL_DISABLE_WRITE_ACTIONS=true`. Today any user who passes the `admins` forward-auth can terminate workflows from the UI.
- Canary environment. The cluster has a single Temporal install, and the authorizer cannot be enabled per namespace. The ADR must decide between a disposable second Temporal release for pre-flip validation (extra shared-pg database and about 1.5Gi memory) and a timed maintenance-window flip with immediate rollback.
- Live-state gaps. This run had no access to the `temporal` namespace (frontend config, namespace list, SDK versions of connected clients). The inventory task must collect them.
