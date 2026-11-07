# Design: argocd-patch-serversidediff-fix

## Current state
Argo CD (`ops.mctl.ai`) reconciles this repo through App-of-Apps (see `/app/agents/mctl-gitops/context/architecture.md`). The running version and ServerSideDiff status are unknown from `context/`. Architecture rules forbid major upgrades on patch-day and mention an Argo 3.7.10 archive bug (Argo Workflows, a separate component) as a reminder that version jumps have broken things before. Earlier proposals on ServerSideDiff leaks exist in `proposals/`; check their status first.

## Proposed solution
1. Discovery: read the running Argo CD version, and check where ServerSideDiff is enabled (`controller.diff.server.side` in `argocd-cmd-params-cm`, `argocd.argoproj.io/compare-options: ServerSideDiff=true` annotations, ApplicationSet templates).
2. Verification: confirm CVE IDs and fixed versions against NVD and the Argo CD GHSA. Choose the target as the newest verified patch in the same minor line (3.2.x, 3.3.x or 3.4.x). Minimum fixed versions per the inbox (unverified): 3.2.12, 3.3.10, 3.4.2.
3. Interim mitigation if ServerSideDiff is enabled and upgrade is delayed: disable it until the upgrade.
4. Upgrade: bump the image tag/chart version in the Argo CD definition in this repo, via git commit, applied to `admins` first. Read the release notes between the current and target patch for behavior changes. Check namespace quota (including `labs`) for the rolling restart surge before rollout.
5. Validate and keep the previous tag for rollback.

Why this way: same-minor patch bumps are low-risk, align with the platform rule against jumps, and git-based changes keep an audit trail.

## Alternatives
- Upgrade to v3.6.1 or the latest minor: rejected, violates the no-jump rule and v3.6.1 has no security value.
- Only disable ServerSideDiff: kept as an interim measure, but it leaves the vulnerable code on a critical component and may not cover all paths.
- Do nothing until IDs are verified: rejected, a patch bump within the line is cheap, but the target version is still gated on verification.

## Platform impact
- Migrations: none expected for patch releases; read release notes for CRD or config changes.
- Backward compatibility: patch-level, same minor; ServerSideDiff behavior may change slightly if disabled interim.
- Resource impact: Argo CD runs in `admins`, not `labs`. A rolling restart briefly raises pod count; verify against quota and note `labs` is close to its memory limit, so confirm the restart does not shift scheduling pressure onto shared nodes. No permanent memory increase expected.
- Risks and mitigations: brief sync interruption (do it off-peak, one component at a time); patch regressions (stage, watch 24h, rollback by reverting tag); unverified CVE IDs (verification task gates the version choice); overlap with older proposals (reconcile them to avoid double work).
