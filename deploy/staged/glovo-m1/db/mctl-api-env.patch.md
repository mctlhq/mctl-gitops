# mctl-api env for Glovo (text only, not applied)

Target: `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`
(`env:` next to `AUDIT_DB_URL`, and `envFromOptionalSecrets`). Not touched here.
Today the file sets `AUDIT_DB_URL` as the legacy `mctl-api` role on database
`mctl-api`, and the work-items store falls back to it. `bridgeStoreDSN` reads
only `COMMERCE_DB_URL`, which is unset, so the bridge is off. That legacy
work-items DSN is PRESERVED during P0 and P1: nothing below replaces it.

Contract source: mctl-api `081bd6b7` (`cmd/api/glovo_team_grant.go`,
`cmd/api/glovo_bridge.go`, `internal/glovo/receipt/ready.go`) and the #1004
amendment (mctl-gitops#2579, design sections 1, 7-10).

    envFromOptionalSecrets:
      - mctl-api-glovo-runtime-db        # optional: the pod boots without it
      - mctl-api-workitems-db            # optional; consumed only once WORK_ITEMS_DB_URL is switched

    env:
      GLOVO_DB_URL: "postgresql://$(GLOVO_DB_USER):$(GLOVO_DB_PASSWORD)@shared-pg-rw.platform-db.svc:5432/mctl-api?sslmode=require"
      # Required by configureGlovoTeamGrants whenever GLOVO_ENABLED=true:
      GLOVO_DB_RUNTIME_ROLE: glovo_runtime
      GLOVO_DB_MIGRATION_ROLE: glovo_migrator
      # D1: dedicated least-privilege role, explicit URL, database mctl-api.
      # NOT applied during P0/P1; the legacy DSN above keeps serving work items.
      WORK_ITEMS_DB_URL: "postgresql://$(WORKITEMS_DB_USER):$(WORKITEMS_DB_PASSWORD)@shared-pg-rw.platform-db.svc:5432/mctl-api?sslmode=require"
      # COMMERCE_DB_URL: UNVERIFIED, deliberately absent (see below).

All three roles share one physical database, `mctl-api` on `shared-pg` (D1).
`receipt.Ready` requires `GLOVO_DB_URL` and `WORK_ITEMS_DB_URL` to be set
explicitly (no `AUDIT_DB_URL` fallback), so the switch to `mctl_api_workitems`
must precede any P2 activation; it is its own authorized action, after the
operator step and the read-only grants verification of design section 8.

## UNVERIFIED, activation blockers (do not guess)

- `COMMERCE_DB_URL` role. #1004 D1 does not decide it. Setting it is what would
  switch the command bridge from 503 to enabled if `MCTL_BRIDGE_ENABLED` is ever
  on. Evidence required (read-only): which role owns the bridge/commerce tables
  and who the grantees are (`pg_class.relowner`, `aclexplode(relacl)` on the
  `bridge_*` relations), and whether any such table exists at all.
- `DB_POOL_MAX_CONNS` and the `connectionLimit` sizing (see roles.patch.md).
  mctl-api sizes one pool per distinct `*_DB_URL` per replica (default 8), so
  with `GLOVO_DB_URL` and `WORK_ITEMS_DB_URL` distinct the earlier "8 x 2
  replicas" comment no longer holds. Evidence required: deployed replica count
  and surge, and the `pgshared: pools` startup log.

## Flags that stay off (all absent today, none is added)

`GLOVO_ENABLED`, `GLOVO_JOIN_ENABLED`, `MCTL_GLOVO_CONTROL_ENABLED`,
`MCTL_BRIDGE_ENABLED`. `GLOVO_TEAM_FALLBACK` does not exist any more and is
not added. The `GLOVO_DB_*_ROLE` names are inert while `GLOVO_ENABLED` is unset.

Write-fence terminology:
- P0/P1: `glovoWriteFenceHoldLifted=false`, `SetFence` NOT called, feature flags
  OFF, zero fake effects.
- P2: separately authorized activation of a real, ready, fail-closed
  `receipt.NewFence` that permits only owner-approved single-use fake `aar_`
  writes (negative tests, revocation, kill switch).
- No real Glovo provider action at any phase.
