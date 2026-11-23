# Tasks: issue-2977-spike-observability-measure-client-visib

No task here runs a live probe or changes any deployed object (VMProbe, VMRule,
blackbox modules, Traefik, Cloudflare Terraform, service values, rollout strategy).

- [ ] 1. Write `docs/spikes/2977-rollout-client-downtime.md` with sections: STATUS
  (`NO LIVE PROBE; DECISION PROVISIONAL`), evidence inventory, signal table, design
  matrix A-D, time/identity contract, safety checklist, decision record and draft
  follow-up issue. Follow the structure of design.md. — DoD: every inventory row
  cites a repo path (`vmprobes.yaml`, `blackbox-exporter.yaml`,
  `blackbox-alerts.yaml`, `mctl-telegram-alerts.yaml`, `mctl-telegram-canary.yaml`,
  `mctl-telegram-slo.yaml`, `traefik-podscrape.yaml`,
  `traefik-helmchartconfig.yaml.tpl`, `firewall.tf`, `monitoring.yaml`, `loki.yaml`,
  `services/labs/mctl-telegram*/values.yaml`) or a read-only tool call, with interval
  and retention. Cloudflare analytics/Logpush, external monitors and Kubernetes event
  retention are listed as "not observed". The issue's lifecycle numbers appear only
  under "lifecycle", never as downtime.
- [ ] 2. Create `scripts/rollout-outage/estimate.py` (stdlib only), implementing the
  attempt/window schema, outcome classes, bounds and `unknown` reasons exactly as
  in design.md. The CLI is `estimate.py ATTEMPTS.jsonl --window META.json`, which
  prints the report JSON to stdout and exits non-zero only on malformed input.
  (depends on 1 for the contract text) — DoD: the module imports none of `socket`,
  `urllib`, `http.client`, `requests`, `httpx` or `subprocess`. The report has
  separate `http_outage` and `lifecycle` keys. `status` is in {measured,
  no_outage_observed, unknown}, and `unknown` always carries `reason`.
- [ ] 3. Add fixtures under `tests/fixtures/rollout-outage/` (one `.jsonl` +
  `.meta.json` per case in T1-T12) and a `README.md` stating they are synthetic.
  (depends on 2) — DoD: no real IPs, user ids, cookies, tokens or response bodies in
  any fixture. Hosts are limited to `tg-preview.mctl.ai`, `tg.mctl.ai` and
  `mctl.ai`.
- [ ] 4. Add `tests/test_rollout_outage_estimator.py` (unittest) covering T1-T13.
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

- [ ] T1. 200 -> 503 x ~15 -> 200 at 1 Hz, 2 s timeout, clock tolerance 50 ms:
  `status: measured`. Lower/upper bounds match hand-computed values to the ms, and
  `precision_target_met: true`.
- [ ] T2. Same outage with a 10 s timeout and timeouts instead of 503s: still
  `measured`, but `precision_target_met: false`.
- [ ] T3. No traffic / no failures with full coverage: `no_outage_observed`.
- [ ] T4. No failures but a 20 s gap in attempts (missed probes): `unknown`,
  `reason: coverage_gap`.
- [ ] T5. A failing span with a 5 s gap between L and F: `unknown`,
  `reason: coverage_gap`.
- [ ] T6. Cloudflare 521/522 attempts: classified `edge_52x`, counted separately
  from `origin_5xx`. The report is `measured`.
- [ ] T7. Concurrent edge paths (ok/503 interleaved from two colos by `cf_ray`
  suffix): `pattern: intermittent`, with the envelope bounds and transition count
  reported.
- [ ] T8. Clock offset unknown, or above tolerance: `unknown`,
  `reason: clock_untrusted`.
- [ ] T9. No success after the failures before the window ends: `unknown`,
  `reason: no_success_after` (and the mirror case `no_success_before`).
- [ ] T10. Probe self-failure (`probe_local_error` or `dns_error` on both subject and
  control): `unknown`, `reason: control_failed` or `probe_local_error`.
- [ ] T11. An attempt with `cf_cache_status: HIT`: `unknown`,
  `reason: edge_cache_served`. One with `redirect_count > 0`: `unknown`,
  `reason: redirect_followed`.
- [ ] T12. Lifecycle metadata of 16.77 s with no subject failures:
  `http_outage.status` is `no_outage_observed` (full coverage), and the lifecycle
  value is reported only under `lifecycle`.
- [ ] T13. Static guard: parse `estimate.py` with `ast` and fail on any forbidden
  network/subprocess import.

## Rollback

Every change is additive (one doc, one script, fixtures, one test, one CI step). To
roll back, revert the PR's merge commit through a normal PR. No deployed object,
metric or alert depends on these files, so a revert has no runtime effect. If only
the CI step is a problem (for example it slows or breaks the required `validate`
check), revert that one step and keep the doc and harness. Staged rollback for any
future live probe is specified in the spike doc and needs its own owner GO.
