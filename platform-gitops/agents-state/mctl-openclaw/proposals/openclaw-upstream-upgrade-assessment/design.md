# Design: openclaw-upstream-upgrade-assessment

## Current state
All three tenants (`admins`, `labs`, `ovk`) run image tag `2026.7.11-beta.2`
per `mctl_get_service_status`/`mctl_get_service_config`, unchanged for at
least three consecutive weekly passes. Upstream is now three release trains
ahead: `2026.7.35` (LTS), `2026.9.5`, `2026.9.6` (mainline). See
`context/architecture.md` for the tenant layout, `context/decisions/0001-*`
for the mandated rollout order, and `context/decisions/0002-*` for the
S3-sync canary / restore-state probe guardrails. `context/current-version.md`
is separately known to be stale (tracked by prior proposals) and should be
corrected as part of this work's completion.

## Proposed solution
A two-phase approach:

**Phase A — assessment (primary deliverable of this proposal).** Produce a
decision document that: (1) confirms `2026.7.11-beta.2`'s exposure against
all currently-published GHSA advisories via the primary advisories page, (2)
evaluates `2026.8.1`, `2026.7.35` (LTS), and `2026.9.6` (mainline) as
candidate upgrade targets, weighing "LTS = smaller diff, slower cadence,
backport-completeness unconfirmed" against "mainline = current but larger
diff and a recent same-day rebuild for a launch crash", and (3) resolves the
three unconfirmed adjacent signals (CCB Belgium, Infosecurity, betterclaw.io)
to specific GHSA/CVE IDs or logs them as non-actionable noise. Phase A also
explicitly reconciles this proposal with the pre-existing
`ghsa-batch-2026-09-11-upgrade-assessment` and older upgrade proposals so
only one upgrade track is executed.

**Phase B — rollout.** Standard ADR-0001 canary rollout: `labs` first (with
explicit memory/CPU baseline-vs-post-upgrade monitoring against its
recently-resized 14Gi/16-CPU quota), an observation window, then `admins`,
then `ovk`, with canary-pause / restore-state-probe handling exactly per
ADR-0002.

## Alternatives
- **Jump straight to `2026.9.6` (mainline) without an assessment phase.**
  Rejected: skips exposure confirmation, and `2026.9.6`'s own release notes
  mention a same-day rebuilt binary after a launch crash — insufficient soak
  time to trust blindly.
- **Stay on the LTS line only (`2026.7.35`) indefinitely.** Deferred, not
  rejected: smaller diff and "critical security updates" per its own notes,
  but backport completeness for all fork-relevant advisories is unconfirmed
  (same open question already flagged against the June-line LTS in the
  sibling GHSA-batch proposal) — Phase A must close this before choosing.
- **Wait for the CCB Belgium / Infosecurity signals to be fully corroborated
  before upgrading at all.** Rejected: the version-lag itself (three trains,
  a known `2026.8.1+` fix for two confirmed High advisories) is already
  independently actionable; waiting only extends exposure. Adjacent signals
  become validation sub-tasks, not blockers.

## Platform impact
- **Migrations:** standard image-tag bump via mctl-gitops/Helm values per
  tenant; no data/schema migration expected, but Phase A must check the
  chosen target's release notes for any S3 state-layout change.
- **Backward compatibility:** a three-train jump raises the risk of breaking
  changes in the plugin SDK/channel extensions; Phase A must diff the
  plugin-sdk surface used by `extensions/*` against the target's changelog.
- **Resource impact (`labs`):** `labs` sits at ~72-73% of its recently
  resized 14Gi memory quota and ~83% of its 16-CPU quota — the tightest
  tenant on the platform. This rollout must treat `labs` as a genuine canary:
  capture a memory/CPU baseline immediately before the bump, monitor through
  the full observation window, and gate promotion on an explicit
  memory-increase threshold. Any measured increase blocks promotion to
  `admins`/`ovk`, per the platform's zero-tolerance `labs`-memory guardrail.
- **Risks and mitigations:**
  - Risk: canary/restore-state-probe regressions from a large version jump →
    Mitigation: follow ADR-0002's canary-pause/restart-with-delay procedure
    exactly; never shorten the probe timeout.
  - Risk: `ovk` downtime ("restarts are painful") → Mitigation: `ovk` is
    always last, only after a full `labs` + `admins` soak; no direct-to-`ovk`
    rollout (ADR-0001).
  - Risk: duplicated/conflicting effort with `ghsa-batch-2026-09-11-upgrade-assessment`
    and older upgrade proposals → Mitigation: Phase A explicitly reconciles
    all of them; execution should mark superseded proposals as closed.
