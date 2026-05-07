# platform-temporal: Document Temporal as a platform service

## Context
Commit `c2066ae` in mctl-gitops (2026-05-06) introduced Temporal workflow
orchestration as a first-class platform service on the mctl cluster:

- **Temporal server** (chart 1.2.0, server 1.31.0) deployed with Postgres advanced
  visibility on the shared PostgreSQL cluster.
- **Temporal Web UI** available at `temporal.mctl.ai`, protected by Backstage OIDC
  (same authentication as `app.mctl.ai`).
- **Shared PostgreSQL** extended with a `temporal` role and `temporal` /
  `temporal_visibility` databases.
- **Credentials** sourced from Vault (`platform/temporal/database`) via ExternalSecret.
- **Tenant namespace registration** done via a PostSync Job (not yet self-serve);
  new tenants must extend the registration script in mctl-gitops.
- First tenant onboarded: `labs/kuptsi-app` (same day, `c878333`).

This means developers building Temporal-based services on any mctl tenant can point
their workers at the shared cluster and use the Web UI at `temporal.mctl.ai` for
workflow inspection. No `docs.mctl.ai` page currently covers Temporal.

**version-status: in production** — deployed 2026-05-06 (confirmed by kuptsi-app
Temporal worker running same day).

## User stories
- AS a **developer** building a Temporal-based service I WANT to know the Temporal
  server URL and how to authenticate SO THAT I can connect my Temporal worker to the
  shared cluster.
- AS a **tenant owner** I WANT to understand how to get a Temporal namespace registered
  for my tenant SO THAT I can start scheduling Temporal workflows without provisioning
  my own Temporal server.
- AS a **platform admin** I WANT a reference for the Temporal Web UI URL, OIDC
  configuration, and how to add new tenant namespaces SO THAT I can onboard tenants
  and troubleshoot Temporal-related issues.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/platform/temporal.md` THE SYSTEM SHALL list the Temporal
  Web UI URL (`temporal.mctl.ai`) and describe the OIDC authentication requirement.
- WHEN a reader wants to connect a Temporal worker to the shared cluster THE SYSTEM
  SHALL provide the Temporal server address and any required configuration.
- WHEN a reader wants to register a new tenant namespace THE SYSTEM SHALL describe
  the current manual process (extend the PostSync Job registration script in
  mctl-gitops) and note that self-serve onboarding is not yet available.
- WHEN a reader needs to understand what Temporal is THE SYSTEM SHALL provide a
  one-paragraph description or an external link to the Temporal documentation.
- IF a reader wants to know which database backend Temporal uses THE SYSTEM SHALL
  state that Temporal uses the shared PostgreSQL cluster with advanced visibility.
- WHILE tenant namespace registration is manual THE SYSTEM SHALL say so explicitly
  and direct platform admins to the mctl-gitops PostSync Job.

## Out of scope
- Temporal SDK documentation (language-specific; link to upstream docs instead).
- Detailed PostgreSQL schema or Vault secret layout (internal implementation details).
- Temporal worker deployment templates (covered by `docs/guides/services.md` and
  standard base-service Helm chart).
- Self-serve namespace registration (not yet implemented; document when it ships).
