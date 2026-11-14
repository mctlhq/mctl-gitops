# Design: issue-343-spike-evaluate-cloudflare-kitesurf-as-a

## Current state

### Repository conventions (mctlhq/.github at `378ac2f370362d52b74f8a8cc36ca402c12e4890`)

- A research spike lands as three pieces:
  - a report under `docs/spikes/<name>.md`, for example `docs/spikes/edge-config-kv-instant.md` with its "Non-claims and evidence tags" and "Evidence pins" sections;
  - a `kind: SpikeDefinition` manifest under `roadmap/spikes/<name>.yaml`, for example `roadmap/spikes/edge-config-kv-instant.yaml` (`lifecycle: proposed`, `execution.devloop: true`, `evidence.report`);
  - one entry in the `AGENTS.md` "Spikes" index.
- The manifest schema is `roadmap/schemas/spike-definition.schema.json`, and `roadmap/README.md` "SpikeDefinition v1alpha1" documents it:
  - at least two unique `UPPER_SNAKE` outcomes;
  - `decision` only under `lifecycle: decided`, so an agent never records its own approval;
  - spike names and issue bindings unique across spikes.
- CI (`.github/workflows/roadmap-validate.yml`) runs `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes`, `roadmap/scripts/lifecycle_guard.py` and `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'`.
- No `kitesurf` string exists anywhere in the repo. Browser mentions are limited to:
  - `docs/spikes/web-platform-unification.md`: Playwright/axe preview checks "not-run";
  - `roadmap/epics/web-platform-contracts.yaml` (epic #330): browser a11y and route-CSP test design;
  - `docs/spikes/agent-client-compatibility.md`: a Cloudflare 403 "browser signature" observation.
- None of these is a browser execution service.
- `.github/ISSUE_TEMPLATE/spike.yml` defines `Source/Question/Outcomes/Lifecycle/Related/Why mctl`. Issue #343 follows it, and its Source is the dedup key. This proposal creates no issue.

### Deployed state checked

- `$MCTL_GITOPS_ROOT` checkout, mctl-gitops `68d6cedbfd5daa244b9f06c14f474029a1c2f40a`. A grep for `playwright|puppeteer|chromium|browserless|headless` over `services/` and `tenants/` matched only:
  - `services/namax66/news-factory/values.yaml`: a worker with ingress disabled, image `ghcr.io/mctlhq/news-factory:0.2.5`, limits `500m`/`512Mi` with the comment "Headless Chromium; 512Mi is what the tenant tested the worker with", `NEWS_BROWSER_ENABLED: "true"`, `NEWS_CHROMIUM_SANDBOX: "false"`, and `runAsUser: 10001`. This is tenant-owned Chromium with the Chromium sandbox disabled.
  - `services/labs/claude-remote/values.yaml`: a "headless `claude -p`" scheduler. This is not a browser.
- `tenants/namax66/values.yaml` shows `allowInternetEgress: true`, `limits.memory: "1Gi"` and `pods: "5"`. A grep of `tenants/*/values.yaml` shows `allowInternetEgress` is true for admins, erpact, labs and namax66, and false for commerce-proof, karabu and mctl.
- `agent-platform/policy.yaml` declares `WebSearch` and `WebFetch` as `category: network`. Execution profiles `issue-investigator-default`, `implementer-default` (`policyRef: production-code-author`), `service-agent-default` and `shepherd-default` grant `WebFetch`. This is HTTP fetch with no JavaScript execution and no browser.
- `argo-workflows/secrets/mctl-agents-secrets.yaml`: the comment says agents "rely on WebSearch/WebFetch only" without an mctl token.
- `infrastructure/cloudflare/`: Workers exist for mctl-web zones (`zones/mctl-ai/workers.tf`) and Workers KV (`account/workers-kv.tf`). No Browser Rendering binding, Dynamic Workers or Kitesurf resource was found by grep.
- `mctl_get_service_status(namax66, news-factory)`: ArgoCD `Healthy`, `Synced`, image `0.2.5`, `base-service`, no database.
- Not observed:
  - The source of mctl-agents, mctl-telegram, mctl-api, mctl-support and news-factory was not cloned here, so in-code browser, Puppeteer or Playwright usage there is UNOBSERVED, not absent.
  - The Playwright fixtures for #330 and gitops#2544 were not located: UNOBSERVED.

### Upstream sources (vendor claims, fetched 2026-11-14)

- `cloudflare/kitesurf`:
  - HEAD `4a2903813a22b08d4f3cc64a4b35339d0293a5d1` (`git ls-remote`), Apache-2.0.
  - The README says it "provides a CDP endpoint, not a full Chrome implementation", and that it has no authentication of its own ("Do not deploy Kitesurf without authentication in front of it").
  - Cloud use requires a Workers Paid plan (Dynamic Workers). Local builds use Bazelisk, Node 22+ and pnpm 9.15.4, and `wrangler` deploys it. The `workers.dev` URL is public by default.
- Blog (structured date 2026-11-13):
  - "experimental", "under heavy development", stateless.
  - Puppeteer `connect` example. Playwright is not mentioned. WebMCP was added in a follow-up, with no detail.
  - The managed Browser Run APIs are named as an alternative.
- kitesurf.dev/benchmarks (run 2026-11-13 02:28 UTC): 38 pages, 5 samples each. Medians for Kitesurf vs cold-start Chrome:

  | Metric | Kitesurf | Cold-start Chrome |
  | --- | --- | --- |
  | Screenshot CPU | 361 ms | 747 ms |
  | Screenshot memory | 54 MiB | 329 MiB |
  | Screenshot wall time | 1.20 s | 1.01 s |

  The worst page was 9.86 s on Kitesurf vs 2.68 s on Chrome. Wall time excludes network time, Chrome excludes launch time, and p95 is unreliable with only 5 samples. All of these are `[VENDOR]`, not MCTL observations.

## Proposed solution

Add a research report and a proposed spike manifest. Change no runtime, infrastructure or issue state.

1. `docs/spikes/cloudflare-kitesurf.md`, with sections in this order:
   1. **Non-claims and evidence tags.** Tags: `[CODE]`, `[DEPLOYED]`, `[DOC]`, `[VENDOR]`, `UNKNOWN`, `NOT_RUN`, `UNOBSERVED`.
   2. **Evidence pins.** The upstream and MCTL commits and dates above.
   3. **Owner and overlap map.** One row each for #18, #151, #181, #308, #314, #330, gitops#2544, mctl-agents#1035 and telegram#1088, plus the statement "no epic, implementation issue or follow-up created".
   4. **Current-state workload matrix.** Rows:
      - agent `WebFetch`/`WebSearch` (all DevLoop profiles);
      - tenant `namax66/news-factory` headless Chromium;
      - preview Playwright/a11y (#330), NOT_RUN;
      - managed Telegram runtime and support-agent web access, UNOBSERVED.

      Columns: owner, tenant/principal propagation, auth/consent, approval, budget, trace, evidence, JS, screenshot, session, interaction, and status (VERIFIED/UNKNOWN/NOT_RUN).
   5. **Capability compatibility matrix**, Kitesurf vs Chromium/Playwright:
      - CDP subset vs Playwright protocol (Playwright drives Chromium over CDP, but Playwright-on-Kitesurf is UNKNOWN);
      - screenshots, JS, cookies/session, WebGL/video, bot challenges, WebMCP.

      Each cell is `[VENDOR]` or UNKNOWN.
   6. **Minimal optional backend contract**, design only:
      - operations `negotiate(features)`, `session.create(tenant, principal, policy_ref, ttl)`, `navigate`, `extract`, `interact`, `screenshot`, `cancel`, `close`;
      - a deadline on every operation;
      - failure classes `unsupported_feature | policy_refused | egress_denied | timeout | cancelled | engine_error | upstream_http_error`;
      - an `evidence_ref` and `trace_id` on every result;
      - cleanup guaranteed on cancel or timeout.

      The contract is stated as "CDP compatibility is not feature parity". Identity, tenant and policy decision references are inputs minted by MCTL; the backend never decides them.
   7. **Routing and fallback.**
      - Selection is by declared capability. An unsupported capability is refused before execution.
      - Fallback to Chromium is allowed only for operations classified read-only: navigate, extract, screenshot. `interact`, and any form submit or non-GET request, is never auto-replayed. It fails closed with `unsupported_feature`, and a new exact approval is needed.
      - Idempotency key is `work_item_id + step + backend`.
      - Circuit breaker per backend: open on N consecutive `engine_error` or a fidelity mismatch.
      - Observation fields: `backend`, `backend_version` (upstream SHA), `fallback_from`, `failure_class`, `cpu_ms`, `wall_ms`.
      - An operator troubleshooting table.
   8. **Threat model and negative tests.** Each threat gets an attack, control, deterministic test and owner. Owner candidates are the MCTL egress proxy/NetworkPolicy (mctl-gitops), the MCP gateway policy (#195 lineage), mctl-api budget and audit, and the adapter. The threats:
      - SSRF to `169.254.169.254`, RFC1918, cluster DNS and the Workers loopback;
      - redirect chains to private addresses, and DNS rebinding with a TTL-0 flip;
      - sandbox escape (Dynamic Worker isolate vs a Chromium with `--no-sandbox`, citing the observed news-factory setting);
      - cross-tenant session or cookie bleed in a shared isolate;
      - token exposure through CDP `Network.getCookies` or `Storage`;
      - DOM and screenshot-OCR prompt injection, where content is always untrusted data and never policy;
      - retention of screenshots and DOM in Workers logs or R2;
      - usage abuse and cost amplification through unbounded sessions;
      - the unauthenticated engine endpoint (upstream README warning).
   9. **Benchmark protocol**, separately authorized:
      - environment: local `wrangler dev` vs hosted Dynamic Workers vs a pinned Chromium/Playwright container, all on synthetic fixtures served from an MCTL-controlled non-production origin;
      - four fixture classes: F1 anonymous HTML/JS extraction; F2 screenshot plus DOM click/type; F3 multi-page synthetic login with a throwaway session; F4 negative cases (WebGL canvas, `<video>`, a synthetic challenge page, plus the SSRF/rebinding targets from section 8);
      - n ≥ 30 per fixture per backend so p95 is meaningful;
      - metrics as listed in requirements.md;
      - the cost formula `per_1000 = 1000 × (worker_requests × rate + cpu_ms × rate + egress + evidence_storage) + fallback_rate × chromium_per_1000`, with UNKNOWN rates;
      - a hard spend ceiling and a time box;
      - every result cell `NOT_RUN`.
   10. **No-go thresholds**, fixed before measurement. Any one blocks B or C:
       - F1/F2 completion below 95% of the Chromium baseline;
       - fidelity mismatch above 2% on the extraction diff;
       - any negative security test not passing deterministically;
       - per-1000 cost including fallback not at least 30% below Chromium;
       - local vs hosted p50 divergence above 2x without an explanation.
   11. **Four-option decision matrix** (A/B/C/D), with total operational cost, policy gates, vendor lock-in (Workers Paid and Dynamic Workers; self-host limited to local `wrangler dev`, so not a production self-host path; UNKNOWN beyond that) and counter-evidence (vendor medians favour Kitesurf on CPU and memory).
   12. **Proposed verdict: `REFERENCE_ONLY`.** This is a research finding, not an approval, for two reasons. First, no MCTL platform-owned browser workload exists to route, since agents use `WebFetch` only. Second, the engine is experimental, unauthenticated by default and Cloudflare-hosted only, and every MCTL-side metric is `NOT_RUN`. Re-open toward `HYBRID_FALLBACK` only when both triggers hold: a governed browser capability is authorized on the roadmap, and the benchmark in section 9 is authorized and passes the thresholds in section 10.
2. `roadmap/spikes/cloudflare-kitesurf.yaml`:
   - `kind: SpikeDefinition`, `metadata.name: cloudflare-kitesurf`, `owner: mctlhq/.github`;
   - the question from the issue;
   - `lifecycle: proposed`;
   - `github.issue: {repository: mctlhq/.github, number: 343}`;
   - outcomes `ADOPT_LIGHTWEIGHT, HYBRID_FALLBACK, REFERENCE_ONLY, REJECT`;
   - `execution.devloop: true`;
   - `evidence.report: docs/spikes/cloudflare-kitesurf.md`;
   - a header comment saying the proposed verdict lives only in the report;
   - no `decision`, `epic` or `timebox`.
3. `AGENTS.md`: append one "Spikes" entry linking the report, "spike report for mctlhq/.github#343, proposed verdict REFERENCE_ONLY".

Why this shape: it follows the established spike pattern (#272, #325). It records the question in Git before the verdict, and it leaves the decision to the owner, as the schema's `decided` gate enforces. It does not invent a browser service that the deployed state does not show.

## Alternatives

- **Build a local Kitesurf vs Playwright harness as a reference model**, like `docs/spikes/finance-assistant/` or `automation-control-plane/`. Dropped: the issue states that any harness or prototype needs separate authorization, and that the investigator may design but not execute.
- **Recommend `HYBRID_FALLBACK` now on the vendor benchmark.** Dropped:
  - the vendor numbers exclude network time and Chrome launch time, and use 5 samples;
  - no MCTL workload is identified to route;
  - adopting would force an authorization and egress design for an engine with no built-in auth;
  - the issue says HYBRID is a candidate, not pre-approved.
- **Open an implementation or benchmark follow-up issue alongside the report.** Dropped: the issue forbids parallel epics or implementation issues, and follow-ups belong in the owner's `decision.followUps`.
- **Record `lifecycle: parked` with an activation trigger.** Considered. Dropped in favour of `proposed`, because the owner has not chosen yet. The report states the suggested re-activation trigger so the owner can park the spike when deciding.

## Platform impact

- Migrations: none. Docs plus one manifest in mctlhq/.github. The roadmap publication does not include spikes yet (`roadmap/README.md`), so publishing is unaffected.
- Backward compatibility: the manifest must satisfy the schema and cross-kind uniqueness (name `cloudflare-kitesurf`, issue #343 bound nowhere else, checked by grep). CI validate and unit tests must stay green.
- Resource and cost impact: zero. No Cloudflare, cluster or model spend beyond this run.
- Risks and mitigations:
  - Readers mistake vendor numbers for MCTL measurements. Mitigation: a mandatory `[VENDOR]` tag and a separate table.
  - Readers treat `REFERENCE_ONLY` as a decision. Mitigation: no `decision` block, `lifecycle: proposed`, and the "proposed verdict" wording.
  - The report flags tenant news-factory's disabled Chromium sandbox. Mitigation: it is stated as an observation for the threat model only. Any remediation is a tenant/owner matter outside this spike, and no change is made.
  - Upstream moves quickly. Mitigation: every upstream fact is pinned to SHA `4a29038` and a fetch date, and the benchmark protocol requires re-pinning before execution.
