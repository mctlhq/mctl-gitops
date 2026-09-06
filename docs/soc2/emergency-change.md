# Emergency change procedure

Normal path: feature branch → PR → Claude P1/P2 gate → merge commit →
Argo CD. This file is the only designed exception.

## What counts as emergency

- Cluster or control-plane outage (API/Vault/Argo CD down).
- Active credential leak.
- Restore from backup.

Not an emergency: image bumps (use `gitops-bump`), docs, Type I paper,
feature work.

## Allowed actions

1. **Hotfix PR** with a shortened review if Claude is unavailable. Still
   a PR unless the next item applies.
2. **Force-push / ruleset bypass / direct main** only if a PR cannot
   restore service. Must be explicitly requested (workspace `AGENTS.md`).
3. **kubectl / vault operator** against live state only to restore
   service. Follow up with a GitOps commit so git matches the cluster.
4. **Manual `review-gate` override.** `main-protection`'s
   `current_user_can_bypass=never` (`docs/soc2/compensating-controls.md`,
   `docs/soc2/risk-register.md`) means there is no ruleset-bypass path for a
   wedged or incorrectly-`failure` `review-gate` check (`#1040`). Post a
   commit status directly instead -- an ordinary repo write, not a ruleset
   action, so it works even with bypass closed:
   ```
   gh api repos/mctlhq/mctl-gitops/statuses/{sha} -f state=success \
     -f context=review-gate -f description="manual override: <reason>"
   ```
   Unlike items 1-3 this is not limited to the outages this file otherwise
   covers -- it exists because `review-gate` itself has no other escape
   hatch. Still goes through the write-up requirement below.

`gitops-bump` / `release-deploy` are **not** emergencies. They are
standing, scoped exceptions.

## Afterward (within 7 days)

Write `docs/soc2/evidence/emergency-YYYY-MM-DD.md` with: trigger, actions,
who bypassed, links to commits, whether git was reconciled, residual risk.

Quarterly access review checks that emergencies were logged.
