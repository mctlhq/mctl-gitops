# Tasks: issue-2456-security-temporal-authenticate-and-autho

Initial state: proposed / blocked for deployment. Tasks 1-2 need no runtime change. Each of tasks 4, 6, 8 and 10 changes live behaviour and needs its own separate human approval.

- [ ] 1. Live inventory (read-only). Record each item below in `docs/runbooks/temporal-client-auth.md` under a "Live evidence (date)" section, kept apart from GitOps desired state:
  - the running server image;
  - the rendered frontend config from the `temporal-config` ConfigMap;
  - `temporal operator namespace list`;
  - connected-client evidence, from frontend logs or `temporal_request` metrics if available;
  - the SDK versions in mctl-api, mctl-agents 1.117.0 and kuptsi-app 0.2.27;
  - whether chart 1.2.0 supports `server.internalFrontend` and `server.config.tls`;
  - the actual default-authorizer role required for each API (poll, start, signal, terminate, list, query) in Temporal 1.31.0 source.

  DoD: every client in the table in design.md is confirmed or corrected. Any caller not on the list is flagged. Each gap is marked "not observed", never as absent.
- [ ] 2. Security ADR `docs/adr/0003-temporal-client-authz.md` plus a rubric (following `docs/adr/0001-rubric.yaml`) (depends on 1). It must select:
  - the identity mechanism (recommended: Vault-signed JWT via ESO `VaultDynamicSecret`);
  - the authorizer (stock default);
  - frontend TLS;
  - the canary or maintenance-window strategy;
  - the temporal-web mode;
  - the trust-domain namespace layout for future `mctl-assistants`.

  It must also state that queue-level authorization is not enforced, and must separate Temporal machine authorization from mctl-api principal/tenant authorization. DoD: the PR is merged with an independent review recorded (a human plus a claude-review pass), and the alternatives are recorded.
- [ ] 3. Cross-repo client support issues: mctl-api, mctl-agents and kuptsi-app (depends on 2). Each must:
  - read `TEMPORAL_TOKEN_FILE` and refresh it at least every 5 minutes, sending `authorization: Bearer`;
  - read `TEMPORAL_TLS_CA_FILE` and `TEMPORAL_TLS_SERVER_NAME`;
  - leave behaviour unchanged when these are unset;
  - never log the token.

  DoD: released image versions are named in the ADR.
- [ ] 4. Credential plumbing in shadow (depends on 2, 3). APPROVAL REQUIRED.
  - Vault config (IaC alongside `vault-human-auth-iac`): the `identity/oidc/key/temporal` key (rotation_period 24h, verification_ttl 2h, allowed_client_ids for each role), one `identity/oidc/role/temporal-<client>` per identity with template `{"permissions": {{identity.entity.metadata.temporal_permissions}}}` and ttl 1h, Kubernetes-auth roles bound to one ServiceAccount each, and entity metadata following the permission map in design.md.
  - ESO `VaultDynamicSecret` generators and `ExternalSecret temporal-token-<client>` (refreshInterval 20m) in `mctl-api`, `admins` (three), `labs` (kuptsi-app) and `temporal` (web, bootstrap).
  - Mount the token at `/var/run/secrets/temporal/token` and set `TEMPORAL_TOKEN_FILE` in `bootstrap/templates/mctl-platform/mctl-api.yaml`, `services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml` and `services/labs/kuptsi-app/values.yaml` (both the main env and the `temporal-worker` extraContainer env).
  - Add the token rows to the inventory in `docs/runbooks/agent-credential-delivery.md`, and extend its CI validator so the volume is rejected on any CWFT or agent pod.

  DoD: every client logs a token `sub` hash and expiry. The server is unchanged. DevLoop and kuptsi alerts stay quiet for 48h.
- [ ] 5. Temporal frontend metrics scrape (`VMServiceScrape` for `temporal` frontend :9090) and `infra-components/observability/vm-rules/temporal-authz-alerts.yaml` (`TemporalAuthzDenials`, `TemporalTokenStale`, `TemporalFrontendCertExpiring`) with promtool tests in `vm-rules/tests/` (depends on 1). DoD: the metrics are visible in VictoriaMetrics, and the tests pass in CI.
- [ ] 6. Frontend TLS (depends on 3, 4, 5). APPROVAL REQUIRED.
  - `ClusterIssuer temporal-internal-ca` with a self-signed bootstrap CA.
  - `Certificate temporal-frontend-tls` in `infra-components/data/temporal/`.
  - The CA public cert reflected to `mctl-api`, `admins` and `labs`.
  - `server.config.tls.frontend` in `bootstrap/templates/data/temporal.yaml` (requireClientAuth false).
  - `TEMPORAL_TLS_CA_FILE` and server name on every client, including `tenant-namespace-job.yaml` and temporal-web (`TEMPORAL_TLS_CA_FILE` / UI TLS env).

  DoD: every client connects over TLS, and a plaintext probe to 7233 fails. DevLoop workflows in flight continue.
- [ ] 7. Authorizer canary or window rehearsal, as the ADR chose (depends on 6). Either a disposable Temporal release in a non-production namespace with the same authorization values and a throwaway database, or a written window plan. DoD: T1–T10 pass on the canary, or the window plan is approved.
- [ ] 8. Authorizer enablement (depends on 7). APPROVAL REQUIRED.
  - Set `server.config.global.authorization` (jwtKeyProvider JWKS URI on vault-active, `permissionsClaimName: permissions`, `authorizer: default`, `claimMapper: default`, audience check) and enable `internalFrontend`.
  - Add a Vault NetworkPolicy peer for the `temporal` frontend pods in `bootstrap/templates/core-infra/vault-netpol.yaml`.
  - Give `tenant-namespace-job.yaml` its token file and `system:admin` identity.
  - Set `TEMPORAL_DISABLE_WRITE_ACTIONS: "true"` on temporal-web, plus its reader token.

  DoD: all legitimate clients are green, and `TemporalAuthzDenials` is zero for legitimate identities over 24h.
- [ ] 9. Negative proof in production (depends on 8). Run T1–T10 with throwaway Vault identities, then delete them. Attach the evidence to the ADR. Update the header of `infra-components/data/temporal/networkpolicy.yaml` so it no longer says "no client authentication", and keep the policy. DoD: all activation gates in #2456 are ticked with links to evidence.
- [ ] 10. (Future, separately approved, not in this proposal.) Register the `mctl-assistants` and `mctl-assistants-provider-<name>` namespaces and identities. DoD: tracked as a new issue that references the ADR.

## Tests

- [ ] T1. No token: `temporal workflow list --namespace mctl-agents` is denied. The same command is also denied against `kuptsi`.
- [ ] T2. Expired token (minted with ttl 1m and used after expiry) is denied. A token signed by an unknown key or issuer is denied. A wrong `aud` is denied.
- [ ] T3. The kuptsi identity is denied start, signal, query, describe, list, terminate and reset against `mctl-agents`.
- [ ] T4. The kuptsi identity polling the `mctl-dev-loop` task queue in `mctl-agents` is denied.
- [ ] T5. A mctl-agents worker identity is denied every operation against `kuptsi`.
- [ ] T6. Every non-admin identity is denied namespace create/update, search-attribute changes and cluster APIs (`system:*`).
- [ ] T7. The temporal-web identity can list and describe in its namespaces. Terminate, signal and reset are denied server-side, not only hidden in the UI.
- [ ] T8. A synthetic "provider" identity with writer on a scratch namespace cannot touch `mctl-agents` or a scratch "control" namespace. This proves the trust-domain split. It also documents, as a known limit, that inside its own namespace the identity can act on any queue.
- [ ] T9. Credential lifecycle:
  - after revocation (disable the Vault role), the client fails within 1 TTL and `TemporalTokenStale` fires;
  - after the signing key rotates, legitimate clients keep working;
  - when a client pod is deleted, the replacement mounts a fresh token and resumes polling;
  - when ESO is down for 30m, clients keep working on the cached token.
- [ ] T10. Continuity: during each of phases 4, 6 and 8, an in-flight DevLoopWorkflow and a kuptsi `TelegramAlbumWorkflow` complete. The `MctlAgents*` worker alerts do not fire. The rollback commit from each phase restores service within 5 minutes.
- [ ] T11. Secret hygiene: grep the worker logs, Loki and the workflow histories of a test DevLoop for the token prefix (`eyJ`). There are no hits. The CI validator rejects a test manifest that mounts `temporal-token-*` into a CWFT pod.

## Rollback

- Phase 8 (authorizer): revert the commit to `bootstrap/templates/data/temporal.yaml`. The frontend restarts without authorization (the current behaviour), and the NetworkPolicy remains the boundary. Clients keep sending ignored tokens. Expected recovery is under 5 minutes, with workflows resuming from history.
- Phase 6 (TLS): revert the server TLS values and the client `TEMPORAL_TLS_*` env in the same commit. The certificates and CA can stay; they are inert.
- Phase 4 (credential plumbing): revert the ExternalSecrets, mounts and env. Clients with `TEMPORAL_TOKEN_FILE` unset send no header. The Vault roles can be left disabled.
- Emergency credential revocation: disable the client's Vault role. For a global stop, rotate `identity/oidc/key/temporal` with a short `verification_ttl`, which invalidates every token. This takes effect only while the authorizer is on.
- Never roll back by deleting `allow-temporal-ingress`. It stays as defense in depth throughout.
