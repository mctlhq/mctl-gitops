# RedLoop Gate 4: empirical egress probe

Gate 4 requires proof that a workload in the `redloop` namespace cannot
reach the internet, the Kubernetes API or other namespaces. The tenant
values (`platform-gitops/tenants/redloop/values.yaml`) say so, and the
NetworkPolicies read back from the cluster agree:

| Policy | Effect on a non-workflow pod |
|---|---|
| `default-deny-all` | denies all ingress and **all egress**, DNS included |
| `allow-ingress-from-monitoring` | ingress from the `monitoring` namespace only |
| `allow-ingress-from-traefik` | ingress from `traefik` and `kube-system` only |
| `allow-workflow-internet-egress` | selects only pods labelled `workflows.argoproj.io/workflow`; does not apply |

Configuration is not evidence. kube-router enforces these policies and
keeps no flow logs, so the only proof is a packet that does not arrive.
This runbook produces that proof once, reproducibly.

**Status: prepared, not run.** Creating the pod is a Kubernetes mutation.
It needs its own operator GO and must not be run as part of a Draft PR or
a review.

## What runs

The probe is [`redloop/egress-probe-pod.yaml`](redloop/egress-probe-pod.yaml):
a one-shot pod in `redloop` that runs only `curl` and `nslookup`.

- It passes Pod Security `restricted`, which the namespace enforces: non-root
  uid 100, read-only root filesystem, all capabilities dropped, seccomp
  RuntimeDefault, no service-account token.
- It fits the namespace quota and LimitRange, and carries no label any
  NetworkPolicy selects. Like the synthetic-staging pod, it is governed only
  by `default-deny-all`.
- The kubelet kills it after 300 s at the latest (`activeDeadlineSeconds`),
  and it is never restarted. The pod object stays until it is deleted.
- The image is `curlimages/curl` 8.11.1, pinned by its multi-arch index
  digest and pulled from Docker Hub. The pull happens on the node, not from
  the pod, so the pod's egress policy does not affect it.

Admission was checked without creating anything:
`kubectl apply --dry-run=server` on 2026-11-17 returned
`pod/redloop-egress-probe created (server dry run)` with no Pod Security
warning, and a follow-up `get` returned NotFound.

## Checks and expected outcomes

Each check prints `probe name=<check> rc=<curl exit> verdict=<...>`.

| Check | Target | Expected | Proves |
|---|---|---|---|
| `loopback-control` | `127.0.0.1:1` | `rc=7 OTHER` | the tool runs and returns a fast refusal; the exit codes mean what they say |
| `external-ip-https` | `https://1.1.1.1/` | `BLOCKED` (rc 28) | no internet egress by IP, so a DNS block is not the only control |
| `external-ip-http` | `http://1.1.1.1/` | `BLOCKED` | same, port 80 |
| `external-name` | `https://example.com/` | `BLOCKED` or `NO_DNS` | no egress by name |
| `kube-api` | `kubernetes` Service ClusterIP `:443` | `BLOCKED` | no path to the API server even with a stolen token |
| `kube-dns-udp` | `kube-dns` ClusterIP, UDP 53 | `BLOCKED` | no DNS, which closes DNS as an exfiltration channel |
| `cross-namespace` | `blackbox-exporter.monitoring` ClusterIP `:9115` | `BLOCKED` | no lateral movement to another namespace |
| `same-namespace` | the synthetic-staging Service `:80` | `BLOCKED` | `allowIntraNamespace: false` holds: pods in redloop cannot reach each other |
| `metadata-169` | `169.254.169.254` | `BLOCKED` | no cloud metadata endpoint |

**PASS** requires all of these:

- all nine `probe name=` lines plus `probe done` are present in the log;
- `loopback-control` is `rc=7`;
- no line says `REACHABLE`.

A log that is missing, truncated or lacks `probe done` is **unknown**, not a
pass. Do not record Gate 4 egress as proven from it; rerun.

`OTHER` with `rc=7` on a deny check means a reset or an ICMP reject came
back instead of a silent drop. The packet was still stopped, so this is not
a failure, but write it down: it is evidence that something on the path
answers.

### The detector was proven both ways

The script was run locally in the same image under the same hardening
(`--read-only --user 100:101 --cap-drop ALL`):

- **Unfiltered network:** `external-ip-https`, `external-ip-http` and
  `external-name` came back `REACHABLE` (rc 0). The probe can see a breach.
- **`--network none`:** no check returned `REACHABLE`. The probe does not
  invent one.

Unroutable placeholder targets (TEST-NET-1) stood in for the cluster
addresses in both runs.

## Procedure (after a separate GO)

Read-only lookups first. The manifest commits no cluster addresses (this
repository is public), so they are filled in at apply time:

```bash
export KUBECONFIG=~/.kube/mctl-preview-config.yaml
API=$(kubectl -n default get svc kubernetes -o jsonpath='{.spec.clusterIP}')
DNS=$(kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP}')
BB=$(kubectl -n monitoring get svc blackbox-exporter -o jsonpath='{.spec.clusterIP}')
RL=$(kubectl -n redloop get svc redloop-redloop-synthetic-staging-base-service -o jsonpath='{.spec.clusterIP}')
render() {
  sed -e "s/__KUBE_API_CLUSTER_IP__/$API/" -e "s/__KUBE_DNS_CLUSTER_IP__/$DNS/" \
      -e "s/__BLACKBOX_CLUSTER_IP__/$BB/" -e "s/__REDLOOP_SVC_CLUSTER_IP__/$RL/" \
      docs/runbooks/redloop/egress-probe-pod.yaml
}
render | grep -c '__' # must print 0
render | kubectl apply --dry-run=server -f -
```

Then the mutation, the evidence and the cleanup:

```bash
render | kubectl apply -f -
kubectl -n redloop wait --for=jsonpath='{.status.phase}'=Succeeded pod/redloop-egress-probe --timeout=180s
kubectl -n redloop logs redloop-egress-probe | tee redloop-egress-probe-$(date -u +%Y%m%dT%H%M%SZ).log
kubectl -n redloop delete pod redloop-egress-probe --wait=true
kubectl -n redloop get pod redloop-egress-probe   # must be NotFound
```

Put the log, the output of `kubectl -n redloop get networkpolicy -o yaml`
taken at the same time, and the commit SHA of this file on the Gate 4 PR
or issue as evidence.

The pod is outside GitOps. Argo CD does not manage it, so it will not
prune it either. The `delete` line is not optional, and quota keeps at most
4 pods in the namespace.

### Rollback

There is nothing to roll back. The pod changes no policy and ends by itself
after 300 s. If it is stuck in `Pending` (image pull, quota), delete it.

### Optional strengthening: a positive control in the cluster

The local runs prove the script can see a breach. To prove that the
cluster-side setup can too, run the same pod in a namespace whose policy
does allow egress, and check that the external lines come back
`REACHABLE`. That is a second mutation in a second namespace, so it needs
its own GO. Without it, the Gate 4 claim rests on the local proof plus the
policy read-back, and the PR evidence should say so.
