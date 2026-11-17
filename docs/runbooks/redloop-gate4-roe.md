# RedLoop Gate 4: Rules of Engagement

**Status: DRAFT, not approved.** No DAST, no scan, and no public exposure of
`staging-redloop.mctl.ai` is authorised until every field marked **TBD**
below is filled in and an operator has signed the approval block at the
end, in a reviewed PR.

These rules govern dynamic testing (DAST, a manual web test) of the RedLoop
synthetic staging fixture. They do not authorise a production pentest,
which is a separate gate.

## 1. Authorisation

| Field | Value |
|---|---|
| Authorising operator | **TBD** (name and role, recorded in the approval PR, not here) |
| Authorisation reference | **TBD** (PR or issue link carrying the signed decision) |
| Tester / scanner operator | **TBD** |
| Operator contact during the window | **TBD** (channel only, e.g. "operator Telegram"; no phone numbers or handles in this public repository) |
| Testing window | **TBD** (start and end in UTC, at most 4 hours per window) |
| Scanner source IP(s) | **TBD** (single /32 per scanner; required only for the edge path in section 4) |
| Scanner and version | **TBD** (e.g. ZAP baseline/full, pinned version) |

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
| Scanner request rate | at most **5 req/s** sustained, single thread or equivalent | the tester (scanner config) |
| Hard limit per client IP | 10 req/s average, burst 20, answered with 429 | Traefik Middleware `redloop-staging-ratelimit` (renders only with the Ingress) |
| Concurrency | at most 2 connections | the tester |

The Traefik limit is a backstop, not the budget. A scanner that gets 429s
is above the RoE and must be slowed down, not retried harder. On the origin
path (port-forward) Traefik is not in the way, so the tester's own
configuration is the only limit. Keep to 5 req/s there too: the pod has a
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
     Using the fast path is an **operator decision (TBD)**: it is not
     authorised by default.
3. **Ingress off**: revert the PR that set `ingress.enabled: true` and let
   Argo CD sync. The Middleware goes away with it.
4. **Scale to 0**: `replicaCount: 0` in the service values (PR). Not yet
   drilled. That is a Gate 4 open item.

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
    is an open operator decision;
  - the alert history for the window.
- Findings go to an issue, never to this public repository's PR text in
  exploitable detail.

## 8. Proposal: scanner exception at the edge (DISABLED, not implemented)

Use this only if the edge path must run without the Managed Free Ruleset in
the way. It is a proposal; nothing in this PR changes Cloudflare.

- **Constraint:** `mctl.ai` is on the Free plan. The custom-rules phase
  allows 5 rules and 4 are in use, so this would take the last slot. That
  is an **operator decision (TBD)**.
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
  - It sits **after** `block_staging_redloop_emergency` in the rules list,
    so the kill switch still wins.
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

1. This RoE is approved: every TBD in sections 1, 6 and 8 is filled in and
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

## Approval

| | |
|---|---|
| Approved by | **TBD** |
| Date (UTC) | **TBD** |
| Approval PR | **TBD** |
