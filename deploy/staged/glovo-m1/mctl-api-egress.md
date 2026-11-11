# mctl-api egress policy (staged, not applied)

Owner decision #7: prepare a default-deny / least-privilege outbound policy and
tests of the required connections; apply only through a separate verified
GitOps gate, before P2 activation. This file is inert documentation; the
manifest is `netpol/mctl-api-egress.yaml`, tested by
`scripts/test-mctl-api-egress-policy.py` (CI job `glovo-m1`).

## What it can and cannot do (read first)

- The cluster CNI (k3s flannel + kube-router) enforces `NetworkPolicy`
  egress; tenant namespaces already use default-deny plus `allow-*` policies.
  It has no FQDN policy and no flow logging, so there is **no audit mode**.
- A NetworkPolicy matches IPs, namespaces, pods and ports, never hostnames.
  The Glovo basket handler runs inside the same mctl-api process, so a rule
  "deny only Glovo" (Option A) **cannot be expressed**: the pods are the
  subject, and they already need public HTTPS for ZITADEL, GitHub, Cloudflare
  and others.
- Option B (this manifest) limits mctl-api to DNS, the Kubernetes API, listed
  in-cluster services and **public TCP 443**. It blocks: every other port to
  the internet, lateral movement to unlisted namespaces, private/link-local
  (cloud metadata) and CGNAT ranges. It does **not** block a Glovo host on
  443, so it is a containment layer, not a Glovo kill switch. The real Glovo
  kill switch stays the application flag (`GLOVO_ENABLED=false`) and the
  facade being a separate Deployment (P2).
- Option C (not staged): replace the 443 rule with an IP allow-list
  (Cloudflare ranges, GitHub `meta`, claude.ai, the ZITADEL host). The Glovo API
  sits on CloudFront, so it would be excluded, but the list goes stale
  silently and a miss breaks login or the GitOps path with no way to audit
  first. Pursue only after flow logging exists, and as its own decision.

## Destination inventory

Confidence: **H** = seen in code/config AND live Service, **M** = code or env
name only, **L** = inferred.

| Destination | Port | Evidence | Conf |
|---|---|---|---|
| kube-dns (kube-system) | 53 UDP/TCP | cluster DNS, every pod | H |
| Kubernetes API 10.255.0.101 | 6443 | live `kubernetes` endpoint, tenant templates | H |
| shared-pg-rw (platform-db) | 5432 | live Service; AUDIT/LIFECYCLE DB URLs | H |
| valkey (platform-events) | 6379 | `EVENTS_VALKEY_URL`, live Service | H |
| temporal-frontend (temporal) | 7233 | `TEMPORAL_ADDRESS`, live Service | H |
| vault-active (vault) | 8200 | `VAULT_ADDR`, live Service | H |
| loki-stack (monitoring) | 3100 | `LOKI_URL`, live Service | H |
| argo-workflows-server | 2746 | workflow operations, live Service | M |
| backstage | 7007 | live Service, portal calls | M |
| erpact-deployer | 8000 | erpact tools, live Service | M |
| zitadel / zitadel-login | 8080 / 3000 | OIDC, live Services; may go via public host instead | M |
| public HTTPS (auth, GitHub, Cloudflare R2, claude.ai) | 443 | `DEX_ISSUER_URL`, `ARGO_LOGS_R2_ENDPOINT`, `OAUTH_CIMD_ALLOWED_HOSTS`, issuer host | M |
| other DB URLs (`*_DB_URL` via envFrom Secret) | 5432 | host unreadable by rule (Secret .data) | **L** |
| gitops SSH (`GITOPS_SSH_KNOWN_HOSTS_PATH`) | 22 | optional; NOT allowed here | **L** |

## Unknowns that must be closed at the gate, before enforcing

1. Hosts behind Secret-delivered DB URLs. If any is not `shared-pg-rw`, the
   canary will fail Postgres calls. Closed by the canary check below.
2. Whether ZITADEL is reached in-cluster or through the public host (both are
   allowed, so this only affects the breakage explanation).
3. Whether gitops-over-SSH (port 22) is used in prod. If yes add a rule for the
   exact GitHub ranges, or accept breakage on that path.
4. Node public IPs: add them as `/32` `except` entries in the 443 rule. Not
   recorded in this public repository; read them at the gate.
5. How kube-router evaluates the ClusterIP for the API server rule (pre- or
   post-DNAT); the tenant templates use `10.255.0.0/24:6443`, so widen to that if
   the `/32` fails in the canary.
6. Chart label support: `mctl-api/helm` has no `podLabels`, so only a manual
   `kubectl label pod` canary works today; promotion to every replica needs a
   chart change or dropping the label from `podSelector`.

## Rollout (at the gate, never from this PR)

1. Apply the policy. It selects nothing yet, so nothing changes.
2. Label ONE replica: `kubectl -n mctl-api label pod <pod> mctl.ai/egress-policy=enforced`.
   The label is lost when the pod restarts, which makes the canary self-healing.
3. Run the verification below against that pod.
4. If green for an agreed soak, promote in a separate PR (drop the extra label
   from `podSelector` or add it through the chart) and re-run the verification.

**Rollback**, fastest first: `kubectl -n mctl-api label pod <pod> mctl.ai/egress-policy-`
(remove label), delete the pod, or delete the policy. NetworkPolicies are
additive and the allow-ingress policy is untouched, so nothing else changes.

## Verification procedure (no production writes)

Everything is read-only or an outbound connect that sends no data.

1. Before: `kubectl -n mctl-api get pods -l app.kubernetes.io/name=mctl-api` shows
   2/2 Ready; record `GET /healthz` and `/readyz` responses.
2. After labelling one pod, from that pod's network namespace (use
   `kubectl debug` with an ephemeral container, no Secret access):
   - allowed: TCP connect to each row marked H/M above (`nc -zv host port`);
     DNS resolves a cluster name and a public name.
   - denied (must time out): TCP 22 and 25 to a public address, TCP 80 to a
     public address, `169.254.169.254:80`, a private address outside the list.
   - **expected NOT to fail**: a connect to the Glovo host on 443. Record it as
     the known limit rather than a defect.
3. `GET /readyz` on the labelled pod stays 200 and a read-only MCP call
   (for example `mctl_whoami`) succeeds through it; the pod log shows no new
   `dial tcp ... i/o timeout` against the allowed destinations.
4. Watch the labelled pod for the agreed soak, comparing error rate with the
   unlabelled replica. Any breakage in an allowed class is a P1 for the gate:
   remove the label and amend the manifest.
5. Re-run `scripts/test-mctl-api-egress-policy.py` at the gate head and require
   green; the test proves the manifest, steps 2-4 prove the cluster.
