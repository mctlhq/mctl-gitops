# Tasks: egress-network-policy

- [ ] 1. Inventory egress endpoints — produce a full list of hosts/CIDRs that openclaw pods
  actually reach in the three tenants — DoD: a table of endpoints (hostname, port, protocol,
  tenant) is captured in the PR description; covers S3, all active channels from
  `context/architecture.md`, the upstream marketplace, `api.mctl.ai`

- [ ] 2. Base NetworkPolicy manifest (depends on 1) — create `egress-network-policy.yaml`
  in `gitops/base/network-policy/` with rules: default-deny egress, allow DNS, allow S3
  (placeholder CIDR), allow channel APIs, allow marketplace, allow mctl-api — DoD: the
  manifest is valid (`kubectl apply --dry-run=client`), contains all endpoints from task 1,
  passes review

- [ ] 3. Tenant overlays (depends on 2) — create Kustomize patches in
  `gitops/overlays/{labs,admins,ovk}/network-policy/` with tenant-specific S3 CIDR/FQDN —
  DoD: three overlay files, each passing `kustomize build` without errors

- [ ] 4. Apply the NetworkPolicy in `labs` (depends on 3) — add the labs overlay to the
  ArgoCD Application, run a sync, observe for 48 hours — DoD: ArgoCD shows Synced+Healthy
  for the labs namespace; openclaw logs contain no connection errors against allowed
  endpoints; the s3-sync canary does not alert; the restore-state probe passes

- [ ] 5. Apply the NetworkPolicy in `admins` (depends on 4) — same as task 4 for the admins
  namespace, observe for 24 hours — DoD: ArgoCD Synced+Healthy; no connection errors; admins
  functional channels work

- [ ] 6. Apply the NetworkPolicy in `ovk` (depends on 5) — same for the ovk namespace —
  DoD: ArgoCD Synced+Healthy; the restore-state probe passes; the s3-sync canary is active
  and green; no production ovk channel has lost connectivity 24 hours after applying

## Tests

- [ ] T1. Dry-run validation — `kubectl apply --dry-run=server -f egress-network-policy.yaml`
  for each tenant; expected: no errors, no warnings

- [ ] T2. Positive test: allowed egress — after applying in labs run `kubectl exec` on the
  openclaw/labs pod and curl each endpoint from the whitelist (S3, Telegram API, Discord
  API, `api.mctl.ai`); expected: HTTP 200 / response without connection refused

- [ ] T3. Negative test: blocking off-target egress — from openclaw/labs pod try to reach
  an internal cluster IP (for example, kube-apiserver or another namespace's service) not
  in the whitelist; expected: connection timeout or ICMP reject within < 5 seconds

- [ ] T4. DNS reachability — in the openclaw/labs pod run `nslookup api.telegram.org`
  and `nslookup s3.<region>.amazonaws.com`; expected: successful resolution

- [ ] T5. S3-sync canary — after applying in labs confirm the s3-sync canary workflow
  finishes successfully on the next cycle; expected: green canary, fresh S3 timestamp

- [ ] T6. Restore-state probe — after applying in labs restart the openclaw/labs pod
  manually (`kubectl rollout restart`) and confirm the readiness probe passes within the
  standard timeout; expected: pod transitions to Ready without an ArgoCD rollback

## Rollback

NetworkPolicy is a separate Kubernetes object, decoupled from the openclaw Deployment.
Rollback runs without restarting pods and without changing the openclaw version:

1. `kubectl delete networkpolicy egress-openclaw -n <namespace>` — restores unrestricted
   egress for the given tenant immediately.
2. Or: remove the overlay from gitops and run an ArgoCD sync with prune — the policy is
   removed via ArgoCD.

Rollback does not affect S3 state, the s3-sync canary or the restore-state probe. Rollback
is safe at any time without coordination with the openclaw team.

Recommended rollback order during an incident: revert `ovk` first, then `admins`, then `labs`
(reverse of ADR 0001).
