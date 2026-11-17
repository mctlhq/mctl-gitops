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
keeps no flow logs, so the only proof is a packet that does not arrive,
backed by the node's rules at the time.

**Status: run 1 FAILED (2026-11-17), next run not authorised.** Creating
the pod is a Kubernetes mutation and reading the node is privileged access.
Each run needs its own operator GO and must not be run as part of a Draft
PR or a review.

## Run history

Every run is recorded here. A later run never replaces an earlier result.

| Run | Date (UTC) | Manifest | Result | Evidence |
|---|---|---|---|---|
| 1 | 2026-11-17 22:22 | `4ba3ba91d` (single phase) | `result=FAIL` | log and verdict table on #2769; analysis held privately by the operator, not in this repository |
| 2 | not run | this revision (startup, wait, steady) | | |

Run 1 stays a FAIL. Its manifest had no startup phase, so it cannot be
reinterpreted after the fact as a steady-state result in either direction.

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

## Phases and output

A check taken at container start and a check taken once enforcement has
been observed answer different questions, so the probe reports them apart:

| Phase | Output | Counts toward the steady-state result |
|---|---|---|
| 1. startup | `probe phase=startup name=external-ip-https ...`, then `probe startup=OPEN\|CLOSED\|UNKNOWN` | **no** |
| 2. wait | repeats the external check every second until it stops connecting, at most `WAIT_MAX` (60 s); prints `probe enforcement-wait=<s>s observed=yes\|no last=<verdict>` | if never observed: yes, see below |
| 3. hold | `probe hold=start seconds=20`: the operator reads the node (procedure step 4) | |
| 4. steady | `probe phase=steady name=<check> ...` for the 9 checks | **yes** |
| 5. hold | `probe hold=end seconds=20`: the operator reads the node again | |
| result | `probe checks=<n> result=PASS\|FAIL\|UNKNOWN`, always the last line; exit code 0, 1 or 2 | |

If enforcement is not observed within `WAIT_MAX`, the steady checks do not
run: a check that was still connecting gives `result=FAIL` (egress is open), anything else gives `result=UNKNOWN`.

### Verdicts

| Verdict | Meaning | Counts as |
|---|---|---|
| `REACHABLE` | a TCP connection completed (`time_connect` > 0, whatever the exit code), or DNS answered at all, NXDOMAIN and SERVFAIL included | **FAIL** |
| `BLOCKED` | curl timed out with no connection (rc 28, `time_connect` 0), or the DNS query timed out | expected |
| `REFUSED` | rc 7 with no connection | **expected only with node evidence**, see below |
| `NO_DNS` | rc 6, accepted only for `external-name` | acceptable |
| `UNKNOWN` | anything else | **not a pass** |

kube-router enforces with `REJECT --reject-with icmp-port-unreachable`, so
in the steady state most checks come back `REFUSED`, external ones
included. From inside the pod a reject, a closed port and an unreachable
network all produce the same rc 7: the local runs below show `--network none`
giving exactly the output of a policy reject. `REFUSED` is therefore
accepted only when the node evidence in step 4 shows the rule that produced
it. Without that evidence a `REFUSED` counts as `UNKNOWN`.

### Steady-state checks

| Check | Target | Expected | Proves |
|---|---|---|---|
| `loopback-control` | `127.0.0.1:1` | `REFUSED` (anything else makes the run `UNKNOWN`) | the tool runs and rc 7 means what the table says |
| `external-ip-https` | `https://1.1.1.1/` | `REFUSED` or `BLOCKED` | no internet egress by IP |
| `external-ip-http` | `http://1.1.1.1/` | `REFUSED` or `BLOCKED` | same, port 80 |
| `external-name` | `https://example.com/` | `BLOCKED` or `NO_DNS` | no egress by name |
| `kube-api` | `kubernetes` Service ClusterIP `:443` | `REFUSED` or `BLOCKED` | no path to the API server |
| `cross-namespace` | `blackbox-exporter.monitoring` ClusterIP `:9115` | `REFUSED` or `BLOCKED` | no lateral movement |
| `same-namespace` | the synthetic-staging Service `:80` | `REFUSED` or `BLOCKED` | `allowIntraNamespace: false` holds |
| `metadata-169` | `169.254.169.254` | `REFUSED` or `BLOCKED` | no cloud metadata endpoint |
| `kube-dns-udp` | `kube-dns` ClusterIP, UDP 53 | `BLOCKED` | no DNS exfiltration channel |

The in-cluster targets must have a ready endpoint (preflight, step 1), so
that a `REFUSED` cannot be a service that is simply down.

### Classification

| Outcome | Requires | Means |
|---|---|---|
| **steady-state PASS** | last line `result=PASS`, node evidence from both holds (step 4), every in-cluster target had a ready endpoint | steady-state isolation observed for this pod |
| steady-state FAIL | `result=FAIL` | a finding |
| UNKNOWN | anything else: `result=UNKNOWN`, missing log or result line, missing or contradicting node evidence, a target without a ready endpoint | isolation **not observed**; find out why and rerun |
| startup observation | `probe startup=OPEN` | recorded for the operator, whatever the steady-state result, and assessed outside this runbook |

**A steady-state PASS is not a Gate 4 approval.** It closes the steady-state
half of Gate 4 criterion 4 only. A `startup=OPEN` line, or an open finding
from an earlier run, stays open until the operator resolves or
explicitly accepts it in the Gate 4 decision.

### The detector was proven both ways

All runs were local, in the same image under the same hardening
(`--read-only --user 100:101 --cap-drop ALL`), with TEST-NET addresses
standing in for the cluster ones, `WAIT_MAX=6` and `HOLD=1`:

| Run | Result |
|---|---|
| unfiltered network all along | `startup=OPEN`, `observed=no last=REACHABLE`, `result=FAIL`, exit 1: open egress is a FAIL |
| network removed during the run | `startup=OPEN`, `observed=yes`, then the steady checks: the two results are reported apart |
| `--network none` | `startup=CLOSED`, every TCP check `REFUSED`, `kube-dns-udp` `UNKNOWN`, `result=UNKNOWN`, exit 2. It also shows why an in-pod `REFUSED` needs node evidence |
| unrendered `__KUBE_API_CLUSTER_IP__` | `bad-target`, `result=UNKNOWN`, exit 2 |
| `WAIT_MAX=abc` | `bad-config`, `result=UNKNOWN`, exit 2 |

The single-phase manifest of run 1 was proven the same way before it ran,
including a real resolver answering (`kube-dns-udp` `REACHABLE`) and a
silently dropped DNS query (`BLOCKED`); those checks are unchanged.

## Procedure (after a separate GO)

1. Read-only lookups and preflight. The manifest commits no cluster
   addresses (this repository is public), so they are filled in at apply
   time:

   ```bash
   export KUBECONFIG=~/.kube/mctl-preview-config.yaml
   API=$(kubectl -n default get svc kubernetes -o jsonpath='{.spec.clusterIP}')
   DNS=$(kubectl -n kube-system get svc kube-dns -o jsonpath='{.spec.clusterIP}')
   BB=$(kubectl -n monitoring get svc blackbox-exporter -o jsonpath='{.spec.clusterIP}')
   RL=$(kubectl -n redloop get svc redloop-redloop-synthetic-staging-base-service -o jsonpath='{.spec.clusterIP}')
   : "${API:?}" "${DNS:?}" "${BB:?}" "${RL:?}"   # an empty lookup stops here
   for p in default:kubernetes monitoring:blackbox-exporter redloop:redloop-redloop-synthetic-staging-base-service; do
     n=$(kubectl -n "${p%%:*}" get endpointslices -l kubernetes.io/service-name="${p#*:}" \
           -o json | jq '[.items[].endpoints[]? | select(.conditions.ready != false)] | length')
     echo "$p ready=$n"   # every line must be ready>=1, or stop
   done
   render() {
     sed -e "s/__KUBE_API_CLUSTER_IP__/$API/" -e "s/__KUBE_DNS_CLUSTER_IP__/$DNS/" \
         -e "s/__BLACKBOX_CLUSTER_IP__/$BB/" -e "s/__REDLOOP_SVC_CLUSTER_IP__/$RL/" \
         docs/runbooks/redloop/egress-probe-pod.yaml
   }
   if render | grep -q '__'; then echo 'unrendered placeholder, stop'; else echo 'rendered OK'; fi
   render | kubectl apply --dry-run=server -f -
   ```

2. Apply and find the node:

   ```bash
   render | kubectl apply -f -
   kubectl -n redloop get networkpolicy -o yaml > netpol-$(date -u +%Y%m%dT%H%M%SZ).yaml
   kubectl -n redloop get pod redloop-egress-probe -o jsonpath='{.spec.nodeName} {.status.podIP}{"\n"}'
   ```

3. Follow the log: `kubectl -n redloop logs -f redloop-egress-probe`.

4. **Node evidence, read-only, during each hold.** When the log prints
   `probe hold=start` and again at `probe hold=end`, on the node from step 2
   (k3s ships the tools under its data directory; nothing here writes):

   ```bash
   X=/var/lib/rancher/k3s/data/current/bin/aux
   date -u +%FT%TZ
   $X/iptables-save -c -t filter | grep 'POD name:redloop-egress-probe namespace: redloop'
   ```

   Required, both times: a `KUBE-POD-FW-*` chain for the probe pod, jumped to
   from `KUBE-ROUTER-FORWARD` for its IP, whose last rules are the
   `rule to REJECT traffic destined for POD name:redloop-egress-probe` REJECT
   and the mark reset. Save both outputs with the log. If the chain name is
   the same in both snapshots, the REJECT packet counter must have grown by
   at least the number of steady `REFUSED` checks; kube-router rebuilds
   chains on its own, so a renamed chain makes the counter comparison
   inapplicable, not failed. A missing chain, or a chain without the REJECT,
   makes the run `UNKNOWN`.

5. Wait for the end, collect, clean up:

   ```bash
   # Bounded: a pod that is never scheduled has no startTime, so
   # activeDeadlineSeconds never fires. Give up after 6 minutes and treat it as UNKNOWN.
   for i in $(seq 1 72); do
     ph=$(kubectl -n redloop get pod redloop-egress-probe -o jsonpath='{.status.phase}')
     case "$ph" in Succeeded|Failed) break ;; esac; sleep 5
   done; echo "phase=$ph"   # anything but Succeeded/Failed: describe the pod, delete it, result UNKNOWN
   kubectl -n redloop logs redloop-egress-probe | tee redloop-egress-probe-$(date -u +%Y%m%dT%H%M%SZ).log
   kubectl -n redloop get events --field-selector involvedObject.name=redloop-egress-probe
   kubectl -n redloop delete pod redloop-egress-probe --wait=true
   kubectl -n redloop get pod redloop-egress-probe   # must say NotFound (non-zero exit is expected)
   ```

   Delete the pod even when a step above failed.

6. Classify with the table above and add a row to the run history.
   Publish only the log, the verdicts and the commit SHA of this file.
   Node rule dumps contain cluster addresses: keep them with the operator,
   not in this public repository.

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
node evidence, and the PR evidence should say so.
