# Design: argo-workflows-4-1-6-go-dsa-qs-verify

## Current state
Argo Workflows runs all pipelines (`context/architecture.md`); a known archive bug exists in v3.7.10.

## Proposed solution
Read-only check of the deployed version in the gitops repo (values/manifests). If already >= fixed version, close the proposal. Otherwise bump a patch within the current line and coordinate with argo-workflows-cve-bundle-upgrade.

## Alternatives
- Blind bump to 4.1.6: may be a major jump, rejected.
- Ignore: leaves a High panic CVE open.

## Platform impact
- Migrations: none for patch bumps.
- Compatibility: verify archive schema on 4.x before rollout.
- Resource impact: none steady-state; negligible for `labs`.
- Risks: workflow disruption; mitigated by rolling out during low cron activity and git revert.
