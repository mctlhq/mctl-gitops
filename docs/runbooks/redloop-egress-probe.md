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

Each check prints `probe name=<check> rc=<exit> connect=<time_connect> verdict=<...>`.
The last line is `probe checks=9 result=PASS|FAIL|UNKNOWN`, and the pod's
exit code is 0, 1 or 2 to match.

The verdict logic is default-deny: a check is `UNKNOWN` unless a rule
positively explains it.

| Verdict | Meaning | Counts as |
|---|---|---|
| `REACHABLE` | a TCP connection completed (`time_connect` > 0, whatever the exit code: TLS errors, empty replies and stalls after connect all land here), or DNS answered at all, NXDOMAIN and SERVFAIL included | **FAIL** |
| `BLOCKED` | curl timed out with no connection (rc 28, `time_connect` 0), or the DNS query timed out | expected |
| `REFUSED` | rc 7: a reset or ICMP reject came back without a connection. The packet was stopped, but something on the path answered; write it down | acceptable |
| `NO_DNS` | rc 6, accepted only for `external-name` | acceptable |
| `UNKNOWN` | anything else: a bad target, a missing binary, a protocol error, an unexpected code | **not a pass** |

| Check | Target | Expected | Proves |
|---|---|---|---|
| `loopback-control` | `127.0.0.1:1` | `REFUSED` (anything else makes the run `UNKNOWN`) | the tool runs and the exit codes mean what the table says |
| `external-ip-https` | `https://1.1.1.1/` | `BLOCKED` | no internet egress by IP, so a DNS block is not the only control |
| `external-ip-http` | `http://1.1.1.1/` | `BLOCKED` | same, port 80 |
| `external-name` | `https://example.com/` | `BLOCKED` or `NO_DNS` | no egress by name |
| `kube-api` | `kubernetes` Service ClusterIP `:443` | `BLOCKED` | no path to the API server even with a stolen token |
| `cross-namespace` | `blackbox-exporter.monitoring` ClusterIP `:9115` | `BLOCKED` | no lateral movement to another namespace |
| `same-namespace` | the synthetic-staging Service `:80` | `BLOCKED` | `allowIntraNamespace: false` holds: pods in redloop cannot reach each other |
| `metadata-169` | `169.254.169.254` | `BLOCKED` | no cloud metadata endpoint |
| `kube-dns-udp` | `kube-dns` ClusterIP, UDP 53 | `BLOCKED` | no DNS, which closes DNS as an exfiltration channel |

Before any check runs, the script validates every target as `IPv4[:port]`.
An empty or unrendered target (`__...__`) ends the run at once with
`result=UNKNOWN`. Without that guard, curl would fail fast with rc 3 and
look like a block.

**Evidence of isolation is only a log that ends in `probe checks=9 result=PASS`.**
`FAIL` is a finding. `UNKNOWN`, a missing log, or a log without the result
line means isolation was **not observed**. It is not a pass. Do not record
Gate 4 egress as proven from it; find out why and rerun.

### The detector was proven both ways

All runs were local, in the same image under the same hardening
(`--read-only --user 100:101 --cap-drop ALL`), with TEST-NET addresses
standing in for the cluster ones:

| Run | Result |
|---|---|
| unfiltered network, DNS target a real resolver | `external-*` and `kube-dns-udp` `REACHABLE`, `result=FAIL`, exit 1: the probe sees a breach on every channel it claims to cover |
| unfiltered network, DNS target unroutable (silent drop) | `kube-dns-udp` `BLOCKED`: a dropped DNS query is told apart from an answered one |
| `--network none` | no `REACHABLE`; `kube-dns-udp` `UNKNOWN` ("Network unreachable" is not a timeout), so `result=UNKNOWN`, exit 2: an unexplained outcome is not promoted to a pass |
| empty target / unrendered `__KUBE_API_CLUSTER_IP__` | `bad-target`, `result=UNKNOWN`, exit 2 |

## Procedure (after a separate GO)

Read-only lookups first. The manifest commits no cluster addresses (this
repository is public), so they are filled in at apply time:

```bash
export KUBECONFIG=~/.kube/mctl-preview-config.yaml
API=$(kubectl -n default get svc kubernetes -o jsonpath='{.spec.clusterIP}')
DNS=$(kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP}')
BB=$(kubectl -n monitoring get svc blackbox-exporter -o jsonpath='{.spec.clusterIP}')
RL=$(kubectl -n redloop get svc redloop-redloop-synthetic-staging-base-service -o jsonpath='{.spec.clusterIP}')
: "${API:?}" "${DNS:?}" "${BB:?}" "${RL:?}"   # an empty lookup stops here
render() {
  sed -e "s/__KUBE_API_CLUSTER_IP__/$API/" -e "s/__KUBE_DNS_CLUSTER_IP__/$DNS/" \
      -e "s/__BLACKBOX_CLUSTER_IP__/$BB/" -e "s/__REDLOOP_SVC_CLUSTER_IP__/$RL/" \
      docs/runbooks/redloop/egress-probe-pod.yaml
}
if render | grep -q '__'; then echo 'unrendered placeholder, stop'; else echo 'rendered OK'; fi
render | kubectl apply --dry-run=server -f -
```

Then the mutation, the evidence and the cleanup:

```bash
render | kubectl apply -f -
# Succeeded = PASS, Failed = FAIL or UNKNOWN (the log's last line says which).
# Bounded: a pod that is never scheduled has no startTime, so
# activeDeadlineSeconds never fires. Give up after 6 minutes and treat it as UNKNOWN.
for i in $(seq 1 72); do
  ph=$(kubectl -n redloop get pod redloop-egress-probe -o jsonpath='{.status.phase}')
  case "$ph" in Succeeded|Failed) break ;; esac; sleep 5
done; echo "phase=$ph"   # anything but Succeeded/Failed: describe the pod, delete it, result UNKNOWN
kubectl -n redloop logs redloop-egress-probe | tee redloop-egress-probe-$(date -u +%Y%m%dT%H%M%SZ).log
kubectl -n redloop delete pod redloop-egress-probe --wait=true
kubectl -n redloop get pod redloop-egress-probe   # must say NotFound (non-zero exit is expected)
```

The last log line must read `probe checks=9 result=PASS`. Put the log, the output of `kubectl -n redloop get networkpolicy -o yaml`
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
