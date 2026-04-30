# Upgrade kubernetes/client-go from v0.32 to v0.36

## Context

mctl-api uses `kubernetes/client-go` v0.32 to query the Kubernetes API for
pods, services, cronjobs, and workflow status. As of 2026-04-22, the current
stable release is v0.36.0, which corresponds to Kubernetes 1.36. mctl-api is
therefore four minor versions behind the latest client library, representing
roughly one year of accumulated changes across API types, informer mechanics,
and client-side rate-limiting behaviour.

No direct CVEs affecting client-go v0.32 have been disclosed today. The
motivation for this upgrade is forward risk management: each minor version of
Kubernetes deprecates and eventually removes API group versions. Clusters
running Kubernetes 1.33–1.36 may have already removed APIs that v0.32 typed
clients reference. Running a 4-version-drifted client library against a cluster
that has progressed past 1.32 creates a growing surface for undetected API
incompatibilities, serialization errors, and watch-cache mismatches. The cost
of upgrading also compounds the longer the drift is allowed to grow. Addressing
the drift now, while there are no breaking changes in the target range, is lower
risk than deferring until a forced upgrade coincides with a cluster upgrade or
an active security event.

## User stories

- AS a platform engineer I WANT mctl-api to use client-go v0.36 SO THAT the
  Kubernetes API client stays aligned with the cluster version and API
  deprecations do not cause silent failures.
- AS a developer I WANT the upgrade validated by the existing test suite SO THAT
  I can merge it without a manual regression cycle on every Kubernetes resource
  type mctl-api reads.
- AS an on-call engineer I WANT the deployment to use the standard rolling
  update with PodDisruptionBudget SO THAT I can roll back immediately if
  Kubernetes API calls start returning unexpected errors.

## Acceptance criteria (EARS)

- WHEN `go mod tidy` is run after bumping `k8s.io/client-go` to `v0.36.0`,
  THE SYSTEM SHALL compile without errors and all associated `k8s.io/*`
  transitive dependencies SHALL be updated to their v0.36-compatible versions.
- WHEN the CI pipeline runs against the upgraded codebase, THE SYSTEM SHALL
  pass all existing unit, integration, and race-detector tests without
  modification to test logic.
- WHEN mctl-api starts after the upgrade, THE SYSTEM SHALL successfully
  list pods, services, cronjobs, and workflow custom resources from the
  Kubernetes API within the existing SLO thresholds.
- WHEN a Kubernetes API call is made to a v0.36-compatible cluster, THE
  SYSTEM SHALL use only API group versions that are present in Kubernetes 1.36
  (no references to removed API versions).
- WHILE the rolling update is in progress, THE SYSTEM SHALL keep at least one
  healthy replica serving traffic (PodDisruptionBudget enforced).
- IF the new image fails its liveness probe within the configured
  `failureThreshold`, THEN THE SYSTEM SHALL automatically roll back to the
  previous image via the ArgoCD sync policy.
- IF any deprecated API type used in mctl-api's client-go calls is removed
  between v0.32 and v0.36, THEN THE SYSTEM SHALL be updated to use the
  replacement API type before the PR is merged.

## Out of scope

- Upgrading the Kubernetes cluster itself (separate infrastructure concern).
- Migrating to controller-runtime or other higher-level Kubernetes client
  frameworks.
- Adding new Kubernetes API capabilities or new resource watches beyond what
  mctl-api already uses.
- Changes to Vault, ArgoCD, Argo Workflows, or Backstage integrations.
- Any change to `labs` tenant workloads or resource quotas.
- Addressing CVEs not related to this version drift (tracked in separate
  proposals).
