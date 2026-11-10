# Tasks: issue-2568-security-glovo-canary-choose-and-prove-t

- [ ] 1. Create `docs/runbooks/glovo-p1-temporal-isolation.md` with a header
  and a verdict line `VERDICT: ROUTE_A_SELECTED; P1: BLOCKED`. The header
  states the issue (#2568), the parent (#2457), the pinned gitops commit and
  the date. — DoD:
  - the file exists;
  - the header and verdict are present;
  - it states that merging grants no approval.
- [ ] 2. Write the inventory section (depends on 1). — DoD:
  - columns are item / desired (Git) / live / label / source;
  - rows cover:
    - frontend TLS;
    - authorizer and claim mapper;
    - dynamic config;
    - Temporal namespaces;
    - the 7 clients;
    - release and rollback mechanics from `bootstrap/templates/data/temporal.yaml`;
    - node capacity from `infrastructure/k3s-preview/kube.tf`, with live
      allocatable NOT_OBSERVED;
    - the Glovo provider (no credential, obsolete staged netpol);
  - every live row cites the dated 2026-11-09 evidence in
    `docs/runbooks/temporal-client-auth.md`, or is NOT_OBSERVED.
- [ ] 3. Write the A versus B decision matrix and the route rationale
  (depends on 2). — DoD:
  - the matrix has the six criteria from design.md;
  - it states why B is not selected;
  - it lists the triggers for re-evaluating B;
  - it gives the Temporal resource requests read from `temporal.yaml`.
- [ ] 4. Write the version-pinned policy section (depends on 3). — DoD:
  - pins: server 1.31.0, chart 1.2.0, Go SDK 1.50.0, Python SDK 1.34.0;
  - kuptsi SDK is marked BLOCKED_NO_ACCESS;
  - the issuer, `aud: temporal-frontend` and JWKS (unresolved gate, node C,
    #2540) are stated;
  - the caller-to-permission table names each caller;
  - the provider has no token and is not admitted;
  - role-to-RPC behaviour is referenced to
    `docs/runbooks/temporal-authz-role-matrix.md`;
  - each default-deny case maps to a canary step S1-S17;
  - the S5 issuer gap is flagged as needing security acceptance.
- [ ] 5. Write the negative canary evidence section (depends on 4). — DoD:
  - it references `docs/runbooks/temporal-auth-canary.md` without restating
    it;
  - it gives the Glovo mapping of synthetic namespaces;
  - evidence slots are empty and dated (the canary is run twice);
  - it states the pre-production continuity checks: DevLoop and kuptsi SLO
    and history, and the mctl-api#934 release hold, which is NOT_OBSERVED.
- [ ] 6. Write the dependency chain and the P1 security approval request
  (depends on 5). — DoD:
  - the node A-I table has owner, issue or PR, missing proof and stop
    condition;
  - the CROSSWALK §5 Glovo gates are listed;
  - the closing request is addressed to the platform security admin role;
  - it lists every missing proof;
  - unknown is stated as blocking.
- [ ] 7. Cross-link the existing docs (depends on 1). — DoD:
  - `docs/runbooks/glovo-m1.md` P1 checklist gains one item pointing to the
    new record;
  - `deploy/staged/glovo-m1/CROSSWALK.md` §4 gains one route-decision line;
  - `deploy/staged/glovo-m1/README.md` lists #2568;
  - `deploy/staged/glovo-m1/gate.yaml` is unchanged.
- [ ] 8. Validate and open the PR (depends on 1-7). — DoD:
  - `scripts/validate-glovo-m1-staging.py --selftest` and
    `scripts/validate-glovo-m1-staging.py` pass locally;
  - `git diff --stat` shows only files under `docs/` and
    `deploy/staged/glovo-m1/*.md`;
  - the PR body links #2568, #2457 and #2469.

## Tests

- [ ] T1. Run `scripts/validate-glovo-m1-staging.py --selftest` and then
  `scripts/validate-glovo-m1-staging.py`. Both exit 0.
- [ ] T2. Run `git diff --name-only origin/main` and check that it lists no
  path under `platform-gitops/` and no `.yaml` file at all. In
  particular `gate.yaml`, `temporal.yaml`, `networkpolicy.yaml` and
  `tenant-namespace-job.yaml` must be untouched.
- [ ] T3. Run `grep -n 'VERDICT: ROUTE_A_SELECTED; P1: BLOCKED'
  docs/runbooks/glovo-p1-temporal-isolation.md`. It returns exactly one line.
- [ ] T4. Grep the new record for `VERIFIED_LIVE`. Every row that matches
  carries a date and an operator source. No row claims live Temporal
  namespaces, connected clients, node allocatable or the mctl-api#934 status
  as observed.
- [ ] T5. Check the new record for the default-deny cases (missing,
  expired, forged and wrong-aud tokens, cross-namespace start, signal,
  query, list and terminate, and provider-to-control/DevLoop). Each one maps
  to an S-step in `temporal-auth-canary.md` that exists.
- [ ] T6. The `glovo-m1` and markdown checks in `validate-manifests.yml` are
  green on the PR.

## Rollback

The change is documentation only, so rollback is a single `git revert` of
the PR. No cluster state, secret, namespace or Temporal configuration is
created, so nothing needs to be pruned. P1 stays BLOCKED either way, because
`deploy/staged/glovo-m1/gate.yaml` is not modified.
