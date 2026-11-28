# Tasks: rbac-location-update-permission

- [ ] 1. Locate and read the current permission policy for location permissions — DoD: summary of current rules recorded in the PR.
- [ ] 2. Update the policy so create/delete use the same allowed groups (depends on 1) — DoD: explicit rules, default deny.
- [ ] 3. Add unit tests for the policy (depends on 2) — DoD: tests cover allowed group, denied group, and missing rule.
- [ ] 4. Validate in staging on 1.57.x that catalog-import update works (depends on 2) — DoD: update by an authorized user succeeds; unauthorized is denied.

## Tests
- [ ] T1. Policy unit tests for create/update/delete.
- [ ] T2. e2e: location update as admin vs viewer.

## Rollback
Revert the policy change; behaviour on pre-1.57 versions is unchanged.
