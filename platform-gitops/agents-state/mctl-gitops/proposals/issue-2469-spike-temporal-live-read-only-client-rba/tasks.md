# Tasks: issue-2469-spike-temporal-live-read-only-client-rba

- [ ] 1. Rewrite the "Live evidence" table in `docs/runbooks/temporal-client-auth.md`
  with the columns Item | Source | Version | Observed | Status, using the
  status values `VERIFIED_SOURCE`, `VERIFIED_LIVE`, `BLOCKED_NO_ACCESS` and
  `BLOCKED_JWT_SEMANTICS`. Fill the GitOps-sourced rows at a pinned commit:
  chart 1.2.0, server 1.31.0, no `global.tls`/`global.authorization`,
  `allow-temporal-ingress` peers, client tags (mctl-api 4.154.0, mctl-agents
  1.117.0, kuptsi-app 0.2.27, temporalio/ui 2.49.1), and Vault `tls_disable = 1`.
  Each live-only row keeps its read-only command. — DoD: every row has a
  source and a date; no row says "absent" or "not configured" without a
  source.
- [ ] 2. Check chart 1.2.0 capability (`server.config.tls`, `internalFrontend`,
  `global.authorization` keys) in `temporalio/helm-charts` at the 1.2.0 tag,
  and record the URL and lines in the inventory (depends on 1). — DoD: the row
  is `VERIFIED_SOURCE`, or it is `BLOCKED_NO_ACCESS` with the reason.
- [ ] 3. Record the client Temporal SDK versions from the lock files at the
  deployed tags in mctl-api, mctl-agents and kuptsi-app (depends on 1). — DoD:
  each SDK row has a repo@tag file link, or it is `BLOCKED_NO_ACCESS`.
- [ ] 4. Create `docs/runbooks/temporal-authz-role-matrix.md`. It holds the
  RPC x role matrix from `temporalio/temporal` `v1.31.0` source with
  file/line citations, explicit `temporal-system` scope semantics, what
  `worker` grants, and a "no task-queue dimension" statement. It also
  re-checks the ADR 0003 candidate permission map against the matrix. — DoD:
  every RPC listed in requirements.md has a cell for each role, each cell is
  allow, deny or "unclear — canary", and every cell is cited.
- [ ] 5. Add the JWT semantics section to the matrix doc (depends on 4). It
  covers the permissions claim, `iss` validation, non-empty audience
  validation and its config key, key-source URI schemes and refresh, Vault
  identity OIDC role/key template, TTL and `verification_ttl`, ESO
  `VaultDynamicSecret` compatibility, and the plaintext in-cluster JWKS
  finding. — DoD: each point is `VERIFIED_SOURCE` with a citation or
  `BLOCKED_JWT_SEMANTICS` with a minimal canary repro.
- [ ] 6. Create `docs/runbooks/temporal-auth-canary.md` (depends on 4, 5). It
  covers isolation (separate release, Kubernetes namespace, database and
  NetworkPolicy; synthetic Temporal namespaces and identities; canary-only
  key; no production credential or endpoint), the version pin, the T1-T11
  steps with their expected gRPC codes, the entry/exit gates, the rollback
  rehearsal, SLO continuity measurement and the stop conditions. — DoD: every
  ADR test T1-T11 maps to at least one step, and nothing in the doc requires
  touching the production release.
- [ ] 7. Replace "Downstream issue breakdown" in the runbook with DAG nodes A-J
  (depends on 4-6). Each node has repo, owner, mandatory review, approval
  gate, rollback, sequencing and stop condition, and there is a text/Mermaid
  DAG. Document the temporal-web `temporal-system:read` implication and defer
  it pending admin-only risk acceptance. — DoD: every node is independently
  approvable, and none is marked approved.
- [ ] 8. Add the recommendation block at the top of the runbook (depends on
  1-7): `GO_TO_SEPARATE_IMPLEMENTATION_PROPOSAL` or `BLOCKED`, the outcome
  labels, and the unresolved unknowns. Add a one-line pointer to the new docs
  in ADR 0003 "Open items" and leave its status `Proposed`. — DoD: the
  verdict follows from the table statuses, and the unknowns are listed
  explicitly.

## Tests

- [ ] T1. `git diff --name-only origin/main` lists only files under `docs/`.
- [ ] T2. `grep -n "http://" docs/runbooks/temporal-authz-role-matrix.md docs/runbooks/temporal-auth-canary.md`:
  every hit is labelled as rejected or as an existing plaintext fact, never as
  a proposed JWKS URI.
- [ ] T3. Every row of the inventory table has a non-empty Source and
  Observed cell (manual table check).
- [ ] T4. The text does not claim queue-level authorization anywhere
  (`grep -in "task.queue"` hits only say it is not enforced).
- [ ] T5. ADR 0003 still reads `**Status:** Proposed`.
- [ ] T6. The repo's Markdown checks in CI (if any) pass, and `validate-manifests.yml`
  is unaffected because no manifest changed.

## Rollback

Revert the docs PR. Nothing is deployed, no credential or namespace is
created, and no runtime state depends on these files.
