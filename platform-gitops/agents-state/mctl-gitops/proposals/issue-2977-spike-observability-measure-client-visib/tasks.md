# Tasks: issue-2977-spike-observability-measure-client-visib

No task here runs a live probe or changes any deployed object (VMProbe, VMRule,
blackbox modules, Traefik, Cloudflare Terraform, service values, rollout strategy).

- [ ] 1. Write `docs/spikes/2977-rollout-client-downtime.md` with status
  `NO LIVE PROBE / DECISION PROVISIONAL`, a source-pinned inventory,
  signal matrix, option A–D comparison, offline estimator contract,
  privacy/failure-domain analysis and draft-only follow-up issue.
  **P1-1:** correct stale Oct 6 Traefik podscrape comment: Oct 29
  `traefik-helmchartconfig.yaml.tpl` **configures** JSON access logging
  400–599; read-only verify running flags and redacted Loki sample or
  mark `runtime: not observed`. Never copy raw Cf-Connecting-Ip,
  Cf-Ray or user headers. Include 30s metrics/60s blackbox/2s Ready,
  CF access unresolved, and distinguish EndpointSlice from pod Ready.
  0.143.0 Loki was *same-day query truncated/unverified*, not expired
  because of configured 14d retention. Lifecycle != HTTP downtime.
- [ ] 2. Create offline stdlib-only
  `scripts/rollout-outage/estimate.py` with CLI
  `estimate.py ATTEMPTS.jsonl --window META.json`, JSON output.
  **P1-2:** separate sampled `http_observations` (a descriptive failure
  event envelope, NOT an unconditional blackout lower bound),
  `continuous_blackout` (unknown by default; only conditional
  model bounds under independent continuity evidence; interleaved
  success => unknown), and independent `lifecycle`.
  Classify unattributed origin/edge 5xx, 403, 429, WAF challenges.
  All-success sampling != proven uptime between probes. Fail closed
  on missing bounds, coverage gaps, clock/cache/redirect/control errors.
  A +/-1–2s target is only conditional model resolution.
- [ ] 3. Create synthetic fixtures under
  `tests/fixtures/rollout-outage/`: no real IPs/user IDs/headers,
  cookies, full CF-Ray or response bodies. Use tg-preview/tg/mctl.ai
  only. Explicitly include counterexamples: errors t0/t10 with
  success t5, and adjacent failed samples with hidden recovery.
  Include challenge/403/429 and privileged ASN24940 control success.
- [ ] 4. Add `tests/test_rollout_outage_estimator.py` (unittest) covering T1-T18.
  (depends on 3) — DoD: `python3 tests/test_rollout_outage_estimator.py` passes
  locally.
- [ ] 5. Add one step to `.github/workflows/validate-manifests.yml` that runs
  `python3 tests/test_rollout_outage_estimator.py`, next to the existing explicit
  `python3 tests/...` steps. (depends on 4) — DoD: the `validate` check is green on
  the PR. The step uses no secrets and no network.
- [ ] 6. Fill in the decision record in the spike doc. Use the provisional
  `RELEASE_SCOPED_PROBE` (conditional upgrade to `HYBRID_EDGE_AND_PROBE`), cost and
  false-positive notes, staged rollback, `owner: pending (issue author)`, the draft
  follow-up issue text and the preview acceptance criteria. Cite the harness result
  for the +/-1-2 s claim. (depends on 4) — DoD: the doc states that production
  instrumentation and any live test require explicit owner GO, and the follow-up is
  drafted, not filed.
- [ ] 7. Open the PR from a feature branch and request an independent review of the
  doc and harness before any follow-up is filed. (depends on 5, 6) — DoD: the PR
  links #2977, mctl-telegram#1108, #1115 and #1116, and states "no deployed object
  changed".

## Tests

- [ ] T1. 200→503 (~15s)→200 at 1Hz, 2s timeout:
  `http_observations.status=measured` and descriptive envelope;
  `continuous_blackout=unknown` without independent proof,
  `precision_target_met=null`; conditional hypothesis bounds
  separately match arithmetic.
- [ ] T2. 10s timeout response interval: sampled failures but
  model half-width no longer satisfies +/-2s.
- [ ] T3. No real user traffic; all synthetic samples successful
  with full coverage: `no_outage_observed` means only no sampled
  failure, not zero downtime between probes or on MCP/OAuth.
- [ ] T4. No failures but a 20 s gap in attempts (missed probes): `unknown`,
  `reason: coverage_gap`.
- [ ] T5. A failing span with a 5 s gap between L and F: `unknown`,
  `reason: coverage_gap`.
- [ ] T6. Cloudflare 521/522 => `edge_52x`;
  502/503/504 without independent origin proof =>
  `http_5xx_unattributed` (not `origin_5xx`).
- [ ] T7. Interleaved 503/200 from multiple colos:
  `pattern=intermittent`, event envelope descriptive,
  transition count present, `continuous_blackout=unknown`,
  no full ray identifiers stored.
- [ ] T8. Clock offset unknown, or above tolerance: `unknown`,
  `reason: clock_untrusted`.
- [ ] T9. No success after the failures before the window ends: `unknown`,
  `reason: no_success_after` (and the mirror case `no_success_before`).
- [ ] T10. Probe self-failure (`probe_local_error` or `dns_error` on both subject and
  control): `unknown`, `reason: control_failed` or `probe_local_error`.
- [ ] T11. An attempt with `cf_cache_status: HIT`: `unknown`,
  `reason: edge_cache_served`. One with `redirect_count > 0`: `unknown`,
  `reason: redirect_followed`.
- [ ] T12. SIGTERM→listening = 16.77s with all-success
  probes: `http_observations=no_outage_observed`; lifecycle
  separately reports 16.77s.
- [ ] T13. AST forbidden-import check: defense-in-depth only.
- [ ] T14. Fail-fast runtime network/socket isolation guard exercised
  by tests without actual external connections.
- [ ] T15. 503@t0, success@t5, 503@t10 disproves a 10s continuous
  blackout lower bound: observation envelope kept, blackout unknown.
- [ ] T16. Two adjacent 503 observations with hidden brief recovery:
  unconditional lower bound is unknown/zero, conditional model clearly labelled.
- [ ] T17. 403/429/Cloudflare challenge from external ASN, while
  trusted ASN24940 control succeeds: distinguish edge denial from origin
  503 and ordinary client access from privileged vantage.
- [ ] T18. Traefik access logging configured on but runtime
  `not observed`; 0.143.0 same-day 1000-line Loki cutoff:
  `query_truncated_or_unverified`, not data retention expiry.

## Rollback

Every change is additive (one doc, one script, fixtures, one test, one CI step). To
roll back, revert the PR's merge commit through a normal PR. No deployed object,
metric or alert depends on these files, so a revert has no runtime effect. If only
the CI step is a problem (for example it slows or breaks the required `validate`
check), revert that one step and keep the doc and harness. Staged rollback for any
future live probe is specified in the spike doc and needs its own owner GO.
