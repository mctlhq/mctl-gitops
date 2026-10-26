# Tasks: issue-2159-hardening-enforce-approved-providers-onl

## Scope of this implementer run (owner amendment, 2026-10-26)

The egress policy applies to the agent pods that run DevLoop itself, so a wrong allowlist would
stop the pipeline that has to fix it, and stages B and C need observed traffic from real runs
between them. This run therefore delivers **stage A only**:

- In scope: tasks 1, 3 and 4. The proxy runs with the allow-all, log-every-host ACL, and the
  agent CWFTs route through it. For task 4, put the executor `podSpecPatch` behind the outcome
  of task 2: if its effect cannot be verified in this run, leave the executor containers
  unproxied (they keep today's direct egress, which stage A does not restrict) and record that
  in the runbook.
- Out of scope for this run, each a separate later PR after the owner reviews the stage A proxy
  log: task 2 (needs a live probe workflow), task 5 (stage B allowlist), task 6 (stage C
  NetworkPolicy) and tests T1-T6, which need live pods. Do NOT add
  `networkpolicy-agents-egress.yaml` or a deny ACL in this PR.
- Stage A must not change what any agent pod can reach. If the proxy is down, a run may fail;
  that is acceptable only because stage A is reverted by one commit (task-4 revert).
- Task 1's inventory must include the scout feed hosts from mctl-agents
  `agents/_scout/sources.yaml` (read via the GitHub API) as candidate allowlist entries.

- [ ] 1. **Finalise the traffic inventory.**
  - Read the scout feed hosts from mctl-agents `agents/_scout/sources.yaml`.
  - Read any non-essential hosts the Claude Code CLI contacts.
  - Add both to the table in design.md. Keep anything still unobservable marked unknown.
  - DoD: a committed `docs/runbooks/mctl-agents-egress.md` with a per-CWFT host list and evidence
    for each entry (implement, investigate, shepherd, run, scout, reconcile, usage-collector,
    approve, completion hook).
- [ ] 2. **Verify that executor `podSpecPatch` takes effect.** (depends on 1)
  - On the cluster's Argo version, submit a throwaway workflow whose `podSpecPatch` adds env to the
    `init` and `wait` containers.
  - DoD: `kubectl get pod -o yaml` shows the env on both executor containers. If it does not, switch
    the design to the Cloudflare-ranges ipBlock fallback and update design.md.
- [ ] 3. **Deploy the egress proxy (stage A).** (depends on 1)
  - Add `platform-gitops/bootstrap/templates/mctl-platform/mctl-agents-egress-proxy.yaml`: the
    `mctl-agents-egress` namespace, Squid ConfigMap (allow-all ACL with logging), Deployment
    (2 replicas), PDB, Service `agent-egress-proxy:3128`, and the namespace's ingress and egress
    NetworkPolicies.
  - DoD: the ArgoCD app is Healthy, and `curl -x` from a pod labelled
    `app.kubernetes.io/name: mctl-agents` succeeds with the request visible in the Squid log in
    Loki.
- [ ] 4. **Point agent pods at the proxy (stage A).** (depends on 2, 3)
  - In each of `cwft-mctl-agents-{implement,investigate,shepherd,run,scout,reconcile,usage-collector,approve}.yaml`:
    - add `HTTP(S)_PROXY`, `NO_PROXY` and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` to every
      step container;
    - add the executor `podSpecPatch`;
    - add `socat` to the `apk add` lines;
    - add a `ProxyCommand` to the `ssh.github.com` `~/.ssh/config` blocks.
  - DoD: `validate-manifests.yml` passes, and one run of each agent kind succeeds with all of its
    external traffic in the proxy log.
- [ ] 5. **Switch the proxy to the allowlist (stage B).** (depends on 4)
  - Replace the allow-all ACL with the `dstdomain` list from task 1.
  - DoD: one run of each agent kind succeeds, and the proxy log shows no denials except expected
    ones (e.g. WebFetch to non-approved hosts, listed in the runbook).
- [ ] 6. **Enforce the NetworkPolicy (stage C).** (depends on 5)
  - Add `platform-gitops/argo-workflows/config/networkpolicy-agents-egress.yaml`
    (`mctl-agents-egress`, podSelector `app.kubernetes.io/name: mctl-agents`,
    `policyTypes: [Egress]`, rules as in design.md), as a single-file PR.
  - DoD: T1-T5 pass, and one real run of each agent kind succeeds.
- [ ] 7. **Document.**
  - Finish the runbook: the allowlist, how to add a host (ConfigMap PR), how to read denials in
    Loki, and how to roll back.
  - Link it from `CLAUDE.md` Secrets Management next to the policy-checkpoint runbook.
  - Note enforcement in the profile comments, e.g. `scout-default/profile.yaml`.
  - DoD: runbook merged and linked.

## Tests

- [ ] T1. **Allowed destination.** From a debug pod in `argo-workflows` labelled
  `app.kubernetes.io/name: mctl-agents`, with the proxy env set,
  `curl -sS https://api.github.com/zen` succeeds.
- [ ] T2. **Non-allowlisted destination (red check).** From the same pod,
  `curl -sS https://example.com` returns proxy 403, and the denial is in the Squid log.
- [ ] T3. **Direct bypass (red check).** From the same pod, with the proxy env unset:
  - `curl --max-time 5 https://1.1.1.1` times out;
  - a connection to a node public IP on 10250 times out;
  - a connection to an arbitrary in-cluster Service (e.g. vault) times out;
  - `kubernetes.default:443` is still reachable.
- [ ] T4. **Platform pods unaffected.** From an unlabelled debug pod in `argo-workflows`, direct
  `curl https://example.com` and an in-cluster Service still succeed. One platform workflow (e.g.
  a deploy-service dry run) succeeds.
- [ ] T5. **Real runs.** One successful run each of implement, investigate, shepherd, run (full or
  incident-responder), scout, reconcile, usage-collector and approve, with the policy in place.
  The completion exit hook delivers its event to mctl-api.
- [ ] T6. **Rollback drill.** Reverting the task-6 commit removes `mctl-agents-egress`, and T3's
  direct `curl` then succeeds again.

## Rollback

- **Stage C (enforcement).** Revert the single commit that added
  `argo-workflows/config/networkpolicy-agents-egress.yaml`. After the next ArgoCD sync, agent pods
  are non-isolated for egress again. They still use the proxy, which keeps working.
- **Stage B.** Revert the ConfigMap ACL commit to restore allow-all.
- **Full rollback to today's behaviour.** Revert the task-4 CWFT commit to remove the proxy env, the
  `podSpecPatch` and the `ProxyCommand`. Wait about 3 minutes for the ArgoCD sync before
  resubmitting, since Argo snapshots templates at submit time. Then remove the proxy bundle.
- No state or data migration is involved, so every step is a pure manifest revert.
