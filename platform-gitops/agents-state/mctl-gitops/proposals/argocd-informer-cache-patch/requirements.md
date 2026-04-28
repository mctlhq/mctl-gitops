# ArgoCD v3.3.8 — Stale Informer Cache and Core-Mode Sync Fixes

## Context

ArgoCD v3.3.8 was released on 2026-04-21 and contains three targeted fixes:

1. **Stale informer cache in RevisionMetadata handler** — the handler could return outdated
   cluster-state snapshots, causing ArgoCD to make sync decisions based on superseded data.
   On a platform that uses the App-of-Apps pattern, one incorrect sync decision can cascade:
   the bootstrap application re-syncs its children, and stale state propagates across all
   tenant services in `admins` and `labs`.

2. **Core-mode sync failure when `server.secretkey` is absent** — if the secret key is
   not yet mounted at the time of a sync operation, ArgoCD core-mode can fail to complete
   the sync, leaving applications in an indefinite `OutOfSync` state.

3. **Revert of autosync event message format change** — the previous format change was
   breaking consumers that parsed the event message string; the revert restores the
   stable format.

The current deployment pins ArgoCD at a version prior to 3.3.8. Because ArgoCD is the sole
reconciliation engine at `ops.mctl.ai`, leaving these bugs unpatched carries a direct risk
of incorrect or stalled deployments for every tenant service.

## User stories

- AS a platform engineer I WANT ArgoCD to evaluate sync decisions against up-to-date cluster
  state SO THAT tenant services are not rolled back or re-synced based on stale data.
- AS a platform engineer I WANT core-mode syncs to succeed regardless of `server.secretkey`
  mount timing SO THAT services are not stuck in an indefinite OutOfSync state.
- AS an on-call engineer I WANT autosync event messages to have a stable, predictable format
  SO THAT alerting rules and log parsers do not produce false positives.

## Acceptance criteria (EARS)

- WHEN the ArgoCD version in the bootstrap chart is updated to v3.3.8 and the change is
  committed to git, THE SYSTEM SHALL deploy ArgoCD v3.3.8 via the App-of-Apps reconciliation
  loop within one sync cycle.

- WHEN ArgoCD v3.3.8 is running, THE SYSTEM SHALL serve RevisionMetadata from the current
  informer cache, not from a stale snapshot, so that sync decisions reflect live cluster state.

- WHILE a core-mode sync operation is in progress and `server.secretkey` is absent from the
  mounted secrets, THE SYSTEM SHALL complete or cleanly fail the sync rather than entering
  an indefinitely blocked state.

- WHEN an autosync event is emitted by ArgoCD, THE SYSTEM SHALL format the event message
  using the stable pre-regression format, ensuring downstream log parsers and alert rules
  remain valid.

- IF the ArgoCD upgrade is rolled back (pinned back to the previous version via a git
  revert), THEN THE SYSTEM SHALL re-deploy the previous ArgoCD version within one sync
  cycle without manual intervention.

- WHILE the ArgoCD upgrade is in progress (pod restart window), THE SYSTEM SHALL not
  terminate in-flight sync operations for applications that were already in a `Syncing`
  state before the upgrade began (graceful rollout behaviour).

- IF the `labs` tenant is active during the upgrade, THEN THE SYSTEM SHALL NOT increase
  persistent memory allocation for the `labs` namespace, as this is a patch-level bump
  with no new components.

## Out of scope

- Upgrading ArgoCD to a minor or major version (e.g. 3.4.x or 4.x) — this proposal
  covers only the 3.3.x → 3.3.8 patch bump.
- Changes to ApplicationSet templates, sync policies, or App-of-Apps topology.
- Modifications to Vault / ExternalSecrets wiring or any tenant service values.
- Adding monitoring dashboards or alert rules for ArgoCD (a separate proposal).
- Migrating the reconciliation engine away from ArgoCD.
