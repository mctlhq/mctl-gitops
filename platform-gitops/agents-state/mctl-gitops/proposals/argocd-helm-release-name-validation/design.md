# Design: argocd-helm-release-name-validation

## Current state
The `apps` ApplicationSet uses git directory generator `services/*/*` (ADR 0001, context/architecture.md); Application and Helm release names come from tenant and service names.

## Proposed solution
A small shell/Go script (under `cli/mctl/` or a CI step) enumerates `services/*/*`, computes the Application name per the ApplicationSet template, and validates against Helm's rules (lowercase alphanumerics and `-`, start/end alphanumeric, <=53 chars). Run it once before the 3.6.3 bump and then as a PR validation check. Offenders get an explicit `releaseName` in the template/values rather than a directory rename, avoiding resource recreation.

## Alternatives
- Rely on Argo CD errors post-upgrade: discovers failures in production. Rejected.
- Rename directories: triggers recreation of workloads. Rejected.

## Platform impact
- Migrations: only for offenders; setting releaseName on an existing Application may change resource labels, so review a diff.
- Backward compatibility: none for compliant names.
- Resource impact: none (CI only); no change for `labs`.
- Risks: wrong name derivation; mitigate by comparing against live `argocd app list`.
