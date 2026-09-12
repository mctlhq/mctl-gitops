# Fix null `service` field in mctl-portal ArgoCD status

## Context
The ArgoCD status response for mctl-portal in tenant `admins` has reported
`service=null` for at least two consecutive daily cycles (2026-09-05 and 2026-09-12),
despite the Application being Healthy/Synced throughout. This points to a small
metadata/labeling gap in the ArgoCD Application manifest or its associated
labels/annotations, rather than a functional problem with the service itself. Left
unfixed, this risks breaking future mctl tooling or automation that keys off the
`service` field (e.g., service-to-tenant mapping, dashboards, or cross-referencing
with the log-pipeline investigation in `portal-log-pipeline-gap`, which may share the
same underlying labeling root cause).

This is a cheap, low-risk hygiene fix scoped entirely to the `admins` tenant, with no
interaction with or impact on the `labs` tenant.

## User stories
- AS a platform tooling maintainer I WANT the ArgoCD status `service` field for
  mctl-portal to be populated correctly SO THAT automation and dashboards that key
  off that field do not silently break or misattribute this service.
- AS an on-call engineer I WANT consistent service metadata across ArgoCD and logging
  tooling SO THAT I can correlate status, logs, and metrics for mctl-portal without
  manual cross-referencing.

## Acceptance criteria (EARS)
- WHEN the ArgoCD Application manifest for mctl-portal is queried for status THE
  SYSTEM SHALL return a non-null `service` field with the correct service name
  (`mctl-portal`).
- WHEN the fix is deployed THE SYSTEM SHALL continue to report Healthy/Synced status
  for mctl-portal with no other status fields regressed or unset.
- IF the root cause of the null `service` field is the same label/annotation gap
  implicated in `portal-log-pipeline-gap` THEN THE SYSTEM SHALL have that shared root
  cause documented and cross-referenced in both proposals rather than fixed twice
  independently.
- WHILE the manifest change is validated THE SYSTEM SHALL NOT affect any other
  service's ArgoCD Application in `admins` or `labs`.

## Out of scope
- Broader ArgoCD Application manifest restructuring or template changes beyond the
  specific label/field causing `service=null`.
- The log-pipeline investigation itself (tracked separately in
  `portal-log-pipeline-gap`), even though the two may share a root cause.
- Any change to `labs`-tenant manifests or tooling.
