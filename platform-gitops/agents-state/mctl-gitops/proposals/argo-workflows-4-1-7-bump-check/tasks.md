# Tasks: argo-workflows-4-1-7-bump-check

- [ ] 1. Determine deployed Argo Workflows version — DoD: version recorded.
- [ ] 2. Review 4.1.7 changelog and verify advisory IDs (depends on 1) — DoD: notes in PR.
- [ ] 3. Bump controller, server and executor tags to 4.1.7 if applicable (depends on 2) — DoD: PR merged, ArgoCD Synced.
- [ ] 4. Check archive and CronWorkflow behavior (depends on 3) — DoD: tests below pass.

## Tests
- [ ] T1. A Succeeded workflow is archived without error.
- [ ] T2. Next scheduled CronWorkflow runs on time.
- [ ] T3. A build pipeline runs end to end.

## Rollback
Revert the bump commit; ArgoCD restores the previous tags. Drain in-flight workflows first.
