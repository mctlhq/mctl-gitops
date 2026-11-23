# Tasks: automated-dependency-update-prs

- [ ] 1. Add dependabot.yml for gomod with weekly grouped minor/patch updates — DoD: first grouped PR is opened.
- [ ] 2. Configure major updates as separate labelled PRs, open-PR limit 5 (depends on 1) — DoD: config reviewed.
- [ ] 3. Document the merge policy in the repo README (depends on 1) — DoD: README section merged.

## Tests
- [ ] T1. Trigger a Dependabot run and confirm grouping and labels.
- [ ] T2. Confirm a failing PR is not merged.

## Rollback
Delete `.github/dependabot.yml`.
