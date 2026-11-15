# ADR 0004: JWKS trust path for Temporal workload JWT verification (DAG node C)

## Context

ADR 0003 (`docs/adr/0003-temporal-client-authz.md`) chose Vault-signed
workload JWTs verified by the stock Temporal claim mapper and authorizer, but
left decision 4 (JWKS transport) open. Spike #2469
(`docs/runbooks/temporal-authz-role-matrix.md`, "Key source" and "Plaintext
in-cluster JWKS" rows) established that the stock v1.31.0 key provider
fetches `jwtKeyProvider.keySourceURIs` with Go `http.Get`, trusts only the
system roots, and has no CA-file, `file://` or inline-key option. The stock
claim mapper does not validate `iss`, so the key set the frontend loads is the
ONLY issuer control: whoever can influence the JWKS bytes can mint any
Temporal permission. The only in-cluster Vault listener is plaintext
(`platform-gitops/bootstrap/templates/core-infra/vault.yaml`, `tls_disable =
1`, SOC F15 accepted residual), and the public `https://secrets.mctl.ai` path
is Cloudflare-fronted and failed from inside the cluster for five hours on
2026-10-09 (`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`
comment). Spike #2506 (`docs/spikes/2506-temporal-jwt-issuer.md`) chose
`HYBRID_WITH_BOUNDARIES` (Vault issues Temporal workload JWTs from a dedicated
named key whose JWKS contains no other key), explicitly conditional on this
node, with fallback `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH`.

Issue #2540 asks for a decision-only ADR that picks one authenticated JWKS
trust path, rejects `http://`, and records the key-rotation procedure, the
fail-closed behaviour when JWKS is unreachable, and what the disposable
canary (node F, `docs/runbooks/temporal-auth-canary.md`) must prove for each
option. This proposal writes a new ADR 0004 that selects a **GitOps-pinned
JWKS served over loopback HTTPS inside the Temporal frontend pod, trusted via
a pod-local CA set as the frontend's only trust root** (option 3 in the
issue, "another option with equivalent authentication"), and records options
1 and 2 as reviewed and rejected with their canary obligations. No runtime
change is made.

## User stories

- AS a platform security reviewer I WANT one authenticated JWKS trust path
  chosen and justified SO THAT node D (credential plumbing) and node F
  (canary) have a fixed target and spike #2506's conditional verdict can be
  relied on.
- AS a platform operator I WANT a written key-rotation and emergency-revocation
  procedure SO THAT I can rotate or kill the Temporal signing key at 03:00
  without a validation gap and without touching any non-Temporal Vault consumer.
- AS the node F canary owner I WANT a per-option list of what the canary must
  prove SO THAT the canary's JWKS-related steps and stop conditions are
  unambiguous.
- AS an ADR 0003 reader I WANT decision 4 to point at the accepted trust-path
  ADR SO THAT the "HTTPS with an explicit CA, or a pinned-key distribution"
  placeholder is resolved in one place.

## Acceptance criteria (EARS)

- WHEN the ADR is merged THE SYSTEM SHALL contain `docs/adr/0004-temporal-jwks-trust-path.md`
  with status `Proposed`, naming exactly one selected trust path and the
  issue (#2540), ADR 0003, spike #2469 and spike #2506 as inputs.
- THE SYSTEM SHALL record in ADR 0004 that any `keySourceURIs` entry with an
  `http://` scheme is rejected, including loopback `http://127.0.0.1`.
- THE SYSTEM SHALL record in ADR 0004 the reviewed options (HTTPS to Vault
  with an internal CA; public `https://secrets.mctl.ai`; custom key provider
  build; GitOps-pinned loopback HTTPS JWKS) with the reason each was selected
  or rejected.
- THE SYSTEM SHALL record in ADR 0004 that the selected JWKS document contains
  only public keys of dedicated Temporal Vault named keys, so JWKS exclusivity
  (spike #2506 boundary 2, canary T2b) holds by construction.
- THE SYSTEM SHALL record in ADR 0004 a planned zero-gap rotation procedure
  (add new public key, switch Vault roles, wait one token TTL plus one
  `refreshInterval`, remove old key) and an emergency-revocation procedure
  with its expected time to effect.
- THE SYSTEM SHALL record in ADR 0004 that Vault automatic rotation of a
  pinned key is prohibited, because an unannounced rotation would make every
  newly issued token fail verification.
- IF the JWKS source is unreachable during a refresh THEN THE SYSTEM SHALL be
  documented as keeping the previously loaded keys (stock behaviour), and IF
  the frontend starts while the JWKS source is unreachable THEN THE SYSTEM
  SHALL be documented as denying every authenticated call (fail closed), with
  the startup-ordering mitigation recorded.
- THE SYSTEM SHALL record in ADR 0004, for each reviewed option, the canary
  steps that node F must pass, mapped onto the existing S1-S17 and the #2506
  T2b/T2c/T9b/T9c steps, plus the new steps introduced by the selected option.
- WHEN ADR 0004 is merged THE SYSTEM SHALL amend ADR 0003 decision 4 and its
  "Open items" with a pointer to ADR 0004, and update the node C row and
  "Unresolved unknowns" item 4 in `docs/runbooks/temporal-client-auth.md`,
  and the JWKS bullet under "Isolation" in `docs/runbooks/temporal-auth-canary.md`,
  without changing any other decision or status.
- WHILE ADR 0004 is `Proposed` THE SYSTEM SHALL contain no change under
  `platform-gitops/` or `infrastructure/` caused by this proposal.
- IF the architecture review finds no reviewed option acceptable THEN THE
  SYSTEM SHALL record outcome `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH` in
  ADR 0004 instead of a selection (issue stop condition).

## Out of scope

- Any runtime change: Vault OIDC keys or roles, ExternalSecrets, cert-manager
  Issuers or Certificates, Temporal chart values, sidecars, NetworkPolicies
  (nodes D, E, F, G).
- Enabling a TLS listener on Vault (SOC F15 residual stays as is).
- Frontend gRPC TLS on 7233 (node E), although the ADR notes how the two CAs
  relate.
- Choosing the issuer (settled by spike #2506) or the permission map (ADR 0003
  decision 8).
- Approving ADR 0003 or moving it out of `Proposed`.

## Open questions

- Whether chart `temporal` 1.2.0 can add a container, volumes and env vars to
  the frontend Deployment only (for example `server.frontend.additionalEnv`,
  `additionalVolumes`, `sidecarContainers`) is NOT_OBSERVED: the upstream chart
  was not readable in this run. The ADR records a fallback (a separate
  `temporal-jwks` Deployment in the `temporal` namespace, serving the same
  file over HTTPS with the same pod-local CA). Node F/G implementers must
  confirm which form the chart allows.
- Whether Go's `SSL_CERT_FILE` override is honoured by the `temporalio/server:1.31.0`
  binary as built (static build, `crypto/x509` on Linux) is expected but
  NOT_OBSERVED; it is a canary step (C1) and a stop condition.
- Whether `keySourceURIs` and `SSL_CERT_FILE` affect any other outbound TLS of
  the frontend (none is configured today: persistence is plaintext
  `connectProtocol: tcp` to shared-pg in `bootstrap/templates/data/temporal.yaml`)
  must be re-checked when node E adds TLS.
- The maximum `rotation_period` Vault accepts for a named key, and whether a
  named key can be set to never rotate automatically, depend on the deployed
  Vault server version (NOT_OBSERVED, `vault status`). The ADR requires a
  rotation_period longer than the planned manual rotation cadence plus an
  alert (node B) on JWKS/Vault `kid` mismatch.
- Acceptable emergency-revocation latency (PR merge + Argo CD sync +
  `refreshInterval`) needs a number from the approver; the ADR proposes
  `refreshInterval: 1m` and a target of <= 15 minutes.
