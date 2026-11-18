# RedLoop Gate 4: Rules of Engagement

**Status: APPROVED for GO-1 only (origin path, 2026-11-18 02:00-03:00 UTC).**
The approval is recorded in the block at the end. It covers the origin-only
ZAP baseline in section 1 and nothing else: no public Ingress, no edge path,
no active scan and no WAF bypass. GO-1 still needs its own explicit
execution GO, and the GO checks in section 9 must hold at the start of the
window. Fields marked **DECIDED** record operator decisions of 2026-11-18.

The first DAST phase (GO-1) uses the **origin path only** (section 4): no
public Ingress, no DNS change and no Cloudflare change. The edge path is a
later, separate decision (GO-2).

These rules govern dynamic testing (DAST, a manual web test) of the RedLoop
synthetic staging fixture. They do not authorise a production pentest,
which is a separate gate.

## 1. Authorisation

| Field | Value |
|---|---|
| Authorising operator | Platform owner. Identity is recorded by the approval on the approval PR, not here |
| Authorisation reference | The approval PR that fills in this table (link added at signature) |
| Tester / scanner operator | **CONFIRMED:** the platform owner runs the scanner personally. A third-party tester needs a new approval |
| Operator contact during the window | **CONFIRMED:** operator Telegram (the same chat the RedLoop alerts reach) |
| Testing window | **CONFIRMED:** **2026-11-18 02:00 to 03:00 UTC**, one window. A green `redloop-waf-verify` run on `main` within the previous 24 h is required (run 44206456843, 2026-11-18 00:55 UTC). If the window is missed, a new one needs a new operator decision |
| Scanner source IP(s) | **Not applicable to GO-1:** the origin path runs over `kubectl port-forward` from the tester's machine. Required only for the edge path (GO-2) |
| Scanner and version | **CONFIRMED:** OWASP ZAP **2.17.0**, baseline scan (`zap-baseline.py`, spider plus passive rules, no active attacks), image `ghcr.io/zaproxy/zaproxy:2.17.0@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af` (multi-arch index, resolved 2026-11-18) |

**GO-1 command** (origin path; the tester's machine, during the window only):

```bash
#!/usr/bin/env bash
set -euo pipefail
umask 077
IMG=ghcr.io/zaproxy/zaproxy:2.17.0@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af
SVC=svc/redloop-redloop-synthetic-staging-base-service
DEP=deploy/redloop-redloop-synthetic-staging-base-service
OUT="$HOME/.local/share/mctl-forensics/redloop-go1-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p -m 0700 "$OUT"                # private: reports never leave this directory
START=$(date -u +%FT%TZ)

kubectl -n redloop port-forward "$SVC" 18080:80 >"$OUT/port-forward.log" 2>&1 &
PF=$!
cleanup() { kill "$PF" 2>/dev/null || true; wait "$PF" 2>/dev/null || true; chmod -R go-rwx "$OUT"; }
trap cleanup EXIT INT TERM             # the port-forward never outlives the script

# Fail closed: no 200 from /healthz within 20 s, or the port-forward died -> no scan.
ready=0
for _ in $(seq 1 20); do
  kill -0 "$PF" 2>/dev/null || break
  if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18080/healthz; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "ABORT: origin not ready; ZAP not started" >&2; exit 1; }

# Enforced budget: ZAP's own rate limiter, one rule matching every host, 4 req/s.
RL="-config network.ratelimit.rules.rule(0).description=redloop-budget"
RL+=" -config network.ratelimit.rules.rule(0).enabled=true"
RL+=" -config network.ratelimit.rules.rule(0).matchStr=.*"
RL+=" -config network.ratelimit.rules.rule(0).regex=true"
RL+=" -config network.ratelimit.rules.rule(0).reqsPerSec=4"
RL+=" -config network.ratelimit.rules.rule(0).groupBy=rule"

set +e
docker run --rm -v "$OUT:/zap/wrk" "$IMG" \
  zap-baseline.py -t http://host.docker.internal:18080/ -m 1 -T 10 -I \
    -r report.html -J report.json \
    -z "-config spider.thread=1 -config connection.timeoutInSecs=10 $RL" \
  >"$OUT/zap.log" 2>&1
ZAP_RC=$?
set -e

# Independent check of the budget, from the origin's own access log. kube-probe
# lines are excluded; everything else (scanner and blackbox probe) is counted,
# so the check can only over-count.
kubectl -n redloop logs "$DEP" --since-time="$START" | grep -v 'kube-probe/' >"$OUT/origin-access.log" || true
MAX=$(awk '{ if (match($0, /\[[^]]+\]/)) print substr($0, RSTART+1, 20) }' "$OUT/origin-access.log" \
      | sort | uniq -c | sort -rn | awk 'NR==1 { print $1 } END { if (NR==0) print 0 }')
echo "zap_rc=$ZAP_RC origin_requests=$(wc -l <"$OUT/origin-access.log") max_req_per_sec=$MAX" | tee "$OUT/budget.txt"
[ "$MAX" -le 5 ] || { echo "BUDGET EXCEEDED: stop condition, report to the operator" >&2; exit 3; }
exit "$ZAP_RC"
```

How the pieces were checked, offline and never against RedLoop (2026-11-18):

- **Flags** exist in `zap-baseline.py -h` of the pinned image (`--network none`).
- **Rate limit.** Tested locally against a throwaway nginx serving 300 links.
  - Without the rule, the spider peaked at **303 req/s**.
  - With the rule above (both `.*` regex and an exact host), the peak was **4 req/s** over about 67 s.
  - So the rule is what holds the 5 req/s budget in section 3. One spider thread alone does not.
- **Reaching the port-forward.** It listens on the tester's loopback only, so nothing is exposed beyond that machine.
  - On the tester's machine (Docker Desktop on macOS), `host.docker.internal` reaches that loopback (HTTP 200).
  - `--network host` does not (connection refused). On Linux, use `--network host` with target `http://127.0.0.1:18080/` instead, and make `$OUT` writable for uid 1000.
- **Private output.** A `0700` output directory is writable by the container on Docker Desktop. Files end up owned by the tester and are stripped of group and other access on exit.
- **Exit status.**
  - `-m 1` caps the spider at one minute, `-T 10` the whole run at ten.
  - `-I` stops warnings from failing the exit code, so judge the outcome from the report.
  - Exit `1` is a readiness abort, `3` is a budget breach, and anything else is ZAP's own status.
One spider thread against a fixture of four paths stays far below the
5 req/s budget in section 3. The baseline scan sends no attack payloads.
An active (full) scan is a separate approval.

A window that has not started or has already ended is not authorised.
Extending a window takes a new approval.

## 2. Scope

**In scope, and nothing else:**

- the host `staging-redloop.mctl.ai`, all paths, methods `GET`, `HEAD`,
  `POST` and `OPTIONS`;
- the same application via `kubectl port-forward` to the
  `redloop-redloop-synthetic-staging-base-service` Service in namespace
  `redloop` (the origin path, section 4).

The fixture is a static nginx (Chainguard, pinned by digest). It serves
`/`, `/healthz`, `/robots.txt` and `/static/`, and returns 404 for
everything else. It holds no data, no credentials and no users.

**Out of scope. Testing them is a violation, whatever the scanner does on
its own:**

- every other host in `mctl.ai`, `mctl.me` and `mctl.ru`, and the apex;
- Cloudflare itself: edge, dashboard, API and Access applications;
- the Kubernetes API, nodes, Traefik, Argo CD, Vault, monitoring and every
  other namespace;
- anything reached by following a redirect or link off the in-scope host.
  Configure the scanner to stay on the host;
- denial of service in any form: volumetric, slow-loris, resource
  exhaustion, or fuzzing at rates above section 3.

## 3. Rate limits

| Limit | Value | Enforced by |
|---|---|---|
| Scanner request rate | at most **5 req/s** sustained, single thread or equivalent | ZAP's rate-limit rule at 4 req/s in the GO-1 command (section 1), verified afterwards from the origin access log |
| Backstop per client | 10 req/s average, burst 20, **per Traefik replica** (3 today, HPA up to 10), answered with 429; keyed on `CF-Connecting-IP`, which an in-cluster client reaching Traefik directly can forge (Cloudflare overwrites it on proxied requests) | Traefik Middleware `redloop-staging-ratelimit` (renders only with the Ingress) |
| Concurrency | at most 2 connections | the tester |

The Traefik limit is a backstop, not the budget. A scanner that gets 429s
is above the RoE and must be slowed down, not retried harder. On the origin
path (port-forward) Traefik is not in the way, so the tester's own
configuration is the only limit, which is why the GO-1 command enforces it
in ZAP and checks it independently. Keep to 5 req/s there too: the pod has a
CPU request of 25m and a limit of 100m.

## 4. Test paths

**Origin path (preferred, no exposure).** Run the scanner against
`http://127.0.0.1:<port>` through
`kubectl -n redloop port-forward svc/redloop-redloop-synthetic-staging-base-service <port>:80`.
This tests the application and the nginx configuration. It requires no
Ingress, no DNS change and no Cloudflare exception, and nobody else's traffic
is involved. It cannot test the edge (WAF, TLS, headers added by Cloudflare).

**Edge path (only with the Ingress enabled, a separate decision).** Run the
scanner against `https://staging-redloop.mctl.ai`. Expect the Cloudflare
Managed Free Ruleset to block some payloads. Record those blocks as results
("the edge stops this"), not as obstacles. Whether to exempt the scanner
from them is section 8. It is off by default.

## 5. Stop conditions

Stop the scanner **at once**, before investigating, if any of these happen:

1. any alert fires: `RedLoopStagingDown`, `RedLoopStagingSlow` or
   `RedLoopStagingProbeAbsent` (operator Telegram);
2. any alert fires for a different service during the window, including
   `PublicEndpointDown`, until it is shown to be unrelated;
3. `RedLoopStagingProbeAbsent` is already firing at the start: the fixture
   is unwatched, so do not start at all;
4. the scanner leaves the in-scope host (check its request log);
5. the tester sees anything that looks like real data, a credential or
   another tenant's content. Stop, do not copy it, report it;
6. the operator contact asks for a stop, or cannot be reached at the start
   of the window;
7. the window ends.

## 6. Emergency shutdown

Apply in order and stop as soon as exposure has ended. This is the order
the owner set. The Alpine image is **not** a rollback target.

1. **Stop the scanner** (the tester).
2. **Cloudflare kill switch**: enable rule `block_staging_redloop_emergency`
   (`infrastructure/cloudflare/zones/mctl-ai/firewall.tf`, rule id
   `d8b4ea76eabc420e99146cafd9596801`). It blocks the host at the edge for
   everyone.
   - **Durable path:** PR setting `enabled = true`, then Cloudflare Apply.
     That is a manual dispatch with environment approval, so it takes minutes.
   - **Fast path:** toggle the rule directly, through the API as the
     Gate 3 drill did (measured RTO 5.65 s) or in the dashboard. This creates drift that the drift run reports.
     A PR must follow to bring Terraform in line or turn the rule back off.
     **DECIDED (2026-11-18):** the fast path is approved **for
     emergencies only**, by the operator, and must be followed by a
     Terraform reconciliation PR (enable the rule in code, or turn it back
     off) and a Cloudflare Apply. The drift run reports it until then.
3. **Ingress off**: revert the PR that set `ingress.enabled: true` and let
   Argo CD sync. The Middleware goes away with it.
4. **Scale to 0**: `replicaCount: 0` in the service values (PR).
   **DECIDED (2026-11-18): accepted as untested for this Gate 4 window.** It
   has not been drilled. The kill switch in step 2, proven in Gate 3, is the
   primary emergency control. On the origin path (GO-1) the first control is
   simpler still: stop the scanner and the port-forward.

The edge path is not open until step 2 has been proven. The Gate 3 drill
proved it on 2026-11-16 (run 43953107922).

## 7. Monitoring and evidence

**Before the window:**

- `probe_success{job="redloop-staging-healthz"}` exists and is 1. This is
  the VMProbe from the monitoring PR, so that PR must be merged first.
- Argo CD shows the redloop application `Synced` and `Healthy`.
- `redloop-waf-verify` (read-only) has passed on `main` within the last 24 h.
- Write down the image digest and the commit SHA of `main`.

**During the window:**

- The tester keeps the scanner's request log.
- The operator watches the RedLoop alerts and `PublicEndpointDown`.

**After the window:**

- Attach to the authorising PR or issue:
  - the scanner report (HTML or JSON);
  - the request log;
  - the start and end times in UTC;
  - the scanner IP;
  - any Cloudflare Security Events for the host in the window. This needs
    a token with Analytics Read, which is **not available today**: the gap
    is an open operator decision. Not applicable to GO-1, whose traffic
    never passes Cloudflare;
  - the alert history for the window.
- Findings go to an issue, never to this public repository's PR text in
  exploitable detail.

## 8. Proposal: scanner exception at the edge (DISABLED, not implemented)

Use this only if the edge path must run without the Managed Free Ruleset in
the way. It is a proposal; nothing in this PR changes Cloudflare.

- **DECIDED (2026-11-18): not approved.** No WAF bypass and no scanner
  exception. Nothing below is to be implemented for this Gate 4 window.
- **Constraint:** `mctl.ai` is on the Free plan. The custom-rules phase
  allows 5 rules and 4 are in use, so this would take the last slot.
- **Bot Fight Mode:** off for the zone (`fight_mode: false`, read
  2026-11-17), so there is no Bot Fight Mode block to skip. The
  `block_spoofed_crawlers` rule only matches clients that claim to be a
  known crawler. Do not configure the scanner with a crawler User-Agent.
- **Shape:**

  ```hcl
  {
    action = "skip"
    action_parameters = {
      phases = ["http_request_firewall_managed"]
    }
    description = "staging-redloop: DAST scanner exception (Gate 4 window only)"
    enabled     = false
    expression  = "(http.host eq \"staging-redloop.mctl.ai\" and ip.src eq 192.0.2.10)"
    logging     = { enabled = true }
    ref         = "skip_staging_redloop_dast"
  }
  ```

  `192.0.2.10` is a TEST-NET placeholder for the scanner IP, which is TBD.

- **Safety properties, all of which must hold in review:**
  - The expression requires **both** the host and the scanner `/32`.
    Traffic to any other host, or from any other IP, is unaffected.
  - It skips **only** the managed phase. It must **not** use
    `ruleset = "current"`, which would skip the remaining custom rules,
    including the kill switch, for the scanner.
  - The kill switch still wins: a `skip` that lists only `phases` does not
    stop evaluation of the custom ruleset, so `block_staging_redloop_emergency`
    is evaluated, and blocks, wherever the skip rule sits. The ban on
    `ruleset = "current"` above is what makes this true. Place it after the
    kill switch anyway, so the intent is visible.
  - It is committed with `enabled = false`. It is enabled for one window by
    PR and Cloudflare Apply, and disabled again by PR afterwards. A rule
    left enabled after its window is a finding.
  - Logging stays on, so the exempted requests remain visible.

Recommendation: run DAST on the origin path first. It needs none of this
and covers everything the fixture can actually get wrong. Take the edge path
and this exception only if the edge itself is the thing under test.

## 9. Gate 4 GO criteria

Gate 4 (public Ingress on, DAST allowed in a window) may be proposed when
all of the following hold:

1. This RoE is approved: every TBD field in sections 1, 6 and 8 is decided and
   signed off in a reviewed PR.
2. Monitoring is live. The VMProbe and the RedLoop alerts are merged and
   synced, `probe_success` reads 1, and the route to the operator Telegram
   is verified, for example with one test alert.
3. The rate limit is merged. The Middleware renders with the Ingress
   (proven by `helm template` with `ingress.enabled=true`).
4. The egress probe (`docs/runbooks/redloop-egress-probe.md`) has passed in
   the cluster, with evidence attached.
5. The kill switch is proven (Gate 3, done), and the fast-path decision in
   section 6 has been taken.
6. Scale to 0 has been drilled once, or explicitly accepted as untested.
7. `redloop-waf-verify` is green on `main` within 24 h of opening the
   Ingress.

## 10. Readiness against section 9 (2026-11-18)

| # | Criterion | State | Evidence |
|---|---|---|---|
| 1 | RoE approved | **met for GO-1**: section 1 confirmed, approval recorded below | this PR |
| 2 | Monitoring live, route verified | **met**: VMProbe and `redloop-alerts` live, `probe_success` 1 (and 1 for the past 24 h), three rules evaluating; one synthetic `RedLoop*` alert delivered to the operator Telegram and resolved | PR evidence comment |
| 3 | Rate limit renders with the Ingress | **met (render)**: `helm template` with `ingress.enabled=true` renders the Ingress and the `redloop-staging-ratelimit` Middleware, and the Ingress references it; with the default values neither renders | PR evidence comment |
| 4 | Egress probe passed | **met (steady state)**: run 2 PASS with node evidence; run 1 FAIL stays on record. A residual pod-startup risk is tracked privately and accepted only for this workload, until 2026-12-18 at the latest, subject to operator signature | #2769 |
| 5 | Kill switch proven, fast path decided | **met**: Gate 3 drill; fast path decided (section 6) | run 43953107922 |
| 6 | Scale to 0 drilled or accepted | **met (accepted as untested)** | section 6 |
| 7 | `redloop-waf-verify` green within 24 h | **met**: rule present, inert, contract matches; valid for a window starting before 2026-11-19 00:55 UTC | run 44206456843 |

For GO-1 (origin path) the Ingress stays disabled, so criterion 3 and the
edge controls are not exercised; they matter for GO-2.

## Approval

The operator's approval was given in writing in the operator session on
2026-11-18 ("RedLoop Gate 4 — Final Operator Authorization"). Claude Code
entered it here on that instruction. It is not a cryptographic signature, and
the agent did not approve anything on its own behalf.

| | |
|---|---|
| Approved by | The platform owner (operator), by written instruction in the operator session |
| Date (UTC) | 2026-11-18 |
| Approval PR | #2784 |
| Scope approved | GO-1 only: OWASP ZAP 2.17.0 baseline (pinned digest), origin path through `kubectl port-forward`, window 2026-11-18 02:00-03:00 UTC, tester the platform owner, contact operator Telegram, budget enforced at 4 req/s and checked against 5 req/s |
| Not approved | GO-2 (public Ingress, edge path), active or full scans, WAF bypass or scanner exception, production pentest |
| Related | The residual pod-startup risk for this workload only is accepted conditionally until 2026-12-18 at the latest. That record is held privately |
