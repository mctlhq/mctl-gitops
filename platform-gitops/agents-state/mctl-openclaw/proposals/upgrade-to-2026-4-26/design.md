# Design: upgrade-to-2026-4-26

## Current state

All three tenants (`ovk`, `labs`, `admins`) are pinned to openclaw 2026.3.14 in
`mctl-openclaw/package.json` and reflected in `context/current-version.md`. The
deployment pipeline is Docker → mctl-gitops → ArgoCD (see `context/architecture.md`).
State is stored in per-tenant S3 buckets; the restore-state readiness probe
(ADR-0002) gates ArgoCD rollout success; the s3-sync canary (ADR-0002) is paused
during rollouts.

Nine CVEs affecting 2026.3.14 are currently unpatched:
- CVE-2026-41371 (CVSS 8.5) — privilege escalation via `chat.send`
- CVE-2026-41349 (CVSS 8.7–8.8) — LLM agentic consent bypass via `config.patch`
- CVE-2026-41342 — auth bypass in remote onboarding
- CVE-2026-41352 (CVSS 8.8) — missing node-pairing authorization, RCE possible
- CVE-2026-41353 (CVSS 8.1) — allowProfiles access control bypass
- CVE-2026-41359 — Telegram config privilege escalation via send endpoint
- April batch CVEs 35636, 35639, 35641, 35668 and related issues (all fixed ≥ 2026.4.5)
- Rotated bearer token echo in `device.token.rotate` (2026.4.26 only)

A prior incomplete proposal (`upgrade-to-2026-4-25`) targeted 2026.4.25; this
proposal supersedes it by targeting 2026.4.26.

## Proposed solution

**Bump the upstream version to 2026.4.26 and roll it out tenant-by-tenant in
ADR-0001 order: `labs` → `admins` → `ovk`.**

Changes:
1. Update `package.json` (and any lockfile) to resolve `openclaw@2026.4.26` from
   the upstream npm registry / fork mirror.
2. Run the full test suite and extension compatibility check against 2026.4.26 in
   CI before promoting to any tenant.
3. Build a new Docker image tagged `2026.4.26-mctl-<sha>`.
4. Update the `labs` helm release in mctl-gitops; ArgoCD syncs; restore-state probe
   gates the rollout; s3-sync canary is paused then restarted with delay.
5. Observe `labs` for the defined observation window (minimum 24 h unless an
   incident forces earlier action). Validate memory metrics via `mcp__mctl__*`.
6. Promote to `admins` with the same canary/probe procedure.
7. Promote to `ovk` with the same canary/probe procedure.
8. Update `context/current-version.md` to reflect 2026.4.26 on all tenants.

Why this approach:
- The three-tenant rollout order is mandated by ADR-0001 and is the only
  production-safe path given `ovk`'s high SLA.
- Keeping the restore-state probe active throughout is mandated by ADR-0002;
  disabling it is explicitly out of scope.
- No code changes beyond the version bump are required; openclaw 2026.4.26 is a
  drop-in upgrade within the 2026.x series.

## Alternatives

**Option A — Cherry-pick only the CVE fixes on top of 2026.3.14.**
Rejected: the number of individual CVE patches (nine distinct fixes across multiple
release points: 2026.3.22, 2026.3.28, 2026.3.31, 2026.4.5+) makes cherry-picking
error-prone and harder to verify than taking the full release. The April batch CVEs
alone span 2026.4.5 through 2026.4.26.

**Option B — Upgrade to the latest nightly / HEAD.**
Rejected: HEAD is untested on our fork's extensions; we need a tagged release with
an upstream changelog to reason about compatibility. 2026.4.26 is the latest stable
tag that includes all fixes.

**Option C — Upgrade `ovk` directly to minimize time exposed.**
Rejected by ADR-0001 (explicitly forbidden) and by the operational risk of
skipping `labs` as a canary for a multi-CVE upgrade.

## Platform impact

**Migrations**
- No data migrations. S3 state format is unchanged between 2026.3.x and 2026.4.x
  in the upstream changelog.
- No schema changes to SQLite skill metrics (non-critical, reset on restart anyway).

**Backward compatibility**
- All three tenants move to the same version; skills YAML is unchanged.
- Extensions in `extensions/*` must be validated against the 2026.4.26 plugin SDK
  in CI (task 2 below) before any tenant is touched.

**Resource impact — `labs`**
- `labs` is close to its memory limit (see `context/architecture.md`).
- The upgrade must be validated for memory footprint in `labs` before promoting to
  `admins`/`ovk`. If memory increases by more than the headroom available in
  `labs`, promotion is blocked until the cause is identified and mitigated.
- CPU impact is expected to be neutral (patch release, no new background workers).

**Risks and mitigations**

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `labs` OOM after upgrade | Medium | Validate memory metric via mctl MCP before promoting; block on excess |
| Restore-state probe timeout on first start | Low | ArgoCD auto-rollback; probe timeout already tuned per ADR-0002 |
| Extension incompatibility with 2026.4.26 SDK | Low | CI plugin-sdk compatibility check gates the image build |
| Silent S3-sync regression | Low | s3-sync canary restarted after each rollout; alert threshold unchanged |
| Upstream 2026.4.26 itself contains a regression | Low | `labs` observation window catches it before `ovk` is touched |
