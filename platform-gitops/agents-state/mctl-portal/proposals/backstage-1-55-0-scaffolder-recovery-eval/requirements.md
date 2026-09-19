# Staged evaluation of Backstage v1.55.0 (scaffolder task recovery + backend perf)

## Context
Backstage v1.55.0 introduces scaffolder task recovery and backend
performance improvements, alongside breaking changes to deprecated catalog
APIs and, per its release notes, an Elasticsearch 8 upgrade requirement.
Scaffolder is mctl-portal's tenant/service onboarding path into
mctl-gitops and Argo Workflows, and today a stuck or failed scaffolder task
has no documented recovery story — so the task-recovery capability is
directly relevant to a known operational gap.

However, `context/architecture.md` does not list Elasticsearch as
mctl-portal's search backend, ADR 0001 explicitly cautions against adopting
a Backstage major/minor bump immediately on release day (community-plugins
compatibility usually lags by 1-2 weeks), and this release ships breaking
catalog-API changes. This is a genuinely new release, distinct from the
already-completed `backstage-1-54-7-oauth-normalization` proposal (a
different, auth-specific patch release). Per the ADR and architecture
guardrails, this proposal is scoped as a **staged evaluation only** — it
does not authorize a production bump. No `labs`-tenant impact
(mctl-portal runs only in `admins`).

## User stories
- AS a platform operator I WANT a documented, gated evaluation of Backstage
  v1.55.0 SO THAT I know whether scaffolder task recovery and backend perf
  improvements are safe and worthwhile to adopt, without rushing a
  production upgrade.
- AS a tenant onboarding a new service I WANT scaffolder tasks to be
  recoverable after a transient failure SO THAT I do not have to restart
  onboarding from scratch.
- AS a platform engineer I WANT confirmation that no forced Elasticsearch 8
  dependency applies to our search setup, and that our custom plugins
  (kubernetes, observability, scaffolder, techdocs) remain compatible,
  SO THAT any eventual adoption does not silently break search or a custom
  plugin.

## Acceptance criteria (EARS)
- WHEN this evaluation is scheduled, THE SYSTEM SHALL wait at least one
  week after the v1.55.0 release date before beginning compatibility
  validation, per ADR 0001 and `context/architecture.md` guidance.
- WHEN the compatibility check is performed, THE SYSTEM SHALL determine and
  document whether v1.55.0's Elasticsearch 8 requirement is forced for
  mctl-portal's current search configuration or is conditional/optional.
- WHEN each custom plugin (kubernetes, observability, scaffolder, techdocs)
  is built and smoke-tested against v1.55.0 in a lower environment, THE
  SYSTEM SHALL record a pass/fail result for each plugin before any
  further decision is made.
- IF the Elasticsearch 8 requirement is confirmed to be forced and
  incompatible with mctl-portal's current search setup, THEN THE SYSTEM
  SHALL reject production adoption of v1.55.0 and document the blocker for
  a future re-evaluation.
- IF any custom plugin fails to build or fails smoke tests against v1.55.0,
  THEN THE SYSTEM SHALL block promotion to production and report the
  specific failure.
- IF all compatibility checks pass, THEN THE SYSTEM SHALL produce a
  follow-on adoption proposal (separate from this evaluation) recommending
  the production bump; this proposal itself SHALL NOT trigger a production
  deployment.
- WHILE the evaluation is in progress, THE SYSTEM SHALL keep the
  currently-deployed 2.6.3 revision serving production traffic in `admins`
  unchanged.

## Out of scope
- Actually deploying v1.55.0 to production (a separate, follow-on proposal
  if this evaluation passes).
- Migrating mctl-portal's search backend to Elasticsearch 8 (only assessed
  here, not implemented).
- Any change already covered by `backstage-1-54-7-oauth-normalization`
  (a different, already-scoped patch release).
- Resolving the breaking changes to deprecated catalog APIs beyond
  identifying and documenting their impact during evaluation.
