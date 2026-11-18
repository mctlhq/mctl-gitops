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
EXECUTE decision. Active DAST, WAF bypass and the production pentest stay out
of scope.

**Why.** GO-1 and GO-1b tested the application through the origin path. They
cannot see the edge: Cloudflare TLS, the HTTP-to-HTTPS redirect, the missing
HSTS header (a seeded gap) and the Traefik route. GO-2 opens the Ingress for
one short window, runs one passive baseline through the edge, and closes the
Ingress again.

### Window and absolute deadline

| Field | Value |
|---|---|
| Approved period | **PROPOSED: operator to set** `P` (start) and the **absolute deadline `D` (UTC)**, with `D - P` at most **60 minutes** |
| Exposure | starts when the Ingress PR (#2799) is synced, never before `P`; must end by `D` |
| Scan | the script refuses to start later than `D - 35 min` and stops itself at `D - 25 min` |
| Tester / contact | **PROPOSED:** the platform owner; operator Telegram |
| Scanner IP | the tester's egress IP, recorded privately, never in this repository |

The merge queue took 10-20 minutes per PR on 2026-11-18. That is an
observation, not a guarantee. If #2799 has not synced by `P + 25 min`, the
scan cannot start, and the window closes without a scan (step 5).

### Timeline

| Step | Latest time | Done when |
|---|---|---|
| 1. `redloop-waf-verify` dispatched (read-only); GO-1b PASS on file; preconditions below hold | before `P` | green run within 24 h of step 2 |
| 2. Enqueue #2799 | at `P`, not before | merged with a merge commit |
| 3. Prepare the revert PR at once: `git revert -m 1 <merge sha>`, pushed and opened, CI running | right after step 2 | PR open |
| 4. Edge preflight (below) | after Argo CD sync | all checks pass, else go to step 6 |
| 5. Passive edge baseline (script below) | start by `D - 35 min` | script exits; it stops itself at `D - 25 min` |
| 6. Enqueue the revert | right after step 5, **at the latest `D - 25 min`** | enqueued |
| 7. Verify closure | before `D - 5 min` | all closure checks below pass |
| 8. Fallback: Cloudflare kill switch | **at `D - 5 min` if step 7 has not passed** | the edge answers 403 for the host |
| 9. Close-out | after step 7 (or 8) | all close-out checks below pass |
| 10. Edge cache expiry check | at `D + 125 min` | no seed path returns the fixture from the edge (below) |

**Closure means verified, not enqueued.** Enqueueing the revert is not
closure. Closure needs **all** of:
- the revert merged and Argo CD `Synced`/`Healthy` on that revision;
- no Ingress and no Middleware in namespace `redloop` (read-only `kubectl get`);
- `https://staging-redloop.mctl.ai/healthz` no longer answering 200 from the
  fixture (Traefik's 404, or 403 if the kill switch is on).

**The edge cache outlives the Ingress.** The zone uses Cloudflare's default
caching (cache level standard, no cache rule for this host), and the fixture
sends no `Cache-Control`. Cloudflare therefore caches `/static/app.js` and
`/robots.txt` for up to 120 minutes after a 200 response, and 404 for 3
minutes. Removing the Ingress does not evict them. Every copy was filled while
the origin was reachable, that is no later than closure, so none can be served
after `D + 120 min`. Step 10 checks this. No purge is planned: it would be a
Cloudflare change outside this approval, and the cached content is the static
synthetic text listed under 10015 below. If the operator wants the copies gone
sooner, a URL purge needs its own decision.

**Fallback (step 8).** The fast path of section 6 (an emergency toggle of
`block_staging_redloop_emergency`) is used if closure is not verified 5
minutes before `D`. It is the already authorised emergency control, not a
routine one. Afterwards, a Terraform reconciliation PR and a Cloudflare Apply
follow, and the revert still has to land.

**The rollback was validated before activation.** On a simulated local merge
of #2799 (2026-11-18), `git revert -m 1` restored `main`'s tree exactly, and
the render then contained no Ingress and no Middleware.

### Preconditions (all must hold at step 2)

1. GO-1b is PASS, with a sanitized summary in #2769.
2. This section is approved and merged.
3. The operator has accepted the separate public-exposure risk assessment, which is held privately. The acceptance that covers the origin windows does not cover public exposure.
4. `redloop-waf-verify` is green within 24 h, and the kill switch rule is present and disabled.
5. The image digest and config checksum match #2796. `probe_success` = 1, no RedLoop alerts, no unexpected restarts, Argo CD Synced/Healthy, no Ingress yet.
6. The Security Events decision below is recorded.
7. The operator contact is reachable for the whole period, including the kill switch fallback.

### Edge preflight (step 4)

- The Certificate `redloop-synthetic-staging-tls` is `Ready`, issued by `letsencrypt-prod`.
- The Ingress names only `staging-redloop.mctl.ai` and references `redloop-redloop-staging-ratelimit@kubernetescrd`. The Middleware exists with `average 10, burst 20`.
- `https://staging-redloop.mctl.ai/healthz` returns 200 through Cloudflare.
- The in-cluster `redloop-staging-healthz` probe reads 1.

**The RedLoop probe stays on the in-cluster path.** `RedLoopStagingDown`
fires per instance after 2 minutes. An edge target would fail while the
certificate is being issued and again during the revert, so it would trip a
stop condition on every activation and every rollback. Instead, the script
watches the edge `/healthz` itself during the scan.

### Request rate: what is enforced, and when

| Control | What it does | Real time? |
|---|---|---|
| ZAP rate-limit rule, 4 req/s | enforces the scanner's budget for spidered and scanned requests | yes, enforced |
| Seed pacing in the hook, about 1 req/s | the five seed requests go through `access_url`, which the rate-limit rule did not throttle in GO-1b (all five fell in one second, exactly at the budget). The hook now waits 1 s between them | yes |
| Live watch in the script (every 5 s) | stops ZAP when the scanner exceeds 5 req/s (FAIL), or when all traffic to the origin does (stop condition, INCONCLUSIVE) | yes, within about 5 s |
| Post-scan check of the full origin log | the evidence on record; fails closed | no, after the scan |
| Traefik Middleware, 10 req/s per client and replica | a backstop only. Verified by configuration, **not** by a burst test, which would be an active test | yes, but not the budget |

The scanner sends a unique User-Agent (`RedLoop-GO2-ZAP/<run>`), so the
origin log tells its requests apart from unrelated public clients. Those are
counted separately and kept privately. `zap-baseline.py` also sends one
reachability check with a `python-requests` User-Agent, which counts as
unrelated.

### Stop conditions

Section 5 applies in full. In addition, stop the scan at once and go to step 6
(or step 8 if it is urgent) if any of these happen:

1. the edge `/healthz` fails twice in a row, or the edge answers 5xx (for example 526, an origin certificate error);
2. the scanner, or all traffic together, exceeds 5 req/s in the origin log;
3. the live origin log cannot be read (the rate is no longer observable);
4. any Traefik or `PublicEndpointDown` alert fires for another host;
5. the scanner requests anything outside `staging-redloop.mctl.ai`;
6. `D - 25 min` is reached.

Conditions 1, 2, 3 and 6 are enforced by the script itself.

### Passive edge baseline (step 5)

Only passive rules run: no active scan, no fuzzing, no WAF bypass (section 8
stays not approved). Five seed paths are used, as in GO-1b.

| Check | Required for PASS | Otherwise |
|---|---|---|
| Seeded controls | 10038 (CSP) **and** 10035 (HSTS) reported on `/` | INCONCLUSIVE |
| Accepted findings | 90004, 10049 and 10015. All optional. 10015 is accepted for this static synthetic fixture only (operator decision 2026-11-18, below) | - |
| Any other finding | none. A header that Cloudflare adds or changes counts too, until the operator has classified it | FAIL, for review |
| HTTP to HTTPS | `http://` redirects to `https://` (Always Use HTTPS) | FAIL |
| Certificate | the edge certificate verifies | unverified: ABORT before the scan, or INCONCLUSIVE |
| TLS 1.1 | refused **by the server**, shown by a `protocol_version` alert with no cipher negotiated | accepted: FAIL. Client cannot offer TLS 1.1, or unknown: INCONCLUSIVE |
| HSTS at the edge | absent, as seeded: the zone sets no HSTS | present: INCONCLUSIVE |
| Coverage | all five seed paths in ZAP's site tree, and in the origin log as scanner requests | INCONCLUSIVE |
| Rate | scanner requests present in the full origin log, at most 5 req/s | missing: INCONCLUSIVE; over 5: FAIL |
| Evidence | report present and parsing, ZAP exited 0 | INCONCLUSIVE |

A zero ZAP exit code alone is never PASS. Exit codes: 0 PASS, 4 FAIL,
5 INCONCLUSIVE, 1 ABORT (nothing scanned).

**10015 (Re-examine Cache-control Directives): accepted for this fixture
only.** ZAP raises it on HTTPS responses without `Cache-Control`. The operator
accepted it on 2026-11-18 as an optional, documented finding for this static
synthetic fixture alone. The ZAP rule is not disabled: it still runs, and the
validator only lists it as optional. Every response of the fixture is a fixed
string from this repository's values file: an HTML title page, a health JSON,
`robots.txt`, one line of JavaScript, and `Not Found`. None sets a cookie or
depends on the requester, so caching cannot expose anything sensitive or
user-specific. The acceptance does not carry over to any other host.

**The TLS 1.1 check needs a client that can offer TLS 1.1**, such as Homebrew
OpenSSL with `-cipher DEFAULT:@SECLEVEL=0`. `OPENSSL` points the script at
it. A client that cannot offer TLS 1.1 is reported as such. That result is
INCONCLUSIVE and is never counted as a server refusal.

**Rehearsal (local only, 2026-11-18; the real hostname was never contacted).**
- The pinned nginx image served the #2796 configuration over TLS, using a
  local CA, on an internal Docker network with no route out.
- ZAP ran only on that network, under the fixture's name.
- Host-side `curl` and `openssl` were pinned to loopback.
- A separate local OpenSSL server stood in for an edge that accepts TLS 1.1.

| # | Scenario (local fixture) | Expected | Got |
|---|---|---|---|
| 1 | #2796 config, redirect, trusted cert, TLS 1.1 refused, no HSTS | PASS | PASS (exit 0). Seeds one per second; scanner max 3 req/s, all traffic 4 |
| 2 | HSTS present at the edge | INCONCLUSIVE | INCONCLUSIVE (5): HSTS present, 10035 not reported |
| 3 | edge accepts TLS 1.1 (separate OpenSSL server) | FAIL | FAIL (4): `tls11=accepted` |
| 4 | client cannot offer TLS 1.1 (no `@SECLEVEL=0`) | INCONCLUSIVE | INCONCLUSIVE (5): `tls11=client_cannot_offer`, not counted as a refusal |
| 5 | `http://` served, not redirected | FAIL | FAIL (4) |
| 6 | pre-#2796 config (no hardening headers) | FAIL | FAIL (4): 10020, 10021, 10036 unexpected |
| 7 | origin log unreadable | INCONCLUSIVE | INCONCLUSIVE (5): live stream lost, ZAP stopped within one tick |
| 8 | edge certificate not trusted | ABORT | ABORT (1), ZAP not started |
| 9 | ZAP fails, no report | INCONCLUSIVE | INCONCLUSIVE (5) |
| 10 | burst of 30 req/s with the scanner User-Agent | FAIL | FAIL (4): live watch stopped ZAP |
| 11 | burst of 30 req/s from an unrelated client | INCONCLUSIVE | INCONCLUSIVE (5): stopped, counted as unrelated, not as scanner |
| 12 | less than 35 min to `D` | ABORT | ABORT (1), nothing scanned |
| 13 | edge reports `cf-cache-status: HIT` | PASS with notes | PASS (0); both cacheable paths recorded as cached, for the close-out |

**Request rate in the rehearsal.** The five seeds reached the origin one per
second in every complete run, for example `/` at :14, `/robots.txt` at :15,
`/healthz` at :16, `/static/app.js` at :17 and `/does-not-exist` at :18. The
spider phase that followed peaked at 3-4 req/s under the 4 req/s rule. No
complete run went above 4 req/s for the scanner.

In every scenario the report directory was `0700`, and no ZAP container or
log stream was left running.

**Defects found and fixed before this PR:**
1. `s_client` prints `Protocol: TLSv1.1` even when the handshake fails. Only
   a negotiated cipher now counts as accepted.
2. 10015 appears on HTTPS only. It is now accepted, as described above.
3. GO-1b sent the five seeds within one second. The hook now paces them at
   about 1 req/s.
4. The script now records `cf-cache-status` for the two cacheable paths, so
   the close-out knows what the edge holds.

```bash
#!/usr/bin/env bash
# GO-2 passive edge baseline. Run on the tester's machine, inside the approved
# exposure window only, after the Ingress is on and the edge preflight passed.
set -euo pipefail
umask 077
IMG=ghcr.io/zaproxy/zaproxy:2.17.0@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af
DEP=deploy/redloop-redloop-synthetic-staging-base-service
HOST=staging-redloop.mctl.ai
URL="https://$HOST"
OPENSSL="${OPENSSL:-openssl}"       # an OpenSSL able to offer TLS 1.1 (checked below)
# Absolute exposure deadline (UTC), from the operator's approval. The scan must
# end early enough to leave 25 minutes for closing the exposure.
DEADLINE="${GO2_DEADLINE:?set GO2_DEADLINE to the approved deadline, e.g. 2026-11-20T10:45:00Z}"
epoch() { python3 -I -c 'import sys,datetime;print(int(datetime.datetime.strptime(sys.argv[1],"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()))' "$1"; }
DL=$(epoch "$DEADLINE")
STOP_AT=$(( DL - 25*60 ))           # scan is stopped here at the latest
[ "$(date +%s)" -le $(( DL - 35*60 )) ] || { echo "ABORT: less than 35 min to the deadline; scan not started" >&2; exit 1; }

RUN=$(date -u +%Y%m%dT%H%M%SZ)
UA="RedLoop-GO2-ZAP/$RUN"           # marks the scanner's requests in the origin log
WUA="RedLoop-GO2-watch/$RUN"        # the tester's own health and TLS requests
ZNAME="redloop-go2-zap-$RUN"
OUT="$HOME/.local/share/mctl-forensics/redloop-go2-$RUN"
mkdir -p -m 0700 "$OUT"             # private: reports never leave this directory
START=$(date -u +%FT%TZ)

cat >"$OUT/seed_hook.py" <<'HOOK'
import time

SEEDS = ["", "robots.txt", "healthz", "static/app.js", "does-not-exist"]

def zap_started(zap, target):
    # access_url is not throttled by ZAP's rate-limit rule (GO-1b sent all five
    # seeds within one second), so the hook paces itself at about 1 req/s.
    base = target.rstrip("/") + "/"
    for i, path in enumerate(SEEDS):
        if i:
            time.sleep(1.0)
        zap.core.access_url(url=base + path, followredirects=False)

def zap_pre_shutdown(zap):
    with open("/zap/wrk/zap-urls.txt", "w") as f:
        f.write("\n".join(zap.core.urls()) + "\n")
HOOK

cat >"$OUT/validate.py" <<'PY'
import json, re, sys

report, urls, access, ua = sys.argv[1:5]
BASE = "https://staging-redloop.mctl.ai"
SEEDS = ["/", "/robots.txt", "/healthz", "/static/app.js", "/does-not-exist"]
REQUIRED = {"10038": "/", "10035": "/"}  # seeded CSP and HSTS gaps: detection controls
OPTIONAL = {"90004", "10049", "10015"}  # 10015: informational, HTTPS only; accepted as not applicable
lines = []

def path_of(uri):
    return (uri[len(BASE):] or "/") if uri.startswith(BASE) else uri

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
    scanner_log = [l for l in open(access) if ua in l]
except OSError:
    scanner_log = None
    lines.append("INCONCLUSIVE: origin access log missing")

for p in SEEDS:
    if zap_paths is not None and p not in zap_paths:
        lines.append(f"INCONCLUSIVE: seed path {p} not in ZAP's site tree")
    pat = re.compile(r'"GET ' + re.escape(p) + r' HTTP/')
    if scanner_log is not None and not any(pat.search(l) for l in scanner_log):
        lines.append(f"INCONCLUSIVE: seed path {p} not in the origin log as a scanner request")

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

CHK="$OUT/checks.txt"; : >"$CHK"
LF=""
cleanup() {
  docker kill "$ZNAME" >/dev/null 2>&1 || true
  [ -z "$LF" ] || kill "$LF" 2>/dev/null || true
  chmod -R go-rwx "$OUT" || true
}
trap cleanup EXIT INT TERM

# Fail closed: the edge must answer /healthz with 200 within 20 s, or no scan.
ready=0
for _ in $(seq 1 20); do
  if curl -fsS -o /dev/null --max-time 5 -A "$WUA" "$URL/healthz"; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "ABORT: edge not ready (or certificate not trusted); ZAP not started" >&2; exit 1; }

# Edge TLS and HTTPS checks, recorded privately.
{
  echo "http_redirect=$(curl -sS -o /dev/null --max-time 5 -A "$WUA" -w '%{http_code} %{redirect_url}' "http://$HOST/" 2>&1)"
  if curl -fsS -o /dev/null --max-time 5 -A "$WUA" "$URL/healthz" 2>/dev/null; then echo "cert=verified"; else echo "cert=failed"; fi
  echo "hsts_header=$(curl -sS -o /dev/null -D - --max-time 5 -A "$WUA" "$URL/" | tr -d '\r' | grep -ci '^strict-transport-security:' || true)"
} >"$OUT/tls.txt"
# TLS 1.1: only a protocol_version alert from the server counts as refused. A
# client that cannot offer TLS 1.1 at all proves nothing (INCONCLUSIVE).
S11=$("$OPENSSL" s_client -connect "$HOST:443" -servername "$HOST" -tls1_1 -cipher 'DEFAULT:@SECLEVEL=0' </dev/null 2>&1 || true)
printf '%s\n' "$S11" >"$OUT/tls11-handshake.txt"
# s_client prints "Protocol: TLSv1.1" even when the handshake fails, and labels
# a TLS 1.1 session's cipher "TLSv1.0". With -tls1_1 forced, any negotiated
# cipher (not "(NONE)") means the server accepted TLS 1.1.
if printf '%s' "$S11" | grep -Eq '^New, [^,]+, Cipher is [A-Z0-9]'; then echo "tls11=accepted"
elif printf '%s' "$S11" | grep -qi 'alert protocol version' && printf '%s' "$S11" | grep -q 'Cipher is (NONE)'; then echo "tls11=refused_by_server"
elif printf '%s' "$S11" | grep -Eqi 'no protocols available|unsupported protocol|unknown option'; then echo "tls11=client_cannot_offer"
else echo "tls11=unknown"; fi >>"$OUT/tls.txt"
cat "$OUT/tls.txt"
grep -q "^http_redirect=30[178] https://$HOST/" "$OUT/tls.txt" || echo "FAIL: http:// is not redirected to https://" >>"$CHK"
grep -q '^cert=verified' "$OUT/tls.txt" || echo "INCONCLUSIVE: edge certificate not verified" >>"$CHK"
case "$(grep '^tls11=' "$OUT/tls.txt")" in
  tls11=refused_by_server) ;;
  tls11=accepted) echo "FAIL: edge accepts TLS 1.1" >>"$CHK" ;;
  *) echo "INCONCLUSIVE: TLS 1.1 rejection not shown (client limitation or unknown)" >>"$CHK" ;;
esac
grep -q '^hsts_header=0' "$OUT/tls.txt" || echo "INCONCLUSIVE: HSTS present at the edge, so the seeded gap cannot be detected" >>"$CHK"

# Enforced budget: ZAP's own rate limiter, 4 req/s, one rule for every host.
RL="-config network.ratelimit.rules.rule(0).description=redloop-budget"
RL+=" -config network.ratelimit.rules.rule(0).enabled=true"
RL+=" -config network.ratelimit.rules.rule(0).matchStr=.*"
RL+=" -config network.ratelimit.rules.rule(0).regex=true"
RL+=" -config network.ratelimit.rules.rule(0).reqsPerSec=4"
RL+=" -config network.ratelimit.rules.rule(0).groupBy=rule"

# Live origin log for the real-time watch below. The post-scan check further
# down re-reads the full log independently.
kubectl -n redloop logs -f "$DEP" --since=5s >"$OUT/origin-live.log" 2>"$OUT/origin-live.err" &
LF=$!

docker run --rm --name "$ZNAME" -v "$OUT:/zap/wrk" "$IMG" \
  zap-baseline.py -t "$URL/" -m 1 -T 10 -I \
    --hook=/zap/wrk/seed_hook.py \
    -r report.html -J report.json \
    -z "-config spider.thread=1 -config connection.timeoutInSecs=10 -config connection.defaultUserAgent=$UA $RL" \
  >"$OUT/zap.log" 2>&1 &
ZP=$!

# Real-time watch, every 5 s, while ZAP runs. It stops ZAP at once when:
#   - the scanner itself exceeds 5 req/s in the live origin log  -> FAIL
#   - all traffic together exceeds 5 req/s (stop condition)       -> INCONCLUSIVE
#   - the live log stream is lost: rate unobservable              -> INCONCLUSIVE
#   - the edge /healthz fails twice in a row                       -> INCONCLUSIVE
#   - the scan would run into the closing time before the deadline -> INCONCLUSIVE
persec() { awk '{ if (match($0, /\[[^]]+\]/)) print substr($0, RSTART+1, 20) }' | sort | uniq -c | sort -rn | awk 'NR==1 { print $1 }'; }
STOPPED=""; HFAIL=0; TICK=0
while kill -0 "$ZP" 2>/dev/null; do
  sleep 5; TICK=$((TICK+1))
  if ! kill -0 "$LF" 2>/dev/null; then STOPPED="INCONCLUSIVE: live origin log stream lost; scan stopped"; break; fi
  S=$(grep -F "$UA" "$OUT/origin-live.log" | persec || true)
  A=$(grep -v 'kube-probe/' "$OUT/origin-live.log" | persec || true)
  if [ "${S:-0}" -gt 5 ]; then STOPPED="FAIL: scanner exceeded 5 req/s ($S) in the live origin log; scan stopped"; break; fi
  if [ "${A:-0}" -gt 5 ]; then STOPPED="INCONCLUSIVE: origin traffic exceeded 5 req/s ($A, scanner ${S:-0}); scan stopped"; break; fi
  if [ $((TICK % 2)) = 0 ]; then
    if curl -fsS -o /dev/null --max-time 5 -A "$WUA" "$URL/healthz"; then HFAIL=0; else HFAIL=$((HFAIL+1)); fi
    if [ "$HFAIL" -ge 2 ]; then STOPPED="INCONCLUSIVE: edge /healthz failed twice; scan stopped"; break; fi
  fi
  if [ "$(date +%s)" -ge "$STOP_AT" ]; then STOPPED="INCONCLUSIVE: closing time before the deadline reached; scan stopped"; break; fi
done
if [ -n "$STOPPED" ]; then
  echo "$STOPPED" >>"$CHK"
  docker kill "$ZNAME" >/dev/null 2>&1 || true
fi
set +e; wait "$ZP"; ZAP_RC=$?; set -e
kill "$LF" 2>/dev/null || true; LF=""
[ "$ZAP_RC" = 0 ] || echo "INCONCLUSIVE: ZAP exit code $ZAP_RC" >>"$CHK"

# Post-scan rate evidence from the full origin log. A failed fetch is recorded,
# never suppressed, and an empty log is never "zero requests".
if ! kubectl -n redloop logs "$DEP" --since-time="$START" >"$OUT/origin-raw.log" 2>"$OUT/origin-logs.err"; then
  echo "INCONCLUSIVE: origin access log could not be fetched" >>"$CHK"
fi
grep -v 'kube-probe/' "$OUT/origin-raw.log" >"$OUT/origin-access.log" || true
SCAN_N=$(grep -cF "$UA" "$OUT/origin-access.log" || true)
SCAN_MAX=$(grep -F "$UA" "$OUT/origin-access.log" | persec || true)
ALL_MAX=$(persec <"$OUT/origin-access.log" || true)
OTHER_N=$(grep -vF "RedLoop-GO2-" "$OUT/origin-access.log" | grep -vc 'Blackbox Exporter' || true)
if [ "${SCAN_N:-0}" = 0 ] || [ -z "$SCAN_MAX" ]; then
  echo "INCONCLUSIVE: no scanner requests in the origin log, so no rate evidence" >>"$CHK"; SCAN_MAX=unknown
elif [ "$SCAN_MAX" -gt 5 ]; then
  echo "FAIL: scanner exceeded 5 req/s ($SCAN_MAX)" >>"$CHK"
fi
[ "${OTHER_N:-0}" = 0 ] || echo "NOTE: $OTHER_N origin requests from unrelated clients during the scan (kept privately)" >>"$CHK"

# Edge cache evidence for the close-out. Cloudflare caches .js and robots.txt
# by default (200: up to 120 min) and 404 for 3 min; the Ingress revert does
# not evict them, so the close-out waits out that TTL (RoE section 12).
for p in /static/app.js /robots.txt; do
  c=$(curl -sS -o /dev/null -D - --max-time 5 -A "$WUA" "$URL$p" 2>/dev/null | tr -d '\r' | awk -F': ' 'tolower($1)=="cf-cache-status"{print $2}')
  echo "edge_cache $p=${c:-none}" >>"$OUT/tls.txt"
  case "$c" in HIT|MISS|EXPIRED|REVALIDATED|UPDATING|STALE) echo "NOTE: $p is cached at the edge ($c); fixture copies expire by D + 120 min" >>"$CHK" ;; esac
done

python3 -I "$OUT/validate.py" "$OUT/report.json" "$OUT/zap-urls.txt" "$OUT/origin-access.log" "$UA" >>"$CHK" 2>&1 \
  || echo "INCONCLUSIVE: report validator failed" >>"$CHK"

if grep -q '^FAIL:' "$CHK"; then V=FAIL; elif grep -q '^INCONCLUSIVE:' "$CHK"; then V=INCONCLUSIVE; else V=PASS; fi
echo "verdict=$V zap_rc=$ZAP_RC scanner_requests=${SCAN_N:-0} scanner_max_req_per_sec=$SCAN_MAX all_max_req_per_sec=${ALL_MAX:-unknown} unrelated_requests=${OTHER_N:-0}" | tee "$OUT/verdict.txt"
cat "$CHK"
case "$V" in PASS) exit 0 ;; FAIL) exit 4 ;; *) exit 5 ;; esac
```

### Close-out (step 9)

- Closure is verified (step 7).
- If the kill switch was used, Terraform is reconciled and applied, and no
  Cloudflare drift is left.
- At `D + 125 min` (step 10), each of the five seed paths is requested once
  through the edge, and none returns the fixture. Every answer is 404 from
  Traefik, or 403 if the kill switch is still on. A cached 200 at that point
  is a stop and an escalation to the operator, never a close.
- No RedLoop alerts. The pod has had no restarts and its digest is unchanged.
- A sanitized summary goes to #2769. The report, the request logs, the
  scanner IP, the times and the alert history stay private.
- **Gate 4 cannot close** until the Ingress change is reverted and verified,
  the edge cache check has passed, and every Cloudflare change, if any, is
  reconciled.

### Cloudflare Security Events (proposed decision)

The Cloudflare token has no Analytics Read, so edge blocks and challenges in
the window cannot be read afterwards. **Proposed:** accept the missing
Analytics Read conditionally, for this one bounded, passive GO-2 window
only. This is recorded as a **limitation of observability**: it does not
mean that WAF events were checked. It does not cover active testing, a WAF
bypass, or any later window. Visibility in the window comes from:
- the RedLoop monitoring;
- the origin access log;
- the scan report, including any 403 answers;
- the proven kill switch.

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
| GO-2 | PROPOSED in section 12, not approved. Needs approval of this section, GO-1b PASS, the separate public-exposure risk acceptance, and a separate GO-2 EXECUTE decision with `P` and `D` |
| Not approved | GO-2 (public Ingress, edge path) until the row above is satisfied, active or full scans, WAF bypass or scanner exception, production pentest |
| Related | The residual pod-startup risk for this workload only is accepted conditionally until 2026-12-18 at the latest. That record is held privately |
