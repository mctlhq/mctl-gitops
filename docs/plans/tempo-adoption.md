# Tempo adoption and eval-sandbox teardown (#1280 follow-up)

**Status: plan, awaiting owner approval. Nothing here is applied.**

ADR 0001 ("Agent execution trace backend") records the verdict **ADOPT
TEMPO / mctl-native only** from the #1280 soak. The soak window was closed
early by owner decision (ADR "Window amendment"), so the verdict rests on
293 h of the declared 324 h. The ADR also says adoption is not a promotion
in place: the permanent backend is a separate change with its own owner
approval. This plan is that change's proposal. Approve it, or change it,
before any manifest is written.

The teardown of the `observability-eval` sandbox is a separate pull request
too. It is described here because the two must be ordered.

## 1. The constraint that orders the work

`scripts/validate-eval-teardown-date.py` fails CI, on `main` as well, once
`otelCollector.eval.teardownAfter` (`2026-10-24`) is in the past while the
sandbox is enabled. So by **2026-10-24** one of these must be merged:

- **A. Teardown first (recommended).** Runbook steps 9–10 on 2026-10-24,
  as declared. Tracing is then off until adoption lands. The R2 bucket and
  its blocks stay, because Tempo was selected (runbook step 9), so the
  permanent Tempo starts on the soak's data.
- **B. Adoption first.** Merge the permanent deployment by 2026-10-24 and
  tear down after it. There is no tracing gap, but it needs this plan
  approved and implemented within two days.

Do not choose the third option, extending `teardownAfter`. The sandbox would
become a de facto permanent deployment, which the ADR rules out.

## 2. Teardown PR (runbook §9, Tempo selected)

One commit:

1. `otelCollector.eval.enabled: false`, the `tempo` candidate
   `enabled: false`, and `teardownAfter: ""`.
2. Keep `vm-rules/tempo-eval-alerts.yaml` and its route. They are silent
   without the sandbox, and the adoption PR renames them rather than
   recreating them (§3.6). This is runbook step 9.4's "Tempo selected" case.
3. Remove the producers' export, as both ADR producer amendments require,
   so nothing exports into a Collector with no trace backend:
   - `otel.enabled` in `services/admins/mctl-agents-worker/values.yaml`,
     `mctl-agents-worker-exec/values.yaml` and
     `mctl-agents-worker-implement/values.yaml`;
   - the `otel` block on `admins-mctl-agent` in
     `bootstrap/templates/mctl-platform/mctl-agent.yaml`.

   The investigate and implement pods need no change. They keep
   `MCTL_TRACE_REQUIRE_PARENT=true` and stay inert with no sampled parent.

Outside git, after Argo CD has pruned:

- Delete the "Tempo (eval)" datasource (`DELETE /api/datasources/uid/tempo-eval`).
  The Loki derived field `trace_id` points at it and stops resolving. The
  adoption PR repoints it (§3.5).
- **Keep** the `tempo-traces` bucket, its token and Vault
  `secret/platform/r2-tempo`. The permanent Tempo reuses them.
- Verify with runbook §10.

## 3. Adoption PR (owner gate)

Proposed shape. Each line is a decision to confirm or change.

1. **Home.** A dedicated `tracing` namespace with its own quota (0 PVCs) and
   NetworkPolicies, carried over from `infra-components/observability/eval/tempo/`.
   It goes through the normal bootstrap rather than the `eval.candidates`
   machinery, which exists to be torn down. Remember that a new namespace
   needs the selective-sync step for the root app (gitops#1925).
2. **Chart.** Keep community `tempo` `2.4.0` (Tempo `2.10.8`), the version
   measured. Moving to the 3.x line is its own change.
3. **Storage and retention.** The same R2 bucket `tempo-traces`, the same
   Vault path and `block_retention: 336h`, with the bucket's 30-day lifecycle
   as the backstop. The WAL stays on an `emptyDir`, because the default
   StorageClass is a billed volume. Losing up to about 5 minutes of
   unflushed spans on a pod reschedule therefore becomes a **standing**
   accepted risk, not a bake-off one. That needs the owner's explicit OK.
4. **Sizing and the read path.** This is the soak's main lesson. A
   full-window trace-by-id enumeration on about 200 blocks throttled the
   1-CPU pod to 80% and raised its working set to 898 MiB:
   - limits `2` CPU / `2Gi` memory, requests `200m` / `768Mi`,
     `GOMEMLIMIT=1600MiB`. That is +100m/+256Mi of requests over the
     sandbox, within the three cx43 workers with no new node;
   - querier `max_concurrent_queries: 4`, frontend
     `max_outstanding_per_tenant` and a trace-by-id `query_timeout`, so a
     heavy reader gets errors instead of starving the pod;
   - search stays limited to 168 h per query (the current default);
   - before relying on trace-by-id for anything that counts spans, find out
     why a bounded fetch returned 5,092 of 6,930 in-window spans in the
     soak (ADR Decision). That is open, and the adoption PR should not
     claim complete reads until it is explained.
5. **Grafana.** The datasource becomes "Tempo", uid `tempo`, with the same
   `tracesToLogsV2` mapping (namespace, pod, ±1m). The Loki derived field
   `trace_id` is repointed to `tempo`.
6. **Alerts.** Rename `TempoEval*` to `Tempo*`, and change the namespace
   selector and the Telegram route. Keep `TempoEvalObjectStorageErrors`'s
   `for: 10m`: the one natural R2 `PUT 500` in the soak correctly stayed
   pending.
7. **Collector.** Set `otelCollector.backendEndpoint` to
   `tempo.tracing.svc.cluster.local:4317`, the one-key swap in
   `docs/runbooks/otel-collector.md`. `backends` stays empty and `eval`
   stays off.
8. **Producers.** Re-enable exactly the two the soak covered: the
   `mctl-agents` DevLoop workers (`MCTL_TRACE_WORKFLOW_TYPES=DevLoopWorkflow`)
   and `admins-mctl-agent`. Any other producer (mctl-api, base-service
   releases) needs its own proposal.
9. **Not in scope.** FinOps cost per execution (`mctlhq/.github#48`) and
   evals (scored 0) stay mctl-native.

## 4. Done means

- The teardown PR is merged and runbook §10 is clean (no
  `observability-eval`, no `otel-eval` Application, no `otlp/eval-` in the
  render, no "Tempo (eval)" datasource).
- The adoption PR is merged on owner approval. A DevLoop and an
  `mctl-agent` ticket render as traces in "Tempo". Loki↔Tempo links work
  both ways. A trace from the soak, for example
  `431486061c652efb376a860d9d656f25`, is still readable from the reused
  bucket within retention.
