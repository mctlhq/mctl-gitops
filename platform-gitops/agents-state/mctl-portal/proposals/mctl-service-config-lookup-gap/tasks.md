# Tasks: mctl-service-config-lookup-gap

- [ ] 1. Identify the backing store/API that `mctl_get_service_config`
      reads from — DoD: data source documented (e.g. registry name, API
      endpoint, or label/annotation source).
- [ ] 2. Identify the backing store/API that supplies the `service` field
      on `mctl_get_argocd_status` for mctl-portal, per
      `proposals/argocd-service-field-gap/` — DoD: data source documented,
      cross-referenced against task 1's finding.
- [ ] 3. Compare the two data sources and determine shared vs. independent
      root cause (depends on 1, 2) — DoD: explicit written conclusion
      ("shared root cause" or "independent gap") with supporting evidence.
- [ ] 4a. IF shared root cause: add the `mctl_get_service_config` "not
      found" symptom as an expanded acceptance criterion on
      `proposals/argocd-service-field-gap/requirements.md`, and mark this
      proposal's status as superseded/merged (depends on 3) — DoD:
      `argocd-service-field-gap` updated with a cross-reference to this
      proposal; this proposal's status noted as merged, no separate fix
      implemented here.
- [ ] 4b. IF independent gap: register `admins/mctl-portal` in the
      config-registry identified in task 1, populating service name,
      tenant, and current version fields (depends on 3) — DoD:
      `mctl_get_service_config` for `admins/mctl-portal` returns a
      successful, populated result.
- [ ] 5. Add a regression check (periodic call or CI-time check) for
      `mctl_get_service_config` on `admins/mctl-portal` (depends on 4a or
      4b) — DoD: check runs automatically and would flag a future
      "not found" regression.

## Tests
- [ ] T1. Verify `mctl_get_service_config` for `admins/mctl-portal` no
      longer returns "service not found" after either branch (4a merge or
      4b independent fix) is completed.
- [ ] T2. Verify `mctl_get_service_config` for at least one other known-good
      service in `admins` is unaffected (no regression from the fix).
- [ ] T3. Verify `mctl_get_argocd_status` for mctl-portal continues to
      report Healthy/Synced with no fields regressed, regardless of which
      branch (4a/4b) is taken.
- [ ] T4. Regression check (from task 5) fires correctly when manually
      simulated against a "not found" condition in a lower environment.

## Rollback
If branch 4a (merge) is taken, rollback is simply reverting the
cross-reference edit to `argocd-service-field-gap/requirements.md`; no
runtime change was made by this proposal itself. If branch 4b (independent
fix) is taken, rollback is removing/reverting the newly-created
config-registry entry for `admins/mctl-portal`, restoring the prior
"not found" state (a known, non-regressive state, since it is the
pre-existing behavior) while a corrected fix is prepared.
