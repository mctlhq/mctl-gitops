# Tracing bake-off sandbox — operator runbook (issue #903 / #1280)

**This runbook is the procedure `mctlhq/mctl-gitops#1280` executes.**
`mctlhq/mctl-gitops#1355` (this commit) lands every piece of that procedure
that is writable and testable offline — a `ResourceQuota`/`LimitRange`, a
committed and pinned (but disabled) candidate catalogue, a collector
exporter fan-out derived from the enabled candidates, a redaction regression
test, and a CI-enforced teardown window. None of it changes cluster state:
`otelCollector.eval.enabled` and every `candidates[].enabled` are `false` as
merged. Opening the sandbox, running the soak, scoring the rubric and
tearing down are #1280's live half, not this proposal's.

Every control below is named by its exact key under `otelCollector.eval` in
`platform-gitops/bootstrap/values.yaml`.

## 1. Preconditions

Before flipping any flag, confirm all of the following:

- **Trace producers are emitting.** `mctlhq/mctl-agent#38` and
  `mctlhq/mctl-agents#195` are the two producers this collector was deployed
  ahead of (`docs/runbooks/otel-collector.md`). If neither has shipped, the
  soak has nothing real to measure beyond the fixture emitter (`wft-otel-trace-fixture`,
  see step 4) and the rubric's candidate UI cells cannot be filled from live
  traffic.
- **The status of #1332.** Run `python3 tests/test_otel_collector_redaction.py`
  and read its output. While `KNOWN_BROKEN_ISSUE = "mctlhq/mctl-gitops#1332"`
  is still set in that file, the collector's `redaction` processor strips
  the four `gen_ai.usage.*_tokens` counters the rubric's
  `ai_agent_observability` dimension is scored from — record this as a
  `0`-with-reason on that dimension's cells (step 4), not a silent skip.
- **Cluster headroom against the quota.** `otelCollector.eval.quota` reserves
  `requests.cpu: "4"`, `requests.memory: "12Gi"`, `limits.cpu: "8"`,
  `limits.memory: "20Gi"`, `pods: "30"`, `persistentvolumeclaims: "4"` and
  `requests.storage: "40Gi"` out of the three-cx43-worker cluster. Confirm
  free capacity for that reservation with `kubectl top nodes` before opening
  the namespace — this is a real bite out of shared capacity, not a
  rounding error.
- **Each candidate pin is resolvable and current.** `otelCollector.eval.candidates`
  today carries exactly one pinned, disabled candidate:

  | Candidate | Chart | targetRevision resolved | Status |
  |---|---|---|---|
  | `tempo` | `grafana/tempo-distributed` | `1.61.3` (resolved 2026-09-24 from `https://grafana.github.io/helm-charts/index.yaml`) | committed, `enabled: false` |
  | `agento11y` (candidate F, self-managed) | — | — | **not committed** |

  Candidate F's absence is deliberate, not an oversight: `agento11y`
  (`https://github.com/grafana/agento11y`) was confirmed at implementation
  time to be an SDK/hooks package that ships telemetry to a hosted Grafana
  Cloud stack — no Helm chart, Docker image or Kubernetes manifest of its
  own exists to pin. There is no self-managed shape to commit. Before
  running the soak with candidate F in scope, #1280 must either locate a
  genuine self-managed deployment shape (and add a candidate entry plus a
  `platform-gitops/infra-components/observability/eval/agento11y/` directory
  the same way `tempo`'s was added) or drop candidate F from the soak
  entirely and record that in the ADR's Decision section. Committing a
  Grafana Cloud endpoint or credential for it is explicitly out of scope
  everywhere in this repo (requirements.md "Out of scope").
- **The ADR/rubric is still frozen.** `python3 tests/test_adr_rubric_frozen.py`
  passes: every `dimensions[].candidates[].score` in
  `docs/adr/0001-rubric.yaml` is `null` and `verdict` is `null`. If this
  fails, something scored a cell before the soak declared its window
  (step 3) — stop and investigate before proceeding, do not silently
  continue the soak.

## 2. Open the sandbox

In **one commit**:

1. Set `otelCollector.eval.enabled: true`.
2. Set `otelCollector.eval.teardownAfter` to a `YYYY-MM-DD` date **at most 14
   days out** from the commit date. `scripts/validate-eval-teardown-date.py`
   (wired into `.github/workflows/validate-manifests.yml`) refuses anything
   else: missing, malformed, in the past, or more than 14 days out all fail
   CI, including on `push: [main]` with no open PR.
3. Flip `enabled: true` on exactly the named `otelCollector.eval.candidates[]`
   entries being soaked this round (e.g. `candidates[0].enabled` for
   `tempo`).

Do not open the sandbox and defer the `teardownAfter` date to "later" — the
CI check makes that impossible by design, and the runbook's honesty
requirement below makes it undesirable even if it were possible.

## 3. Declare the soak — before any measurement

Before looking at a single trace, write into
`docs/adr/0001-agent-execution-trace-backend.md`:

- the soak window (start and end timestamps);
- the target trace volume (e.g. "N DevLoop executions" or "N days of
  mctl-agent traffic").

This is the honesty control: a soak whose length is chosen after looking at
the data is not a measurement. If the window needs to change mid-soak, that
is a recorded amendment with a reason, never a silent extension.

## 4. Measurement sources, per rubric cell

`docs/adr/0001-rubric.yaml`'s six weighted dimensions, and where each one's
evidence comes from:

| Dimension | Weight | Source |
|---|---|---|
| `trace_reconstruction` | 25 | Candidate UI against the representative fixture `tests/fixtures/devloop-trace.json`, submitted via the registered `otel-trace-fixture` `ClusterWorkflowTemplate` (`platform-gitops/argo-workflows/cluster-templates/wft-otel-trace-fixture.yaml`) — parent/child tree, async/queue/Temporal/Argo visibility, search, error navigation. |
| `ai_agent_observability` | 25 | `gen_ai.usage.*` counters (input/output/cache/reasoning tokens) and the candidate's model/tool/session grouping UI. **Unmeasurable while #1332 is open** — record as a `0`-with-reason cell, not a skipped one, per step 1. |
| `data_ownership_portability` | 20 | The candidate's documented self-hosting licence (already recorded per-candidate in `docs/adr/0001-rubric.yaml`'s `stage_a`), plus a live check of raw data export and OTLP compatibility against the deployed candidate. |
| `operations` | 15 | `otelcol_exporter_*` series in VictoriaMetrics for exporter health (send failures, queue size/capacity — same metrics `docs/runbooks/otel-collector.md`'s verification commands already query); `kubectl top` and the quota's own `status.used` (`kubectl -n observability-eval get resourcequota observability-eval-quota`) for the operations footprint against `otelCollector.eval.quota`. |
| `security_privacy` | 10 | `tests/test_otel_collector_redaction.py`'s output (what is and is not redacted before it ever reaches the candidate) plus a check of the candidate's own storage of prompts/completions/credentials. |
| `evals_quality_loop` | 5 | Whether the candidate can attach a deterministic or LLM-eval score to a submitted execution, checked against the fixture from `trace_reconstruction` above. |

## 5. Score and promote

Fill the null cells in `docs/adr/0001-rubric.yaml`, apply `decision_rule`,
pick exactly one of the seven `permitted_verdicts`, and write the ADR's
Decision section. `tests/test_adr_rubric_frozen.py` stops enforcing the
freeze the moment scores are non-null — that is expected; the freeze exists
to keep this proposal (#1355) from pre-empting the decision, not to block
#1280 from making it.

## 6. Teardown — one commit

In the **same single commit**:

1. `otelCollector.eval.enabled: false`.
2. Every `otelCollector.eval.candidates[].enabled: false`.
3. `otelCollector.eval.teardownAfter: ""`.

Because the bootstrap Application syncs with `prune: true`
(`platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml`)
and each candidate Application carries its own
`finalizers: [resources-finalizer.argocd.argoproj.io]` and
`syncPolicy.automated.prune: true`, this one commit cascades: the candidate
Applications (and their workloads and PVCs) go first, then the
`ResourceQuota`, the `LimitRange`, the four `NetworkPolicy` objects and the
`observability-eval` Namespace itself.

Do not revert the PRs that opened the sandbox instead of running this
teardown — see `docs/runbooks/tracing-bake-off.md`'s own rollback case 4
(this runbook, this section) and `tasks.md`'s Rollback section in the
originating proposal: reverting templates while ArgoCD still holds live
candidate Applications orphans them.

## 7. Verify nothing is left running

```bash
# Namespace gone
kubectl get ns observability-eval   # expect: NotFound

# No candidate Applications left in ArgoCD
kubectl -n argocd get applications | grep otel-eval   # expect: no output

# No PersistentVolumes left behind (PVCs go with the namespace; a Retain
# reclaim policy on the underlying StorageClass would leave the PVs)
kubectl get pv | grep observability-eval   # expect: no output

# The collector's traces pipeline back to its pre-soak state
helm template test platform-gitops/bootstrap -f platform-gitops/bootstrap/values.yaml \
  | grep -A5 'exporters:$' | grep -c 'otlp/eval-'   # expect: 0
```

If any of these still shows the sandbox, the teardown commit above has not
fully reconciled yet, or something outside this procedure re-enabled a
flag — do not consider the spike closed until every check above is clean.
