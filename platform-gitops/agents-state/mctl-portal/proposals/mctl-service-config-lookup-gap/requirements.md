# Investigate and fix mctl_get_service_config lookup gap for admins/mctl-portal

## Context
This cycle, `mctl_get_service_config` was called for `admins/mctl-portal`
for the first time and returned an error: "service not found:
admins/mctl-portal". This is a harder failure than the previously-known
issue tracked in `proposals/argocd-service-field-gap/`, where the ArgoCD
status call succeeds but returns a null `service` field. Both symptoms
point at platform tooling being unable to fully resolve/introspect this
service's identity, which risks silently breaking automation that depends
on service lookup — including this very agent pipeline (researcher/analyst/
spec-writer runs read `mctl_get_service_config` as an input).

It is not yet established whether this "not found" error and the ArgoCD
`service=null` field share the same underlying root cause (e.g. a missing
or malformed service-registration label/annotation on the ArgoCD
Application, or a config-registry entry that was never created) or are
genuinely independent gaps (e.g. a separate config-registry index that was
never populated for this service, unrelated to the ArgoCD Application
labels). This proposal does not assume either answer; it starts with an
investigation task and scopes the fix conditionally.

## User stories
- AS a platform tooling maintainer I WANT to know whether the
  `mctl_get_service_config` "not found" error and the ArgoCD `service=null`
  field share a root cause SO THAT I fix the underlying gap once instead of
  patching two symptoms independently.
- AS an on-call engineer or agent pipeline consumer I WANT
  `mctl_get_service_config` to resolve `admins/mctl-portal` successfully
  SO THAT automation and dashboards that depend on service config lookup do
  not silently fail.

## Acceptance criteria (EARS)
- WHEN this proposal is picked up, THE SYSTEM SHALL first investigate
  whether the `mctl_get_service_config` "not found" error and the
  `argocd-service-field-gap` null `service` field originate from the same
  underlying registration/labeling gap, and SHALL document the finding
  before any fix is implemented.
- IF the investigation determines the two issues share the same root cause,
  THEN THE SYSTEM SHALL fold this proposal into `argocd-service-field-gap`
  as an expanded acceptance criterion there (this proposal SHALL be marked
  superseded/merged rather than implemented separately) and SHALL NOT
  implement the fix twice.
- IF the investigation determines the two issues are genuinely independent,
  THEN THE SYSTEM SHALL scope and implement an independent fix so that
  `mctl_get_service_config` for `admins/mctl-portal` returns a valid,
  populated service-config object.
- WHEN `mctl_get_service_config` is called for `admins/mctl-portal` after
  the fix, THE SYSTEM SHALL return a successful result containing at least
  the service name, tenant, and current version, instead of a "service not
  found" error.
- WHILE the fix is being validated, THE SYSTEM SHALL NOT affect
  `mctl_get_service_config` lookups for any other service in `admins` or
  `labs`.

## Out of scope
- The ArgoCD `service=null` field fix itself, if the investigation finds
  the two are independent (that remains fully scoped in
  `proposals/argocd-service-field-gap/`).
- The empty service-logs investigation (tracked separately in
  `proposals/portal-log-pipeline-gap/`), even though it may eventually
  prove related.
- Any change to `labs`-tenant service registration or config.
