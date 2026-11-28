# Tasks: argocd-helm-release-name-validation

- [ ] 1. Read the ApplicationSet template and document the name derivation — DoD: rule written in PR.
- [ ] 2. Write the validation script (depends on 1) — DoD: outputs name, length, valid/invalid.
- [ ] 3. Run against the repo and compare with live Application names (depends on 2) — DoD: offender list, possibly empty.
- [ ] 4. Fix offenders with an explicit releaseName (depends on 3) — DoD: diff reviewed, no resource recreation.
- [ ] 5. Add the script as a PR validation step (depends on 2) — DoD: CI fails on an invalid sample.

## Tests
- [ ] T1. A 54-char name is flagged.
- [ ] T2. Uppercase/underscore names are flagged.
- [ ] T3. All current compliant services pass.

## Rollback
Remove the CI step; revert releaseName overrides via git revert.
