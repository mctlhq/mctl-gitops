# Design: plugin-sdk-migration-discord-compat

## Current state
Per `context/architecture.md`, the fork's Plugin SDK usage is: extensions live in
`extensions/*` and import `openclaw/plugin-sdk/*`. The architecture doc also lists
"Channel-agnostic refactors" under "Known limitations / footguns" — changes to
shared SDK/plugin surfaces affect **all** built-in and extension channels and need
routing/allowlist/pairing/onboarding/docs verification, not just the specific
channel being tested.

Deployed image tag across all three tenants is `2026.7.11-beta.2` (per the
researcher's `mctl_list_services` check), which is chronologically past the
2026.7.2-beta.7 release that introduced the `before_agent_start` deprecation.
Whether the fork's currently-deployed extensions already exercise a deprecated
path (and are only working because the legacy path hasn't been fully removed yet)
or have already been implicitly migrated is unknown — the researcher pass did not
inspect fork source, only upstream release notes and issue trackers. Upstream
issue #122655 additionally shows the *official* Discord plugin breaks on
registration after the same SDK export change, which is a concrete precedent for
what could go wrong in the fork's own Discord extension if it shares the affected
export surface.

## Proposed solution
Two phases, matching the effort-3 / "plan + validate" framing of the finding
rather than a full big-bang migration:

**Phase 1 — Inventory and risk classification (low risk, read-only):**
1. Enumerate all packages under `extensions/*` and grep for
   `openclaw/plugin-sdk/*` imports and `before_agent_start` hook registrations.
2. For each, determine whether the specific import/hook usage matches the
   deprecated surface described in the 2026.7.2-beta.7 release notes, or the
   export-change symptoms described in upstream #122655.
3. Produce a per-extension classification: unaffected / needs-migration /
   needs-investigation, with the Discord extension always in the
   needs-investigation-at-minimum bucket given #122655's direct precedent.

**Phase 2 — Remediation for affected extensions, Discord first:**
4. For each extension classified needs-migration, write the specific code change
   (updated import paths / new registration API in place of `before_agent_start`)
   as a scoped patch.
5. Deploy and validate in `labs` only first: confirm the extension still loads,
   registers, and (for Discord specifically) can send/receive a test message.
   Explicitly check `labs` memory metrics before/after to confirm no increase.
6. After an observation period in `labs` (per ADR-0001's rollout order), promote
   the same change to `admins`, then `ovk`, re-validating channel function at each
   step.
7. Any extension that cannot be cleanly migrated before the legacy path is fully
   removed upstream is flagged as a blocking risk against adopting any future core
   version that removes the legacy path — this becomes an explicit gate on the
   *separate* decision (out of scope here) to bump the deployed core version.

This treats the Discord registration check as the concrete, testable proof point
for the migration approach (mirroring #122655's failure mode) while keeping the
broader SDK migration scoped to inventory + classification, not a full rewrite of
every channel extension in one pass.

## Alternatives
- **Wait until the next core version bump forces the migration.** Dropped:
  deployed tenants are already on `2026.7.11-beta.2`, past the beta that
  introduced the deprecation; waiting risks a forced, unplanned migration under
  time pressure during a future core bump, exactly when `ovk`'s "restarts are
  painful" constraint (per `context/architecture.md`) makes mistakes most costly.
- **Migrate all `extensions/*` packages in one large PR/rollout.** Dropped: this is
  a channel-agnostic refactor per the architecture doc's footgun list, and a
  single big-bang change increases blast radius across every channel
  simultaneously. A per-extension, Discord-first approach is safer and matches the
  effort-3 (not effort-5) sizing of the finding.
- **Fix the upstream `@openclaw/discord` package directly (#122655) instead of
  auditing the fork's own extension.** Dropped: the fork does not maintain that
  upstream package (per `context/architecture.md`'s "What NOT to do" — don't proxy
  upstream issues without checking fork-relevance); the fork-relevant action is
  checking and fixing the fork's *own* `extensions/discord`-equivalent code, using
  #122655 only as a signal of what symptom to look for.

## Platform impact
- **Migrations:** code-level migration of plugin import paths / hook registration
  in affected `extensions/*` packages only (scope determined by Phase 1
  inventory). No data migration, no S3 schema change, no skills-layer change.
- **Backward compatibility:** the deprecated `before_agent_start` path is expected
  to keep working for some transition period upstream (per the beta release
  framing as "deprecates", not "removes"), so this migration can be rolled out
  incrementally without a hard cutover; extensions not yet migrated continue to
  function until upstream actually removes the legacy path — but that removal
  timeline is not confirmed here, so any extension left un-migrated should be
  explicitly tracked as a risk (per requirements.md acceptance criteria) rather
  than assumed safe indefinitely.
- **Resource impact (especially `labs`):** the migration is an import/registration
  code change, not a new process or added dependency footprint; expected memory
  impact is effectively zero, but this must be explicitly confirmed against
  `labs` memory metrics before/after each extension's rollout (per requirements.md),
  consistent with `labs` being close to its memory limit.
- **Risks and mitigations:**
  - *Risk:* an extension is migrated incorrectly and silently fails to register,
    disabling a channel without an obvious error. *Mitigation:* explicit
    post-deploy validation step (channel registers + test message) in `labs`
    before promotion, mirroring the exact failure mode reported in #122655.
  - *Risk:* the Discord extension shares the same export-surface bug as the
    official `@openclaw/discord` plugin (#122655), and the fix is not as simple as
    an import-path update. *Mitigation:* Phase 1 explicitly investigates this
    case; if remediation is nontrivial, it is flagged as a blocking risk rather
    than force-fit into this proposal's scope, and can spawn a dedicated
    follow-up.
  - *Risk:* a channel-agnostic refactor (per the architecture doc's footgun)
    inadvertently affects routing/allowlist/pairing/onboarding for channels beyond
    Discord. *Mitigation:* Phase 1's per-extension inventory and classification is
    explicitly there to scope the blast radius before any code changes are made,
    and Phase 2 validates each affected extension individually rather than
    assuming a shared fix is safe everywhere.
  - *Risk:* rollout order is skipped under time pressure (e.g. going straight to
    `ovk` because a channel outage is urgent). *Mitigation:* this proposal commits
    to `labs` → `admins` → `ovk` ordering per ADR-0001 explicitly in both
    requirements.md and tasks.md; no fast-path to `ovk` is defined here.
