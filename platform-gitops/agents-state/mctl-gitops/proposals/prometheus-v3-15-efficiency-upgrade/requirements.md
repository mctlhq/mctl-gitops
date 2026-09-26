# Upgrade Prometheus to v3.15.0 for scrape-compression and service-discovery efficiency

## Context
Prometheus v3.15.0 introduces several efficiency-focused improvements over our current
tracked baseline: Unix Domain Socket scraping, the OM2.0 scrape format, stabilized XOR2 float
chunk encoding, runtime log-level configuration, zstd scrape-response compression, and AWS
service-discovery efficiency improvements. This is a performance/efficiency proposal, not a
security-driven one — the relevant CVEs surfaced this cycle (CVE-2026-40179, CVE-2026-42151)
are already resolved by versions predating v3.15.0 and are tracked separately (see
`prometheus-security-patch` and the inbox "Dropped" notes).

The `labs` tenant is currently running at ~83% of its CPU limit and ~70% of its memory limit
per this cycle's metrics snapshot (`context/architecture.md` flags `labs` as a tenant to watch
for resource pressure). Reduced scrape/network/CPU overhead from zstd compression and
scrape-format/SD efficiency gains is a genuine opportunity to ease that pressure rather than
add to it, which is why this proposal is framed as a performance win specifically relevant to
`labs`, not a routine version-currency bump.

## User stories
- AS a platform operator I WANT Prometheus scrape traffic to use zstd compression and the more
  efficient OM2.0 format SO THAT scrape-related CPU and network overhead is reduced across all
  tenants, particularly the resource-constrained `labs` tenant.
- AS the mctl-gitops owner I WANT service-discovery efficiency improvements (AWS SD) adopted
  SO THAT discovery overhead does not grow unnecessarily as tenant workloads scale.
- AS an SRE I WANT confirmation that the upgrade does not regress metric correctness (chunk
  encoding change) SO THAT dashboards and alerts remain accurate after the upgrade.

## Acceptance criteria (EARS)
- WHEN Prometheus is upgraded to v3.15.0, THE SYSTEM SHALL continue scraping all currently
  configured targets in both `admins` and `labs` without data gaps.
- WHEN zstd scrape-response compression is available and supported by a target's exporter,
  THE SYSTEM SHALL negotiate and use compression to reduce scrape payload size.
- WHILE the upgrade is applied incrementally, THE SYSTEM SHALL maintain existing alerting rules
  and dashboards functioning without modification (no breaking query/API changes expected at
  this version).
- IF the XOR2 float chunk encoding change affects on-disk data compatibility with the prior
  chunk format, THEN THE SYSTEM SHALL verify read-compatibility with existing TSDB blocks
  before rollout and document any required migration step.
- IF post-upgrade CPU/memory usage in `labs` increases rather than decreases, THEN THE SYSTEM
  SHALL treat this as a regression and roll back per the rollback plan in `tasks.md`.

## Out of scope
- CVE-2026-40179 and CVE-2026-42151 remediation — both are already fixed by versions predating
  v3.15.0 and are folded into version-currency framing here, not tracked as separate CVE fixes;
  see `prometheus-security-patch` for the original CVE-driven proposal (different, older CVE
  set).
- Migrating scrape configs to Unix Domain Sockets platform-wide — the capability is adopted as
  available, but a full migration of existing TCP-based scrape targets is a separate, optional
  follow-up, not required by this proposal.
- Any change to Loki, Vault, or other observability-adjacent components.
- Increasing `labs` tenant resource quota — this proposal is about reducing usage within the
  existing quota, not requesting more.
