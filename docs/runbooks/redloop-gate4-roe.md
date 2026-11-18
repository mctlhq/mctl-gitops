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

## 11. GO-1b: repeat origin baseline with seeded coverage

**Status: APPROVED for GO-1b on merge of this section.** The operator decided
in writing on 2026-11-18 ("RedLoop Gate 4 GO-1b — Operator Decisions"). Claude
Code entered that decision here; it is not a cryptographic signature.
**Running the scan needs a separate operator EXECUTE GO.** Merging this
section authorises nothing by itself.

**Why.** GO-1 (2026-11-18 02:00 UTC, #2769) reached only the linked pages,
because the spider follows links, so `/healthz` and `/static/` were never
passively scanned. #2796 then hardened the response headers. GO-1b checks
that hardening on every fixture path.

| Field | Value |
|---|---|
| Scope | Origin only, through `kubectl port-forward`, exactly as GO-1. No Ingress, no edge, no Cloudflare change |
| Scanner | OWASP ZAP **2.17.0**, `zap-baseline.py`: passive rules only, the same rule set as GO-1, the pinned digest from section 1 |
| Coverage | A seed hook requests `/`, `/robots.txt`, `/healthz`, `/static/app.js` and a 404 path (`/does-not-exist`) before the spider runs, then records ZAP's site tree |
| Request budget | Same as GO-1: ZAP's rate-limit rule at 4 req/s, checked afterwards against 5 req/s in the origin's access log (section 3) |
| Tester / contact | **CONFIRMED:** the platform owner; operator Telegram |
| Testing window | **CONFIRMED: 2026-11-18 13:00 to 14:00 UTC**, one window. If it is missed, a new window needs a new operator decision |
| WAF verification | Kept for consistency with GO-1, although the origin path does not cross the WAF: a green `redloop-waf-verify` run on `main` within the previous 24 h is required |
| Preconditions | #2796 merged and rolled out; image digest unchanged; response headers verified; Argo CD Synced/Healthy; `ingress.enabled: false`; `probe_success` = 1; no RedLoop alerts; no unexpected restarts; renewed risk acceptance in force; section 9 checks hold at window start |
| Stop conditions | Section 5, plus the window end |
| Reports | Private, as in GO-1 (`0700` directory), including the raw origin log; only a sanitized summary goes public |

**Result rules.** The script decides the result itself. A zero ZAP exit code
alone is never PASS. FAIL outranks INCONCLUSIVE, which outranks PASS.

| Check | Required for PASS | Otherwise |
|---|---|---|
| Seeded control | ZAP rule **10038** (CSP not set) reported on `/`, which proves the scanner detects the seeded gap | INCONCLUSIVE |
| Accepted findings | **90004** (COEP / COOP / CORP) and **10049** (storable content) may appear; they are optional | - |
| Any other finding | none | FAIL, for operator review |
| Seed coverage | All five seed paths are in ZAP's recorded site tree **and** in the origin access log | INCONCLUSIVE |
| Rate evidence | The origin access log was fetched and shows the scan's requests, at most 5 per second | Fetch failed or log empty: INCONCLUSIVE. Over 5 req/s: FAIL (stop condition) |
| Report | `report.json` is present and parses; ZAP exited 0 | INCONCLUSIVE |

A failed `kubectl logs` fetch is recorded, never suppressed, and missing logs
never count as zero requests. Exit codes: 0 PASS, 4 FAIL, 5 INCONCLUSIVE.

**Risk acceptance.** The RedLoop-only acceptance of the residual pod-startup
risk, tracked privately, is renewed for:
- the configuration merged in #2796 (merge `b495ca329`, identified by its rendered config checksum);
- the GO-1b window.

It expires on 2026-12-18 at the latest, and every earlier invalidation
condition still applies. It covers no other workload. GO-2 needs a separate
risk review.

**Rehearsal (local only, never against RedLoop, 2026-11-18).** The script
above was run end to end on the tester's machine. A stub `kubectl` served the
pinned nginx image on loopback.

| Scenario | Verdict (exit) |
|---|---|
| #2796 configuration | **PASS** (0): 5/5 seed paths, 11 requests, peak 3 req/s, findings 10038, 90004, 10049 |
| Pre-#2796 configuration | **FAIL** (4): unexpected 10020, 10021, 10036, 10063 |
| Origin log fetch fails | **INCONCLUSIVE** (5): fetch failure, no rate evidence, seed paths unconfirmed |
| CSP added, so the seeded gap is gone | **FAIL** (4): unexpected 10055; 10038 missing is also reported |

The validator was also checked on its own against a report without 10038, a
site tree without `/healthz`, a missing URL list and a malformed report. Each
gave INCONCLUSIVE. In every scenario the report directory was `0700` and no
container was left running.

**GO-1b command** (the tester's machine, during the window only):

```bash
#!/usr/bin/env bash
set -euo pipefail
umask 077
IMG=ghcr.io/zaproxy/zaproxy:2.17.0@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af
SVC=svc/redloop-redloop-synthetic-staging-base-service
DEP=deploy/redloop-redloop-synthetic-staging-base-service
OUT="$HOME/.local/share/mctl-forensics/redloop-go1b-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p -m 0700 "$OUT"                # private: reports never leave this directory
START=$(date -u +%FT%TZ)

# Seed hook: request fixed paths before the spider, so that paths without an
# inbound link are passively scanned too. The requests go through ZAP, so the
# rate-limit rule below applies to them.
cat >"$OUT/seed_hook.py" <<'HOOK'
SEEDS = ["", "robots.txt", "healthz", "static/app.js", "does-not-exist"]

def zap_started(zap, target):
    base = target.rstrip("/") + "/"
    for path in SEEDS:
        zap.core.access_url(url=base + path, followredirects=False)

def zap_pre_shutdown(zap):
    # Evidence of what ZAP actually requested and passively scanned.
    with open("/zap/wrk/zap-urls.txt", "w") as f:
        f.write("\n".join(zap.core.urls()) + "\n")
HOOK

# Result validator: seed coverage and finding classification (run after ZAP).
cat >"$OUT/validate.py" <<'PY'
import json, re, sys

report, urls, access = sys.argv[1:4]
BASE = "http://host.docker.internal:18080"
SEEDS = ["/", "/robots.txt", "/healthz", "/static/app.js", "/does-not-exist"]
REQUIRED = {"10038": "/"}      # seeded CSP gap: positive scanner-detection control
OPTIONAL = {"90004", "10049"}  # accepted as not applicable, may or may not appear
lines = []

def path_of(uri):
    if not uri.startswith(BASE):
        return uri
    return uri[len(BASE):] or "/"

try:
    sites = json.load(open(report))["site"]
except Exception as e:
    sites = None
    lines.append(f"INCONCLUSIVE: report.json unreadable ({type(e).__name__})")
try:
    zap_paths = {path_of(u.strip()) for u in open(urls) if u.strip()}
except OSError:
    zap_paths = None
    lines.append("INCONCLUSIVE: ZAP URL list missing")
try:
    log = open(access).read()
except OSError:
    log = None
    lines.append("INCONCLUSIVE: origin access log missing")

for p in SEEDS:
    if zap_paths is not None and p not in zap_paths:
        lines.append(f"INCONCLUSIVE: seed path {p} not in ZAP's site tree")
    if log is not None and not re.search(r'"GET ' + re.escape(p) + r' HTTP/', log):
        lines.append(f"INCONCLUSIVE: seed path {p} not in the origin access log")

if sites is not None:
    found = {}
    for site in sites:
        for a in site.get("alerts", []):
            entry = found.setdefault(a["pluginid"], [a.get("name", ""), set()])
            entry[1].update(path_of(i.get("uri", "")) for i in a.get("instances", []))
    for pid, (name, paths) in sorted(found.items()):
        where = " ".join(sorted(paths))
        if pid in REQUIRED or pid in OPTIONAL:
            lines.append(f"OK: {pid} {name} on {where}")
        else:
            lines.append(f"FAIL: unexpected finding {pid} {name} on {where}")
    for pid, path in REQUIRED.items():
        if path not in found.get(pid, ["", set()])[1]:
            lines.append(f"INCONCLUSIVE: seeded control {pid} not reported on {path}")

print("\n".join(lines))
PY

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
    --hook=/zap/wrk/seed_hook.py \
    -r report.html -J report.json \
    -z "-config spider.thread=1 -config connection.timeoutInSecs=10 $RL" \
  >"$OUT/zap.log" 2>&1
ZAP_RC=$?
set -e

# --- Evaluation. Fail closed: the ZAP exit code alone is never PASS, and
# missing evidence is INCONCLUSIVE, never "zero requests" or "no findings".
CHK="$OUT/checks.txt"; : >"$CHK"
[ "$ZAP_RC" = 0 ] || echo "INCONCLUSIVE: ZAP exit code $ZAP_RC" >>"$CHK"

# Independent request-rate evidence from the origin's own access log. The raw
# fetch is kept as is; a failed fetch is recorded, never suppressed.
if ! kubectl -n redloop logs "$DEP" --since-time="$START" >"$OUT/origin-raw.log" 2>"$OUT/origin-logs.err"; then
  echo "INCONCLUSIVE: origin access log could not be fetched" >>"$CHK"
fi
# kube-probe lines are excluded; everything else (scanner and blackbox probe)
# is counted, so the rate check can only over-count. grep exits 1 when no line
# is left; emptiness is checked explicitly below.
grep -v 'kube-probe/' "$OUT/origin-raw.log" >"$OUT/origin-access.log" || true
N=$(wc -l <"$OUT/origin-access.log" | tr -d ' ')
MAX=$(awk '{ if (match($0, /\[[^]]+\]/)) print substr($0, RSTART+1, 20) }' "$OUT/origin-access.log" \
      | sort | uniq -c | sort -rn | awk 'NR==1 { print $1 }')
if [ "$N" = 0 ] || [ -z "$MAX" ]; then
  echo "INCONCLUSIVE: no request-rate evidence in the origin access log" >>"$CHK"; MAX=unknown
elif [ "$MAX" -gt 5 ]; then
  echo "FAIL: budget exceeded, max $MAX req/s (stop condition, report to the operator)" >>"$CHK"
fi

python3 -I "$OUT/validate.py" "$OUT/report.json" "$OUT/zap-urls.txt" "$OUT/origin-access.log" >>"$CHK" 2>&1 \
  || echo "INCONCLUSIVE: report validator failed" >>"$CHK"

if grep -q '^FAIL:' "$CHK"; then V=FAIL; elif grep -q '^INCONCLUSIVE:' "$CHK"; then V=INCONCLUSIVE; else V=PASS; fi
echo "verdict=$V zap_rc=$ZAP_RC origin_requests=$N max_req_per_sec=$MAX" | tee "$OUT/verdict.txt"
cat "$CHK"
case "$V" in PASS) exit 0 ;; FAIL) exit 4 ;; *) exit 5 ;; esac
```

## 12. GO-2: controlled public exposure and passive edge baseline (PROPOSED)

**Status: PROPOSED, not approved.** Nothing in this section is authorised
until the operator approves it in this PR and then gives a separate GO-2
EXECUTE decision. Active DAST and the production pentest stay out of scope.

**Why.** GO-1 and GO-1b tested the application through the origin path. They
cannot see the edge: Cloudflare TLS, the HTTP-to-HTTPS redirect, the missing
HSTS header (a seeded gap) and the per-client Traefik limit. GO-2 opens the
Ingress for one short window, runs one passive baseline through the edge,
and closes the Ingress again.

### Exposure window and timeline

| Field | Value |
|---|---|
| Exposure window | **PROPOSED: operator to set.** At most **2 hours**, from the moment the Ingress PR (`#2799`) is enqueued to the moment its revert is synced. Suggested: one weekday morning, 10:00-12:00 UTC |
| Scan window | Inside the exposure window. The scan starts no later than 45 minutes before the window ends |
| Tester / contact | **PROPOSED:** the platform owner; operator Telegram |
| Scanner IP | The tester's egress IP, recorded privately before the scan, never in this repository |

| Step | When | Who | Done when |
|---|---|---|---|
| 1. `redloop-waf-verify` | within 24 h before step 2 | operator dispatch (read-only) | green on `main` |
| 2. Enqueue `#2799` (Ingress on) | window start | tester | merged through the merge queue |
| 3. Edge preflight | after Argo CD sync | tester | the checks below pass |
| 4. Passive edge baseline | after step 3, before window end minus 45 min | tester | the script below finishes |
| 5. Enqueue the revert of `#2799` | right after step 4, and no later than window end minus 30 min | tester | revert merged, Argo CD synced, Ingress gone |
| 6. Close-out | after step 5 | tester | the checks below pass |

The merge queue takes 10-20 minutes per PR (observed 2026-11-18). That is
why step 5 starts 30 minutes before the window ends. If the revert is not
synced when the window ends, the kill switch fast path (section 6) applies.

### Preconditions (all must hold at step 2)

1. GO-1b is PASS, with its evidence on file.
2. This section is approved and merged.
3. The public exposure risk review is accepted separately by the operator. It covers a public static fixture on the shared Traefik, and the pod-startup window if the pod restarts while it is exposed. The earlier acceptance covers the origin windows only.
4. `redloop-waf-verify` is green within 24 h; the kill switch rule is present and disabled.
5. The image digest and config checksum are unchanged from #2796. `probe_success` = 1, no RedLoop alerts, no unexpected restarts, Argo CD Synced/Healthy.
6. The operator has decided the Security Events gap (below).

### Edge preflight (step 3, a handful of requests)

- The Certificate `redloop-synthetic-staging-tls` is `Ready`, issued by `letsencrypt-prod`.
- `https://staging-redloop.mctl.ai/healthz` returns 200 through Cloudflare.
- Both `redloop-staging-healthz` targets read `probe_success` = 1: in-cluster and edge.
- No other host has changed: the Ingress names only `staging-redloop.mctl.ai`.

### Stop conditions

Section 5 applies in full. In addition, stop at once and close the exposure
(step 5, or the kill switch if it is urgent) if any of these happen:

1. the edge target of `redloop-staging-healthz` fails, or the edge answers with 5xx (for example 526, an origin certificate error);
2. more than 5 req/s show in the origin access log, whatever the source;
3. any Traefik or `PublicEndpointDown` alert fires for another host;
4. the scanner requests anything outside `staging-redloop.mctl.ai`;
5. the exposure window would run past its end.

### Passive edge baseline (step 4)

This is the GO-1b script with three changes:
- the target is `https://staging-redloop.mctl.ai/` instead of a port-forward;
- four TLS and HTTPS requests are made and recorded before the scan;
- **HSTS (ZAP 10035) on `/` is a second required control**, next to CSP (10038).

Only passive rules run: there is no active scan, no fuzzing and no WAF
bypass (section 8 stays not approved).

| Check | Required for PASS | Otherwise |
|---|---|---|
| Seeded controls | 10038 (CSP) **and** 10035 (HSTS) reported on `/` | INCONCLUSIVE |
| Accepted findings | 90004 and 10049, both optional | - |
| Any other finding | none. A header that Cloudflare adds or changes counts too, until the operator has classified it | FAIL, for review |
| HTTPS | `http://` redirects to `https://` (Always Use HTTPS); the edge certificate verifies; TLS 1.1 is refused (minimum TLS 1.2) | FAIL; an unverified certificate is INCONCLUSIVE |
| HSTS at the edge | absent, as seeded: Cloudflare does not add it, because the zone sets no HSTS | present: INCONCLUSIVE |
| Coverage | all five seed paths in ZAP's site tree and in the origin access log | INCONCLUSIVE |
| Rate | origin access log fetched, at most 5 req/s | missing: INCONCLUSIVE; over 5: FAIL |

**Not yet rehearsed.** Before this section is approved, the script must run
end to end against a local TLS fixture, as GO-1b's did, and the result must
be attached to this PR.

```bash
#!/usr/bin/env bash
set -euo pipefail
umask 077
IMG=ghcr.io/zaproxy/zaproxy:2.17.0@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af
HOST=staging-redloop.mctl.ai
URL="https://$HOST"
DEP=deploy/redloop-redloop-synthetic-staging-base-service
OUT="$HOME/.local/share/mctl-forensics/redloop-go2-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p -m 0700 "$OUT"                # private: reports never leave this directory
START=$(date -u +%FT%TZ)

# Seed hook: request fixed paths before the spider, so that paths without an
# inbound link are passively scanned too. The requests go through ZAP, so the
# rate-limit rule below applies to them.
cat >"$OUT/seed_hook.py" <<'HOOK'
SEEDS = ["", "robots.txt", "healthz", "static/app.js", "does-not-exist"]

def zap_started(zap, target):
    base = target.rstrip("/") + "/"
    for path in SEEDS:
        zap.core.access_url(url=base + path, followredirects=False)

def zap_pre_shutdown(zap):
    # Evidence of what ZAP actually requested and passively scanned.
    with open("/zap/wrk/zap-urls.txt", "w") as f:
        f.write("\n".join(zap.core.urls()) + "\n")
HOOK

# Result validator: seed coverage and finding classification (run after ZAP).
cat >"$OUT/validate.py" <<'PY'
import json, re, sys

report, urls, access = sys.argv[1:4]
BASE = "https://staging-redloop.mctl.ai"
SEEDS = ["/", "/robots.txt", "/healthz", "/static/app.js", "/does-not-exist"]
REQUIRED = {"10038": "/", "10035": "/"}  # seeded CSP and HSTS gaps: positive detection controls
OPTIONAL = {"90004", "10049"}  # accepted as not applicable, may or may not appear
lines = []

def path_of(uri):
    if not uri.startswith(BASE):
        return uri
    return uri[len(BASE):] or "/"

try:
    sites = json.load(open(report))["site"]
except Exception as e:
    sites = None
    lines.append(f"INCONCLUSIVE: report.json unreadable ({type(e).__name__})")
try:
    zap_paths = {path_of(u.strip()) for u in open(urls) if u.strip()}
except OSError:
    zap_paths = None
    lines.append("INCONCLUSIVE: ZAP URL list missing")
try:
    log = open(access).read()
except OSError:
    log = None
    lines.append("INCONCLUSIVE: origin access log missing")

for p in SEEDS:
    if zap_paths is not None and p not in zap_paths:
        lines.append(f"INCONCLUSIVE: seed path {p} not in ZAP's site tree")
    if log is not None and not re.search(r'"GET ' + re.escape(p) + r' HTTP/', log):
        lines.append(f"INCONCLUSIVE: seed path {p} not in the origin access log")

if sites is not None:
    found = {}
    for site in sites:
        for a in site.get("alerts", []):
            entry = found.setdefault(a["pluginid"], [a.get("name", ""), set()])
            entry[1].update(path_of(i.get("uri", "")) for i in a.get("instances", []))
    for pid, (name, paths) in sorted(found.items()):
        where = " ".join(sorted(paths))
        if pid in REQUIRED or pid in OPTIONAL:
            lines.append(f"OK: {pid} {name} on {where}")
        else:
            lines.append(f"FAIL: unexpected finding {pid} {name} on {where}")
    for pid, path in REQUIRED.items():
        if path not in found.get(pid, ["", set()])[1]:
            lines.append(f"INCONCLUSIVE: seeded control {pid} not reported on {path}")

print("\n".join(lines))
PY

cleanup() { chmod -R go-rwx "$OUT" || true; }
trap cleanup EXIT INT TERM

# Fail closed: the edge must answer /healthz with 200 within 20 s -> else no scan.
ready=0
for _ in $(seq 1 20); do
  if curl -fsS -o /dev/null --max-time 5 "$URL/healthz"; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "ABORT: edge not ready; ZAP not started" >&2; exit 1; }

# Edge TLS and HTTPS checks: four requests, recorded privately.
{
  echo "http_redirect=$(curl -sS -o /dev/null --max-time 5 -w '%{http_code} %{redirect_url}' "http://$HOST/")"
  echo "tls_negotiated=$(curl -sS -o /dev/null --max-time 5 -w '%{ssl_verify_result} %{http_version}' "$URL/healthz")"
  if curl -sS -o /dev/null --max-time 5 --tls-max 1.1 "$URL/healthz" 2>/dev/null; then echo "tls11=accepted"; else echo "tls11=refused"; fi
  echo "hsts_header=$(curl -sS -o /dev/null -D - --max-time 5 "$URL/" | tr -d '\r' | grep -ci '^strict-transport-security:')"
} >"$OUT/tls.txt" 2>&1
cat "$OUT/tls.txt"

# Enforced budget: ZAP's own rate limiter, one rule matching every host, 4 req/s.
RL="-config network.ratelimit.rules.rule(0).description=redloop-budget"
RL+=" -config network.ratelimit.rules.rule(0).enabled=true"
RL+=" -config network.ratelimit.rules.rule(0).matchStr=.*"
RL+=" -config network.ratelimit.rules.rule(0).regex=true"
RL+=" -config network.ratelimit.rules.rule(0).reqsPerSec=4"
RL+=" -config network.ratelimit.rules.rule(0).groupBy=rule"

set +e
docker run --rm -v "$OUT:/zap/wrk" "$IMG" \
  zap-baseline.py -t "$URL/" -m 1 -T 10 -I \
    --hook=/zap/wrk/seed_hook.py \
    -r report.html -J report.json \
    -z "-config spider.thread=1 -config connection.timeoutInSecs=10 $RL" \
  >"$OUT/zap.log" 2>&1
ZAP_RC=$?
set -e

# --- Evaluation. Fail closed: the ZAP exit code alone is never PASS, and
# missing evidence is INCONCLUSIVE, never "zero requests" or "no findings".
CHK="$OUT/checks.txt"; : >"$CHK"
[ "$ZAP_RC" = 0 ] || echo "INCONCLUSIVE: ZAP exit code $ZAP_RC" >>"$CHK"

# Independent request-rate evidence from the origin's own access log. The raw
# fetch is kept as is; a failed fetch is recorded, never suppressed.
if ! kubectl -n redloop logs "$DEP" --since-time="$START" >"$OUT/origin-raw.log" 2>"$OUT/origin-logs.err"; then
  echo "INCONCLUSIVE: origin access log could not be fetched" >>"$CHK"
fi
# kube-probe lines are excluded; everything else (scanner, blackbox probe and
# any other internet client) is counted, so the rate check can only over-count.
# Over 5 req/s is FAIL until the operator has reviewed the source of the excess. grep exits 1 when no line
# is left; emptiness is checked explicitly below.
grep -v 'kube-probe/' "$OUT/origin-raw.log" >"$OUT/origin-access.log" || true
N=$(wc -l <"$OUT/origin-access.log" | tr -d ' ')
MAX=$(awk '{ if (match($0, /\[[^]]+\]/)) print substr($0, RSTART+1, 20) }' "$OUT/origin-access.log" \
      | sort | uniq -c | sort -rn | awk 'NR==1 { print $1 }')
if [ "$N" = 0 ] || [ -z "$MAX" ]; then
  echo "INCONCLUSIVE: no request-rate evidence in the origin access log" >>"$CHK"; MAX=unknown
elif [ "$MAX" -gt 5 ]; then
  echo "FAIL: budget exceeded, max $MAX req/s (stop condition, report to the operator)" >>"$CHK"
fi

grep -q '^http_redirect=30[178] https://staging-redloop.mctl.ai/' "$OUT/tls.txt" || echo "FAIL: http:// is not redirected to https://" >>"$CHK"
grep -q '^tls_negotiated=0 ' "$OUT/tls.txt" || echo "INCONCLUSIVE: edge certificate not verified" >>"$CHK"
grep -q '^tls11=refused' "$OUT/tls.txt" || echo "FAIL: edge accepts TLS 1.1" >>"$CHK"
grep -q '^hsts_header=0' "$OUT/tls.txt" || echo "INCONCLUSIVE: HSTS present at the edge, so the seeded gap cannot be detected" >>"$CHK"

python3 -I "$OUT/validate.py" "$OUT/report.json" "$OUT/zap-urls.txt" "$OUT/origin-access.log" >>"$CHK" 2>&1 \
  || echo "INCONCLUSIVE: report validator failed" >>"$CHK"

if grep -q '^FAIL:' "$CHK"; then V=FAIL; elif grep -q '^INCONCLUSIVE:' "$CHK"; then V=INCONCLUSIVE; else V=PASS; fi
echo "verdict=$V zap_rc=$ZAP_RC origin_requests=$N max_req_per_sec=$MAX" | tee "$OUT/verdict.txt"
cat "$CHK"
case "$V" in PASS) exit 0 ;; FAIL) exit 4 ;; *) exit 5 ;; esac
```

### Close-out (step 6)

- The Ingress and the Middleware are gone; `https://staging-redloop.mctl.ai/`
  is back to Traefik's 404.
- The edge probe target is removed together with the Ingress, and the
  in-cluster target reads 1.
- No RedLoop alerts. The pod has had no restarts and its digest is unchanged.
- The kill switch rule is still disabled, and no Cloudflare drift is left.
- A sanitized summary goes to #2769. The report, the request log, the scanner
  IP, the times and the alert history stay private.

### Cloudflare Security Events: a visibility gap to decide

The Cloudflare token has no Analytics Read, so edge blocks and challenges in
the window cannot be read afterwards. One of these is needed before GO-2:
- **(a)** the operator provides a read-only Analytics token for the window;
- **(b)** the operator accepts that edge events are not visible. The scan
  report still shows 403 answers, but not which rule produced them.

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
| GO-1b | Approved in section 11 by the operator's written decision of 2026-11-18 ("RedLoop Gate 4 GO-1b — Operator Decisions"): origin only, window 2026-11-18 13:00-14:00 UTC. Running it needs a separate EXECUTE GO |
| Not approved | GO-2 (public Ingress, edge path), active or full scans, WAF bypass or scanner exception, production pentest |
| Related | The residual pod-startup risk for this workload only is accepted conditionally until 2026-12-18 at the latest. That record is held privately |
