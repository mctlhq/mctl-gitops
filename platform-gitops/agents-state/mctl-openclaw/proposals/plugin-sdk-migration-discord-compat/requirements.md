# Plan Plugin SDK migration ahead of before_agent_start deprecation and validate Discord plugin registration

## Context
Upstream openclaw 2026.7.2-beta.7 deprecates the `before_agent_start` hook and
legacy plugin imports; the fork's `extensions/*` packages currently import
`openclaw/plugin-sdk/*` in the pre-deprecation style described in
`context/architecture.md`. All three tenants are already deployed on
`2026.7.11-beta.2` — past the beta that introduced this deprecation — which means
the fork's real exposure window to a forced breaking change is narrower than the
static `context/current-version.md` baseline (2026.3.14) suggests. This gap between
documented and actual deployed version is a known, separately-tracked
documentation issue (see inbox "Dropped" section) but it directly affects how
urgently this migration should be planned.

Compounding this, upstream issue #122655 reports that the official
`@openclaw/discord@latest` plugin itself fails to register on core 2026.8 after the
same SDK export changes. Discord is a channel the fork runs across all three
tenants, so this is not a hypothetical: even without any fork-side code touching
`before_agent_start`, the Discord extension's plugin registration path is at risk
of breaking on the next core bump if it depends on the same deprecated export
surface. This proposal covers planning the SDK migration and validating Discord
plugin registration specifically — not a full migration of every extension.

## User stories
- AS the mctl-openclaw service owner I WANT a concrete migration plan for the
  Plugin SDK ahead of the `before_agent_start` deprecation SO THAT a future core
  version bump does not break fork extensions with no warning.
- AS the mctl-openclaw service owner I WANT the Discord plugin's registration path
  specifically validated against the new SDK export shape SO THAT the Discord
  channel does not go down across all three tenants when the fork eventually moves
  to a core version where the legacy path is fully removed.
- AS the mctl-openclaw service owner I WANT any migration validated in `labs`
  before `admins`/`ovk` SO THAT a botched migration has minimal blast radius, per
  ADR-0001.

## Acceptance criteria (EARS)
- WHEN the migration-planning task runs THE SYSTEM SHALL produce an inventory of
  every `extensions/*` package that imports `openclaw/plugin-sdk/*` and/or
  registers a `before_agent_start` hook.
- WHEN the inventory is complete THE SYSTEM SHALL classify each extension as
  "needs migration" (uses the deprecated hook/import path) or "unaffected", with
  the Discord extension explicitly checked against upstream #122655's described
  export-change symptoms.
- IF the Discord extension is found to use an import/registration path affected by
  the SDK export changes THEN THE SYSTEM SHALL produce a specific remediation plan
  (updated imports/registration calls) before the fork moves to a core version
  where the legacy path is removed.
- WHEN a migration change is implemented for any extension THE SYSTEM SHALL be
  deployed to and validated in `labs` first, per ADR-0001's rollout order, before
  promotion to `admins` then `ovk`.
- WHEN Discord plugin registration is validated post-migration THE SYSTEM SHALL
  confirm the Discord channel registers successfully and can send/receive a test
  message in `labs`.
- WHILE the migration is planned and implemented THE SYSTEM SHALL NOT increase
  `labs` memory footprint as a result of the change.
- IF an extension cannot be migrated before the deprecated path is removed
  upstream THEN THE SYSTEM SHALL flag it explicitly as a blocking risk to the next
  core version bump, rather than allowing a silent gap to surface at rollout time.

## Out of scope
- Actually adopting the openclaw 2026.7.2-beta.7 / 2026.8-line core release itself
  — this proposal is about preparing extensions for the migration, not the core
  version bump decision (that remains a separate rollout decision, still subject
  to `labs` → `admins` → `ovk` ordering).
- Non-Discord extensions beyond the inventory/classification step, unless the
  inventory finds they also depend on the deprecated hook/import path (in which
  case they get the same remediation-plan treatment, but deep validation work for
  every other channel is not committed to in this proposal).
- Fixing the upstream `@openclaw/discord` official plugin itself (#122655) — that
  is an upstream bug in a package the fork does not maintain; this proposal only
  covers the fork's own extension code and registration path.
- Correcting `context/current-version.md`'s stale baseline — `context/` is
  read-only for this agent; already noted as a separate documentation-hygiene item
  in the inbox.
