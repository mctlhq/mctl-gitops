# Design: prometheus-v3-15-efficiency-upgrade

## Current state
Per `context/architecture.md`, Prometheus is deployed as part of the observability stack
(alongside Loki), likely templated through `platform-gitops/helm-charts/base-service/` or a
dedicated monitoring chart within `platform-gitops/services/<tenant>/`. Our tracked latest was
v3.14.0 last cycle; v3.15.0 was released Sep 24, 2026. `labs` tenant resource usage this cycle
is limits.cpu 13250m/16 (~83%), limits.memory 10016Mi/14Gi (~70%) — down from ~94%/~83% last
cycle after a quota increase, but absolute usage keeps climbing, so any efficiency headroom
matters for that tenant specifically per `context/architecture.md`'s explicit flag to watch
`labs` resource pressure.

## Proposed solution
1. **Version bump.** Update the Prometheus image/chart version pin in `platform-gitops` from
   the current tracked version to v3.15.0, following the same review process as other
   dependency-currency proposals in this repo.
2. **Enable zstd scrape-response compression** where exporters support it, to reduce per-scrape
   payload size and associated CPU/network cost — the primary efficiency lever relevant to
   `labs`.
3. **Adopt OM2.0 scrape format** where compatible, for parsing efficiency gains on the
   Prometheus server side.
4. **Leave XOR2 chunk encoding on its stabilized default** (no explicit opt-out), since it is
   now stable in v3.15.0, but verify TSDB read-compatibility with existing blocks before
   rollout (see Platform impact / Risks).
5. **Evaluate AWS SD efficiency improvements** if AWS-based service discovery is in use on this
   platform; adopt if applicable, otherwise no action needed (this is a no-op if the platform
   does not use AWS SD).
6. **Defer Unix Domain Socket scraping migration.** The capability is available in v3.15.0 but
   migrating existing scrape configs from TCP to UDS is a larger, optional follow-up not
   required to realize the primary compression/format efficiency gains — scoped out per
   `requirements.md`.
7. **Staged rollout with `labs`-first monitoring.** Given `labs` is the tenant under the most
   resource pressure, roll the upgrade out there first (or with heightened monitoring) so any
   unexpected regression is caught before wider rollout, and so the expected efficiency
   improvement can be measured directly against the tenant it is meant to help.

## Alternatives
- **Skip the upgrade and wait for a future release.** Rejected: v3.15.0's compression and SD
  efficiency gains directly address a live, flagged concern (`labs` resource pressure); waiting
  defers a low-risk, tangible improvement without clear benefit.
- **Adopt Unix Domain Socket scraping platform-wide immediately as part of this proposal.**
  Rejected as in-scope-now: requires reconfiguring scrape targets and exporters beyond a
  version bump, materially larger effort/risk than the compression and format gains, which are
  mostly configuration flags on the existing setup. Deferred to an optional follow-up.
- **Pursue quota increase for `labs` instead of an efficiency upgrade.** Rejected: this
  proposal is explicitly about reducing usage within existing quota rather than requesting
  more, consistent with `context/architecture.md` flagging `labs` as a tenant to watch rather
  than simply grow.

## Platform impact
- **Migrations:** Primarily a version bump plus scrape-config flag changes (enabling zstd
  compression, OM2.0 format). The XOR2 chunk-encoding stabilization requires a pre-rollout
  check that existing on-disk TSDB blocks remain readable under v3.15.0 — Prometheus minor
  version upgrades are generally forward-compatible with existing block formats, but this must
  be explicitly verified against the v3.15.0 release notes/upgrade guide before rollout rather
  than assumed.
- **Backward compatibility:** No breaking query/API changes expected at this version per the
  release notes summary; existing alerting rules and dashboards should continue to function
  unmodified. Compression negotiation is backward-compatible — exporters that do not support
  zstd simply continue uncompressed.
- **Resource impact (labs):** This is the core motivation. Expected net decrease in scrape-
  related CPU and network overhead in `labs` due to zstd compression and SD efficiency gains,
  which directly eases the tenant's ~83% CPU / ~70% memory pressure rather than adding to it.
  If actual post-upgrade measurement shows an increase instead, this must be treated as a
  regression (see Acceptance criteria) and triggers rollback.
- **Risks and mitigations:**
  - Risk: chunk-encoding stabilization introduces an unexpected TSDB read-compatibility issue.
    Mitigation: explicit pre-rollout compatibility check against release notes/upgrade guide,
    `labs`-first staged rollout with monitoring before wider adoption.
  - Risk: expected resource savings do not materialize (e.g. exporters don't support zstd).
    Mitigation: measure `labs` CPU/memory before and after rollout; if no improvement, the
    upgrade is still a safe version-currency bump but the efficiency framing is revisited.
  - Risk: version bump introduces unrelated regressions in scrape reliability. Mitigation:
    staged rollout, regression tests in `tasks.md` covering scrape target coverage and alerting
    continuity.
