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

`gitops-bump` / `release-deploy` are **not** emergencies. They are
standing, scoped exceptions.

## Afterward (within 7 days)

Write `docs/soc2/evidence/emergency-YYYY-MM-DD.md` with: trigger, actions,
who bypassed, links to commits, whether git was reconciled, residual risk.

Quarterly access review checks that emergencies were logged.
