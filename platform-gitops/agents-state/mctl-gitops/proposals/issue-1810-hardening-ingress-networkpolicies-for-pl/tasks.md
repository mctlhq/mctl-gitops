# Tasks: issue-1810-hardening-ingress-networkpolicies-for-pl

- [ ] 1. Inventory live Temporal clients — confirm from cluster state (pod env
  `TEMPORAL_ADDRESS`, frontend connection logs or conntrack on the frontend
  pod) that the only sources are `temporal`, `mctl-api`, `admins`, `traefik`
  and the `labs` kuptsi-app pod; confirm the kuptsi-app pod's
  `app.kubernetes.io/instance` label value; confirm whether any
  `argo-workflows` pod dials 7233. — DoD: findings recorded in the PR
  description; allowlist adjusted if anything else appears.
- [ ] 2. Add `platform-gitops/infra-components/data/temporal/networkpolicy.yaml`
  with `allow-temporal-ingress` as in design.md (depends on 1) — DoD: file
  has header comment (threat, client table with file refs, rollback), every
  peer commented, 2-space YAML, kubeconform-valid.
- [ ] 3. Ensure CI validates the new manifest (depends on 2) — DoD:
  `validate-manifests.yml` covers `infra-components/data/temporal/` with
  kubeconform, or the PR notes why existing coverage already does.
- [ ] 4. Merge, wait for the temporal Application to sync, run tests T1-T5
  (depends on 3) — DoD: results posted on #1810.
- [ ] 5. Follow-up PR: `backstage` ingress allowlist, same shape (depends on 4)
  — DoD: merged, T1-style probe and forward-auth on a public service pass.
- [ ] 6. Follow-up PR: `argocd` ingress allowlist (depends on 5) — DoD:
  merged, UI via Traefik, argocd CLI from mctl-api/argo-workflows and repo
  sync still work.
- [ ] 7. Follow-up PR: `monitoring` ingress allowlist for Loki / VictoriaMetrics
  / Alertmanager, port-scoped where tenants push (depends on 6) — DoD:
  merged, Grafana dashboards and log queries work, scrape targets all up.
- [ ] 8. Open a separate issue for Temporal client authentication (mTLS or
  authorizer) — DoD: issue linked from #1810.

## Tests

- [ ] T1. From an ephemeral pod in a tenant namespace other than `labs` (e.g.
  `ovk`), `nc -zvw3 temporal-frontend.temporal.svc.cluster.local 7233` times
  out; same for 7234/7235/7239 against the history/matching/worker Services.
- [ ] T2. From a `labs` pod that is not kuptsi-app, the same probe times out.
- [ ] T3. From the kuptsi-app pod (both containers), 7233 connects and the
  `temporal-worker` sidecar logs keep showing task-queue polling.
- [ ] T4. DevLoop end to end: start via mctl-api `use_temporal`, query via
  `mctl_get_dev_loop`, approve signal via `mctl_approve_dev_loop` on a test
  issue; `admins` workers continue polling (worker SDK metrics in
  VictoriaMetrics keep reporting poll success).
- [ ] T5. `https://temporal.mctl.ai` loads after Backstage login and lists
  workflows; `temporal-namespaces-bootstrap` PostSync Job succeeds on a
  re-sync.
- [ ] T6. CI: `helm lint` / kubeconform green; tenant NetworkPolicy allowlist
  check unaffected (policy is outside tenant namespaces).

## Rollback

Delete `platform-gitops/infra-components/data/temporal/networkpolicy.yaml`
(revert the PR). The temporal Application prunes the NetworkPolicy
(`prune: true`) and reachability returns to the previous cluster-wide state
within one sync. For an emergency before the revert merges, `kubectl delete
networkpolicy allow-temporal-ingress -n temporal` (selfHeal will re-create it
on the next sync, so the revert must follow). Follow-up phases roll back the
same way, one file each. DevLoopWorkflow state is durable in shared-pg, so a
temporarily blocked client resumes once connectivity returns.
