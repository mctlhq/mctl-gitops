# Tasks: issue-2506-spike-temporal-evaluate-zitadel-vs-vault

- [ ] 1. Collect pinned upstream evidence: ZITADEL v4.19.2 (Actions v2
  `preaccesstoken` claim append, web-key algorithms and rotation,
  client-credentials and private-key-JWT grants, token exchange, role claim
  format), Vault identity OIDC (named key, `allowed_client_ids`,
  `rotation_period`, `verification_ttl`, role template, `.well-known/keys`
  scope), ESO `VaultDynamicSecret`. Reuse #2469 citations for Temporal
  v1.31.0. — DoD: each fact has a tag/commit URL and line, or is labelled
  `NOT_OBSERVED` with the command that would observe it.
- [ ] 2. Inventory GitOps desired state for ZITADEL and Vault (depends on 1):
  projects, `zitadel_machine_user.customer_lifecycle`, token types,
  `has_project_check`, Actions executions and their toggle, ZITADEL and Vault
  ingress, `vault-netpol.yaml`, absence of Temporal egress policy. — DoD:
  table with file:line per row, desired-state vs live column, no live claim
  without operator output.
- [ ] 3. Answer RQ1-RQ4 (depends on 1, 2). — DoD: each answer cites evidence
  rows; every unresolved part is listed as a gap.
- [ ] 4. Write the A/B/C/D decision matrix and threat model (depends on 3). —
  DoD: every criterion in requirements.md has a cell per option; the threat
  model covers the seven threats listed in requirements.md and the
  Temporal-vs-mctl-api authorization boundary.
- [ ] 5. Write the role/claim mapping (depends on 4). — DoD: each ADR 0003
  identity maps to `permissions`, issuer-side binding object and
  ServiceAccount; no row uses `worker` alone; no provider row holds a
  `mctl-agents:*` or `mctl-assistants:*` permission.
- [ ] 6. State the verdict and its change conditions (depends on 4). — DoD:
  exactly one outcome label; preconditions that are `NOT_OBSERVED` are named;
  the fallback to `BLOCKED_NEEDS_AUTHORIZER_OR_TRUST_PATH` is explicit; the
  text says no enablement is licensed while #2469 is `BLOCKED`.
- [ ] 7. Write the issuer-specific negative-test contract, migration/rollback
  and operator cost (depends on 5). — DoD: each step maps to T1-T11 and to an
  existing canary S-step or is marked new; stop conditions listed.
- [ ] 8. Write the proposed ADR 0003 amendment text and the #2469 handoff
  (depends on 6). — DoD: amendment marked "proposed, not adopted"; handoff
  names DAG nodes A, C, D, F, I only; no new DAG.
- [ ] 9. Assemble `docs/spikes/2506-temporal-jwt-issuer.md` and optionally
  add its link to the "Companion documents" line of
  `docs/runbooks/temporal-client-auth.md` (depends on 1-8). — DoD: the diff
  touches only those two files; `docs/adr/` untouched; PR opened for
  independent DevLoop review and human decision, not merged automatically.

## Tests

Document checks (run on the PR):

- [ ] D1. `git diff --name-only origin/main` lists only
  `docs/spikes/2506-temporal-jwt-issuer.md` and, at most,
  `docs/runbooks/temporal-client-auth.md`.
- [ ] D2. Every evidence row has a status label from the vocabulary and a
  source; `grep -c NOT_OBSERVED` rows each name the observing command.
- [ ] D3. `grep -n "eyJ"` over the new document returns nothing (no token
  material).
- [ ] D4. The document contains exactly one verdict label line.

Issuer-specific canary contract to be written into the document (for #2469
node F; not executed by this issue):

- [ ] T1. No token on `canary-control` StartWorkflowExecution: PermissionDenied (S1).
- [ ] T2a. Token from the Temporal Vault key with wrong `aud` and with no `aud`: denied (S6).
- [ ] T2b. Valid-signature token from a second Vault named key in the same
  Vault namespace: must be denied; if allowed, JWKS exclusivity is a stop
  condition (new).
- [ ] T2c. A ZITADEL human access token (JWT type) for any project, replayed
  against the canary frontend: denied, because the ZITADEL JWKS is never a key
  source (new).
- [ ] T2d. Expired, unknown `kid`, forged signature, HS256 and EdDSA tokens:
  denied (S2-S4).
- [ ] T2e. Wrong `iss` with valid key: record result; expected allowed (S5).
- [ ] T3/T4. `canary-kuptsi` and `canary-provider-a` identities against
  `canary-control`, including start, signal, query, list, terminate and poll
  of `mctl-dev-loop`: denied (S9, S10).
- [ ] T5. `canary-control` against `canary-kuptsi`: denied (S11).
- [ ] T6. Non-admin identities on namespace and cluster APIs: denied (S12).
- [ ] T7. Web identity, if enabled: writes denied (S13).
- [ ] T8. Provider entity with edited metadata by a non-admin path: cannot
  gain a control permission; the token's `permissions` equal the
  admin-written entity metadata only (new).
- [ ] T9a. Disable the client's Vault role and wait one TTL: new tokens fail,
  old token rejected after `exp` (S14).
- [ ] T9b. Rotate the Temporal named key with `verification_ttl` set: no
  validation gap; rotating it does not affect any ZITADEL or other Vault
  consumer (new).
- [ ] T9c. JWKS unreachable during refresh: old keys kept; frontend restart
  during the outage: all clients denied; record time to recovery (new).
- [ ] T9d. ESO stopped: workers keep running until token expiry and recover
  after ESO returns (S14).
- [ ] T10. Synthetic long workflows survive every phase (S15).
- [ ] T11. No `eyJ` in logs, Loki, or histories (S16).

Stop conditions added by this spike: T2b or T2c allowed; T8 permission
self-assertion possible; T9b affects a non-Temporal consumer; T9c recovery not
bounded.

## Rollback

Documentation only. Revert the PR (or close it unmerged). No runtime state,
credential, ADR status or release blocker changes, so there is nothing else to
restore.
