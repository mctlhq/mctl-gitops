# Tasks: plugin-sdk-migration-discord-compat

- [ ] 1. Enumerate all `extensions/*` packages and grep for `openclaw/plugin-sdk/*`
  imports and any `before_agent_start` hook registrations. — DoD: a complete list
  of extensions with their current import/hook usage is documented.
- [ ] 2. For each extension in the inventory, classify as unaffected /
  needs-migration / needs-investigation, comparing against the deprecated-surface
  description in the 2026.7.2-beta.7 release notes. (depends on 1) — DoD: every
  extension has an explicit classification with the reasoning noted.
- [ ] 3. Specifically investigate the fork's Discord extension against the
  export-change symptoms described in upstream #122655 (official
  `@openclaw/discord` failing to register on core 2026.8). (depends on 1) — DoD:
  a determination of whether the fork's Discord extension shares the affected
  export surface, with supporting evidence (code inspection, and if feasible a
  registration test against a core version matching #122655's report).
- [ ] 4. For each extension classified needs-migration (including Discord if
  confirmed affected by task 3), write a scoped code patch updating the
  import path / registration call away from the deprecated surface. (depends on
  2, 3) — DoD: a patch exists per affected extension, touching only that
  extension's import/registration code, no unrelated changes bundled in.
- [ ] 5. Deploy and validate each patch in `labs` first, one extension at a time,
  starting with Discord. (depends on 4) — DoD: for Discord, the channel registers
  successfully and a test message can be sent/received in `labs`; for other
  affected extensions, equivalent functional validation is defined and passed.
- [ ] 6. Confirm `labs` memory metrics show no increase attributable to each
  migrated extension, sampled before and after its `labs` deployment. (depends on
  5) — DoD: memory comparison recorded per extension, confirming no measurable
  increase.
- [ ] 7. After an observation period in `labs` per ADR-0001, promote each
  validated patch to `admins`, then `ovk`, re-validating channel function at each
  tier. (depends on 5, 6) — DoD: all needs-migration extensions are running the
  updated code in all three tenants, each confirmed functioning post-rollout.
- [ ] 8. For any extension that cannot be cleanly migrated (task 4 blocked or
  task 3/5 reveals a deeper incompatibility), document it explicitly as a
  blocking risk against any future core version bump that removes the legacy
  `before_agent_start` path. (depends on 2, 3, 4) — DoD: a written risk note
  exists per blocked extension, to be consulted before any future core-version
  upgrade decision.

## Tests
- [ ] T1. Static check: after patching, no affected extension's source still
  references the deprecated `before_agent_start` hook or legacy
  `openclaw/plugin-sdk/*` import path flagged in task 2.
- [ ] T2. In `labs`, verify the Discord extension registers without error on
  pod startup post-migration.
- [ ] T3. In `labs`, send and receive a test message via the Discord channel
  post-migration.
- [ ] T4. In `labs`, repeat T2/T3-equivalent functional checks for every other
  extension migrated in task 4.
- [ ] T5. Confirm `labs` memory metrics (before/after comparison from task 6) show
  no measurable increase for any migrated extension.
- [ ] T6. Repeat T2-T4 in `admins` and then `ovk` before considering rollout of
  each extension's migration complete.

## Rollback
Each extension's migration is deployed and validated independently, `labs` first,
so a bad migration is caught before it reaches `admins`/`ovk`. If a migrated
extension misbehaves in `labs` (fails to register, breaks send/receive, or shows a
`labs` memory increase), revert that extension's specific import/registration
patch in `labs`, confirm the channel returns to its pre-migration working state,
and hold that extension's migration for rework before re-attempting. Because
patches are scoped per-extension (task 4), reverting one extension's change does
not require rolling back any other extension's already-promoted migration. If an
issue is only discovered after promotion to `admins` or `ovk`, revert that
tier's deployment to the prior image/patch state for the affected extension only,
prioritizing `ovk` recovery first given its high-SLA, restart-sensitive
constraints from `context/architecture.md`.
