# Design: issue-2540-adr-temporal-jwks-trust-path-decision-fo

## Current state

Documents (decision trail, all `Proposed` / document-only):

- `docs/adr/0003-temporal-client-authz.md`: decision 1 (Vault-signed JWT,
  ESO-delivered file), decision 4 ("JWKS only over authenticated transport
  (HTTPS with an explicit CA, or a separately reviewed pinned-key
  distribution). A plaintext `http://vault-active...` JWKS URI is not
  approved."), decision 5 (pinned `aud`), decision 6 (canary required),
  "Rollout and rollback" (global stop by rotating the signing key with a short
  `verification_ttl`). Rubric `docs/adr/0003-rubric.yaml`.
- `docs/runbooks/temporal-client-auth.md`: verdict `BLOCKED`; unresolved
  unknown 4 ("How a pinned-key or HTTPS-with-CA JWKS source is delivered given
  the stock provider's limits"); DAG node C row (repo mctl-gitops ADR, owner
  platform security, architecture review, admin approval, rollback none,
  before D and F, stop "no authenticated option reviewed").
- `docs/runbooks/temporal-authz-role-matrix.md` lines 112-118: `iss` not
  validated (`default_jwt_claim_mapper.go:194`); key source is
  `jwtKeyProvider.keySourceURIs` + `refreshInterval` (`config.go:647-650`),
  fetched with `http.Get` and parsed as JWKS
  (`default_token_key_provider.go:141-153`), system roots only, no CA file, no
  `file://`, no inline key; a failed refresh keeps old keys; `refreshInterval
  0` loads once at start. HTTPS-with-CA "needs the CA added to the Temporal
  image trust store (for example via `SSL_CERT_FILE`/`SSL_CERT_DIR`)".
- `docs/runbooks/temporal-auth-canary.md`: Isolation bullet "JWKS is served
  only over HTTPS with an explicit CA (or the pinned-key option chosen in node
  C)"; S8 rejects plaintext `keySourceURIs`; S14 covers revocation/rotation;
  stop condition "an authenticated JWKS path cannot be demonstrated (S8)".
- `docs/spikes/2506-temporal-jwt-issuer.md`: verdict `HYBRID_WITH_BOUNDARIES`;
  boundary 2 "Vault issues Temporal workload JWTs from a dedicated named key
  whose JWKS contains no other key"; precondition "`.well-known/keys` serves
  only the Temporal key" (NOT_OBSERVED, canary T2b); new canary steps T2b,
  T2c, T9b, T9c; section 9 proposed ADR 0003 amendment; fallback
  `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH`.

Manifests:

- `platform-gitops/bootstrap/templates/data/temporal.yaml`: chart `temporal`
  1.2.0 (server 1.31.0), `server.replicaCount: 1`, no `server.config.tls`, no
  `server.config.authorization`; persistence to shared-pg with
  `connectProtocol: tcp` (no outbound TLS from the server today); second
  source `platform-gitops/infra-components/data/temporal/` holds only
  `externalsecret.yaml`, `networkpolicy.yaml`, `tenant-namespace-job.yaml`.
- `platform-gitops/bootstrap/templates/core-infra/vault.yaml`: chart 0.28.1,
  3-node Raft HA, listener `tls_disable = 1` with the SOC F15 comment
  ("Enabling a TLS listener is a Raft/cert change ... not a contained
  rollback"), edge TLS only at Traefik for `secrets.mctl.ai`
  (`letsencrypt-prod`).
- `platform-gitops/bootstrap/templates/core-infra/vault-netpol.yaml`:
  `allow-vault-ingress` allowlist (ESO, Traefik, mctl-api, argo-workflows,
  ...); `temporal` is not a peer.
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` (around
  line 151): mctl-api uses in-cluster Vault because `https://secrets.mctl.ai`
  timed out from inside the cluster for five hours on 2026-10-09.
- cert-manager is deployed; only ACME ClusterIssuers (`letsencrypt-prod`,
  `letsencrypt-staging`, `letsencrypt-http01`) exist, owned by Terraform
  (`infrastructure/k3s-preview/extra-manifests/letsencrypt-*.yaml.tpl`,
  `platform-gitops/bootstrap/templates/core-infra/cert-manager-dns01.yaml`).
  No CA or selfSigned issuer and no trust-manager `Bundle` exist in the repo.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/bootstrap/templates/data/temporal.yaml` and
  `$MCTL_GITOPS_ROOT/bootstrap/templates/core-infra/vault.yaml`: byte-identical
  to the clone (`diff -q`, no output). Same desired state: no TLS, no
  authorizer, Vault plaintext listener.
- `$MCTL_GITOPS_ROOT/infra-components/data/temporal/`: only
  `externalsecret.yaml`, `networkpolicy.yaml`, `tenant-namespace-job.yaml`.
- grep for `identity/oidc` and `VaultDynamicSecret` under
  `$MCTL_GITOPS_ROOT/bootstrap` and `infra-components`: no hits (no Vault OIDC
  key/role or dynamic secret is declared).
- `mctl_list_services team=admins`: `mctl-agents-worker{,-exec,-implement}` at
  1.117.0 deployed (worker is `OutOfSync`, unrelated to this decision). The
  Temporal server itself is a platform Argo CD Application, not a catalogue
  service, so no MCP tool in this run reads its live config.
- Live Temporal facts (server image 1.31.0, rendered config with no `tls:` or
  `authorization:` block, empty dynamic config) are cited from the operator
  session of 2026-11-09 recorded in `docs/runbooks/temporal-client-auth.md`;
  they were not re-observed in this run.
- NOT_OBSERVED in this run: Vault server version (`vault status`), Vault
  named-key `rotation_period` limits, chart 1.2.0 frontend
  sidecar/env/volume keys, `SSL_CERT_FILE` behaviour of the shipped server
  binary. Each is recorded as an open question and a canary step, not
  assumed.

## Proposed solution

Deliverable: a new decision document `docs/adr/0004-temporal-jwks-trust-path.md`
(status `Proposed`), a scoring rubric `docs/adr/0004-rubric.yaml` in the
0003-rubric format, and pointer-only edits to ADR 0003, the client-auth
runbook and the canary contract. A new ADR is preferred over amending ADR 0003
in place because ADR 0003 is still `Proposed` with its own review trail and
spike #2506 already carries an unadopted amendment to it; node C has its own
owner (platform security) and approval gate in the DAG table.

### Selected trust path: GitOps-pinned JWKS over loopback HTTPS (option 3)

1. **Key material.** Vault keeps signing (spike #2506 boundary 2) with one or
   two dedicated identity named keys, `temporal-a` / `temporal-b` (names are
   proposals for node D), each with `allowed_client_ids` limited to the
   Temporal roles. The private key never leaves Vault.
2. **Pinned JWKS document.** The public JWKS for exactly the active Temporal
   key(s) is committed to Git as a ConfigMap in the `temporal` namespace
   (for example `platform-gitops/infra-components/data/temporal/jwks-configmap.yaml`,
   created by node F/G, not now). Public keys are not secrets, so this
   follows the "no secrets in YAML" rule. The operator obtains the JWK by
   reading Vault's `.well-known/keys` over `https://secrets.mctl.ai` (system
   roots) and extracts only the Temporal `kid`; a CI check (node D) compares
   the committed `kid`/`n`/`e` with Vault and fails on drift.
   Authentication of the JWKS bytes is Git review plus Argo CD, which is
   already the trust root for `server.config.authorization` itself: anyone
   who can change the pinned JWKS could equally change the authorizer config,
   so no new principal enters the trusted computing base.
3. **Transport.** A static HTTPS file server runs next to the frontend
   (preferred: a Kubernetes native sidecar, an init container with
   `restartPolicy: Always`, so it is Ready before the frontend container
   starts; k3s 1.34 supports this). It listens on `127.0.0.1` only and serves
   the ConfigMap at `https://localhost:<port>/jwks.json`.
   `server.config.authorization.jwtKeyProvider.keySourceURIs` names only that
   URI. The bytes never cross the pod network, so the plaintext-Vault and
   Cloudflare-path problems do not apply. `http://`, including
   `http://127.0.0.1`, stays rejected (issue rule, ADR 0003 decision 4, canary S8).
4. **Trust root delivery.** A namespace-scoped cert-manager `Issuer` chain in
   `temporal` (selfSigned issuer, then a CA `Certificate` with a long
   lifetime, then a CA `Issuer`, then a leaf `Certificate` for `localhost` /
   `127.0.0.1`). The frontend container gets `SSL_CERT_FILE` pointing at the
   mounted CA `ca.crt` only. Go's `crypto/x509` then uses that file *instead
   of* the system bundle. This narrows the frontend's trust to one pod-local
   CA. The frontend makes no other outbound TLS call today. The CA is
   separate from node E's frontend serving CA, so a node E compromise does
   not let anyone forge the JWKS server. Leaf renewal under the same CA needs
   no frontend restart. The sidecar must reload or be restarted on renewal,
   and node F/G picks the mechanism. "reloader" appears in
   `bootstrap/templates/observability/monitoring.yaml`, but whether it can
   watch the `temporal` namespace was not checked. CA rotation requires a frontend restart and is
   scheduled, never automatic.
5. **Fallback form** (if chart 1.2.0 cannot add a frontend-only sidecar): a
   separate `temporal-jwks` Deployment + ClusterIP Service in `temporal`
   serving the same ConfigMap over HTTPS with a leaf from the same pod-local
   CA. The transport is then the in-namespace pod network, still
   TLS-authenticated, behind `allow-temporal-ingress` (intra-namespace only).
   The authentication strength is the same, but there is one more moving part.

### Key rotation procedure (planned, zero gap)

Vault automatic rotation of the active Temporal key is prohibited:
`rotation_period` is set longer than the manual cadence, and node B alerts
when Vault's current Temporal `kid` is not in the pinned JWKS.

1. Create (or reuse the standby slot) named key `temporal-b` in Vault (node D tooling).
2. PR: add `temporal-b`'s public JWK to the pinned JWKS (now A+B). Merge, wait
   for Argo CD sync plus one `refreshInterval` (proposed `1m`). Verify via the
   frontend metric/log that both `kid`s are loaded.
3. Switch every Temporal Vault role's `key` to `temporal-b`. New tokens are
   signed by B; old A tokens stay valid until `exp` (TTL <= 1h).
4. Wait one token TTL plus one ESO refresh interval.
5. PR: remove `temporal-a` from the pinned JWKS. Merge, then wait for sync and `refreshInterval`.
6. Rotate or delete `temporal-a` in Vault. It becomes the standby slot for the next rotation.

### Emergency revocation

- One identity: disable its Vault role (ADR 0003, effect within one TTL).
  Unchanged.
- Signing-key compromise: a PR that removes the compromised `kid` (and adds a
  fresh key if one is staged), merged without waiting for the normal review
  cadence. The effect time is merge plus Argo CD sync plus `refreshInterval`,
  with a proposed target of <= 15 min. The ADR also documents a break-glass:
  scale the frontend to 0 (all Temporal traffic stops, fail closed). This
  replaces ADR 0003's "rotate the signing key with a short
  `verification_ttl`", which only works for a JWKS fetched live from Vault.

### Failure modes (fail closed)

- JWKS server unreachable during a refresh: the stock provider keeps the
  last loaded keys and logs an error (matrix doc). Tokens keep verifying.
  Revocation by key removal is delayed until the server is back. Node B alerts
  on the refresh error log or metric.
- Frontend starts while the JWKS server is down or the CA file is missing: no
  keys are loaded and every authenticated call gets `PermissionDenied`. The
  native-sidecar ordering makes this rare. It cannot fail open, because the
  provider has no fallback key source.
- Malformed or empty ConfigMap: same as above. A CI check (node D) validates
  the JWKS schema and the `kid` set before merge.
- CA or leaf expiry: TLS handshake fails, which is the same as unreachable.
  cert-manager renews the leaf, and expiry alerts come from node B.

### Canary obligations (node F) per option

Applies on top of S1-S17 and #2506 T2b/T2c/T9b/T9c.

| ID | Selected option (pinned loopback HTTPS) must prove |
|---|---|
| C1 | `SSL_CERT_FILE` is honoured by `temporalio/server:1.31.0`: the frontend loads keys from `https://localhost` with the pod-local CA, and fails to load them (logged TLS error) when `SSL_CERT_FILE` is unset or points at the system bundle. Stop if not honoured |
| C2 | A JWKS server presenting a leaf from a different CA (simulated MITM) is rejected: no keys loaded, all calls denied |
| C3 | Exclusivity: a token signed by a second Vault named key that is not in the pinned file is denied. This is T2b, now expected to pass by construction |
| C4 | Planned rotation steps 1-6 with continuous synthetic traffic: zero `PermissionDenied` (extends T9b/S14) |
| C5 | Emergency removal: time from merge to denial of the removed `kid` is measured and meets the approver's target |
| C6 | T9c: sidecar killed during a refresh keeps the old keys. Frontend restarted while the sidecar is down denies everything, and recovers when the sidecar returns. Record recovery time |
| C7 | S8 extended: configs with `http://` (including `http://127.0.0.1`) or with any non-loopback `keySourceURIs` entry fail review |
| C8 | Vault auto-rotation guard: the `kid`-mismatch alert fires when the canary Vault key is rotated out of band |

Rejected options keep their own obligations in the ADR (for reopen):

- **Option 1 (HTTPS to Vault with internal CA):** TLS-terminating proxy or
  listener proven in front of Vault, JWKS exclusivity (T2b) shown with a
  second named key present, CA delivery (C1/C2), Vault-reachability outage
  behaviour (T9c), automatic Vault rotation with `verification_ttl` (T9b).
- **Option 1b (public `secrets.mctl.ai`):** the same plus a Cloudflare-path
  outage test, which repeats the 2026-10-09 failure mode.
- **Option 2 (custom key provider build):** all S1-S17 rerun on the custom
  image, an upgrade-diff review for every Temporal minor release, and
  signature/provenance of the custom image.

## Alternatives

1. **HTTPS JWKS from Vault with an internal CA in the server trust store
   (issue option 1).** The CA would go in through `SSL_CERT_FILE` (the same
   mechanism as the selected option). Vault serves HTTPS either through its
   own TLS listener or through a TLS sidecar in the Vault pods. Rejected:
   (a) a TLS listener is the SOC F15 change that `vault.yaml` itself calls
   "not a contained rollback"; a sidecar still rolls the 3-node Raft
   StatefulSet. (b) JWKS exclusivity is not guaranteed: if
   `.well-known/keys` serves every named key in the Vault namespace (#2506,
   NOT_OBSERVED), any other Vault OIDC consumer's key becomes a Temporal
   issuer, and a pass-through proxy cannot filter it. (c) `temporal` would
   need a new `allow-vault-ingress` peer, which widens reachability to the
   secret store. (d) Temporal authorization becomes a runtime dependency on
   Vault availability. Its advantages, automatic rotation with
   `verification_ttl` and revocation without a PR, do not outweigh (b).
   - 1b, public `https://secrets.mctl.ai` with system roots: no CA work, but
     Cloudflare and the public path enter the TCB, the 2026-10-09 in-cluster
     timeout is a recorded failure mode, and (b) still applies. Rejected.
2. **Pinned key via a custom key provider or authorizer build (issue option
   2).** Temporal accepts a custom `TokenKeyProvider` only through a custom
   server binary. That would add an mctl-owned server image, a rebuild and
   review on every Temporal release (1.31.0 today), and supply-chain
   provenance work, and it contradicts ADR 0003's "no custom server build" and
   the rubric's `stock_binary` weight 25. Rejected; the selected option gets
   the pinned-key property on the stock binary.
3. **Loopback `http://127.0.0.1` JWKS (no TLS).** Technically the bytes never
   leave the pod, but this breaks the explicit issue rule and canary S8, and
   any non-loopback mistake in the URI would silently become a spoofable
   source. Rejected.

## Platform impact

- **Migrations / backward compatibility:** none. The change is documentation
  only. ADR 0003 stays `Proposed`. The client-auth runbook verdict stays
  `BLOCKED` until nodes D-H run. Spike #2506's verdict condition ("an
  authenticated JWKS path for the `temporal` namespace") becomes satisfiable,
  pending canary C1-C8.
- **Resource impact (future, nodes F/G):** one small static file-server
  container per frontend pod (estimate 10m CPU / 16Mi), or one extra
  Deployment in the fallback form; cert-manager objects in `temporal`. No
  Vault change, and no new NetworkPolicy peer on Vault.
- **Risks and mitigations:**
  - Operator forgets to add the new key before switching roles, so every new
    token fails. Mitigations: the documented order, the CI `kid` check, the
    node B mismatch alert, and the canary rehearsal C4.
  - Vault auto-rotates the key. Mitigations: long `rotation_period`, the
    mismatch alert, and canary C8. Open question on the version-specific
    limits.
  - Revocation latency depends on Git and Argo CD. Mitigations: the
    break-glass (frontend scale-to-zero), a target recorded by the approver,
    and canary C5.
  - `SSL_CERT_FILE` is not honoured by the shipped binary. Canary C1 is a
    stop condition; the ADR outcome then falls back to
    `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH`.
  - Chart 1.2.0 cannot inject a frontend sidecar. Use the fallback Deployment
    form (same authentication, documented).
