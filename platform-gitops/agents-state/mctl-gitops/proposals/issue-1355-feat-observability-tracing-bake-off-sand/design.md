# Design: issue-1355-feat-observability-tracing-bake-off-sand

## Current state

### The gated evaluation templates (#903, already merged)

`platform-gitops/bootstrap/templates/observability/eval-namespace.yaml` renders,
under a single `{{- if .Values.otelCollector.eval.enabled }}` guard (line 9,
closed at line 147):

- a `Namespace` `observability-eval` with label `mctl.ai/purpose:
  issue-903-spike` and annotation `mctl.ai/teardown-after` sourced from
  `.Values.otelCollector.eval.teardownAfter` (line 20);
- four `NetworkPolicy` objects: `default-deny-all` (`podSelector: {}`),
  `allow-intra-namespace`, `allow-cluster-egress` (DNS to `kube-system`, the
  pod/service CIDRs minus the node subnets, a 6443 carve-out for
  `kubernetes.default`), and `allow-ingress-from-monitoring` restricted to TCP
  4317/4318 from the `monitoring` namespace.

There is **no `ResourceQuota` and no `LimitRange`** in that file, and none
anywhere else for `observability-eval`. The only quota/limit precedent in the
repo is the tenant chart:
`platform-gitops/helm-charts/tenant/templates/resourcequota.yaml` (a flat
`range $key, $val := .Values.tenant.quotas` into `spec.hard`, every value
quoted) and `templates/limitrange.yaml` (a `type: Container` entry with
`default`, `defaultRequest` and `max`, gated on
`.Values.tenant.limitRange.enabled`). Their default values live at
`platform-gitops/helm-charts/tenant/values.yaml:22-35` and `:70-81`.

`eval-candidates.yaml` renders one ArgoCD `Application` per entry of
`.Values.otelCollector.eval.candidates` (line 25), inside the same
`eval.enabled` guard. Each entry is `{name, repoURL, chart, targetRevision,
manifestsPath, values}`; `manifestsPath` switches the Application from a single
`source` to a two-element `sources` list whose second element points back at
this repo. `syncPolicy.automated.prune: true`, `selfHeal` deliberately omitted
(line 70-72 explains why: #1280 must be able to `kubectl scale --replicas=0` a
candidate for the outage test). **There is no per-candidate flag** — the list is
all-or-nothing — and `platform-gitops/bootstrap/values.yaml:43` ships
`candidates: []`, so no pin is committed anywhere.

### The collector and its fan-out

`platform-gitops/bootstrap/templates/observability/otel-collector.yaml` is an
ArgoCD `Application` whose first source is the upstream
`opentelemetry-collector` chart at `0.173.0`, image
`otel/opentelemetry-collector-contrib:0.160.0`, with the whole collector config
inlined under `helm.values` (lines 27-287). The traces pipeline is
`receivers: [otlp]`, processors `memory_limiter -> k8sattributes -> resource ->
redaction -> filter/health -> batch`, exporters `debug` plus, conditionally,
`otlp/backend` (from the scalar `.Values.otelCollector.backendEndpoint`, line
217) and one `otlp/<name>` per entry of `.Values.otelCollector.backends` (the
`range` at line 241, mirrored in the pipeline list at line 285).

So a generalized fan-out already exists — but it is driven by a **second list**,
`otelCollector.backends`, which has no relationship to
`otelCollector.eval.candidates`. Today an operator who wants to evaluate
candidate X must add X to `eval.candidates` (to deploy it) and separately to
`backends` (to send it spans), with the endpoint hand-typed and nothing checking
the two agree. `tests/fixtures/otel-eval-candidates.example-values.yaml` is the
worked two-entry overlay that demonstrates exactly this duplication
(`backends[].name: candidate-a/candidate-b` and `eval.candidates[].name:
candidate-a/candidate-b`, kept in sync by hand).

### Redaction

`redaction` runs with `allow_all_keys: true` and these
`blocked_key_patterns` (lines 178-185):

```
(?i).*(authorization|cookie|api[-_]?key|token|secret|password|credential).*
(?i)^vault\..*
(?i)^gen_ai\.(prompt|completion).*
(?i).*\.messages$
(?i)^mcp\.tool\.(arguments|result)$
^db\.statement$
^http\.(request|response)\.header\..*
```

The first pattern contains the bare alternative `token`, wrapped in `.*` on both
sides. It therefore matches `gen_ai.usage.input_tokens`,
`gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read_input_tokens` and
`gen_ai.usage.reasoning_tokens` — the four attributes
`tests/test_devloop_trace_fixture.py:41-43` requires the representative fixture
to carry, and the exact counters the rubric's `ai_agent_observability`
dimension (`docs/adr/0001-rubric.yaml`, weight 25) is scored from. That is
#1332. Nothing in the repo tests it: `tests/test_devloop_trace_fixture.py` T4
only asserts the *poisoned* fixture's four attributes **are** matched
(line 123), never that anything survives. The collector compiles these with Go
RE2, which has no negative lookahead, so the eventual fix has to be a rewritten
alternation (e.g. anchoring `token` so it cannot match inside `_tokens`), not a
lookahead.

### CI

`.github/workflows/validate-manifests.yml` runs on `pull_request` and on
`push: [main]`. It already has an eval-specific render step (lines 99-109,
`helm template` with the example overlay through `kubeconform`) and four
issue-903 unit-test steps (lines 399-437). The repo-wide convention for a
detector script is `--selftest` first, then the real run — stated explicitly at
lines 154-159, 168-171, 191-198, 205-207, 228-231 and 251-257 ("a detector that
has never been seen to fire is not known to work"). `scripts/` holds nine
`validate-*.py` detectors following that shape; `scripts/validate-openclaw-version-pin.py`
is the closest template (reads YAML under `platform-gitops/`, yields
mismatches, `--selftest` builds a throwaway tree).

`tests/test_otel_collector_backends_render.py` is the render harness: plain
`python3`, no pytest, a `check()`/`failures` accumulator, a `helm_template()`
helper and a `collector_config()` helper that pulls the config back out of the
Application's `spec.sources[0].helm.values`. T1 compares the default render
against the committed golden file `tests/fixtures/otel-collector-config-default.yaml`
and prints the `--write-golden` regeneration command on failure.

### Runbook and rubric

`docs/runbooks/otel-collector.md` documents the collector, the fan-out overlay
shape, the eval namespace gate and the fixture emitter (lines 199-229), plus
verification commands and accepted residuals. There is **no
`docs/runbooks/tracing-bake-off.md`**. `docs/adr/0001-rubric.yaml` is frozen:
five candidates, six weighted dimensions summing to 100, every score `null`,
`verdict: null`, a `stage_a` paper screen where only `tempo` is `SURVIVES` and
`traceway`/`langfuse`/`phoenix` are `UNVERIFIED`.
`tests/test_adr_rubric_frozen.py` enforces the freeze, the weight agreement with
the ADR's Markdown table, and the "no `issue-903-body` row may be `SURVIVES`"
rule.

## Proposed solution

Six changes, all inside the existing `otelCollector.eval` key, all off by
default.

### 1. `ResourceQuota` and `LimitRange`, inside the existing guard

Append both objects to `eval-namespace.yaml` inside the `eval.enabled` block
(rather than a new file) so they cannot exist without the namespace and cannot
outlive it. Shape copied from the tenant chart:

```yaml
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: observability-eval-quota
  namespace: observability-eval
spec:
  hard:
    {{- range $key, $val := .Values.otelCollector.eval.quota }}
    {{ $key }}: {{ $val | quote }}
    {{- end }}
---
apiVersion: v1
kind: LimitRange
metadata:
  name: observability-eval-limits
  namespace: observability-eval
spec:
  limits:
    - type: Container
      default: { cpu/memory from .eval.limits.default }
      defaultRequest: { ... .eval.limits.defaultRequest }
      max: { ... .eval.limits.max }
```

`platform-gitops/bootstrap/values.yaml` gains, under `otelCollector.eval`:

```yaml
    quota:
      requests.cpu: "4"
      requests.memory: "12Gi"
      limits.cpu: "8"
      limits.memory: "20Gi"
      pods: "30"
      persistentvolumeclaims: "4"
      requests.storage: "40Gi"
    limits:
      default:        { cpu: "1",    memory: "2Gi" }
      defaultRequest: { cpu: "100m", memory: "256Mi" }
      max:            { cpu: "4",    memory: "8Gi" }
```

The two caps the issue fixes (`persistentvolumeclaims: 4`,
`requests.storage: 40Gi`) get a dedicated literal assertion in the render test,
not just "the quota rendered" — the whole point is that a later values edit
widening them fails CI. `requests.storage` is the key that matters most here:
ClickHouse-backed candidates (Langfuse, SigNoz per the rubric's `stage_a`
dependency rows) will otherwise claim whatever the chart's default PVC size is,
on a cluster whose only current object-storage user is Loki on Cloudflare R2.

### 2. Per-candidate flags and committed pins

Keep `otelCollector.eval.candidates` as the list shape `eval-candidates.yaml`
already ranges over, but change it from an empty list supplied by the operator
into a **committed catalogue of disabled, pinned candidates**, each gaining
three fields:

```yaml
    candidates:
      - name: tempo
        enabled: false                 # <- the per-candidate flag
        repoURL: https://grafana.github.io/helm-charts
        chart: tempo-distributed
        targetRevision: "<resolved at implementation time>"
        manifestsPath: platform-gitops/infra-components/observability/eval/tempo
        otlpEndpoint: "tempo-distributed-distributor.observability-eval.svc.cluster.local:4317"
        insecure: true
      - name: agento11y-self-managed
        enabled: false
        ...
```

`eval-candidates.yaml` changes exactly one line: `{{- range
.Values.otelCollector.eval.candidates }}` gains `{{- if .enabled }}` … `{{- end
}}` inside it. The outer `eval.enabled` guard is unchanged and still dominates,
so a per-candidate flag on with the sandbox off renders nothing — which is what
makes "enabled: false everywhere" byte-identical to today's render.

The per-candidate manifest set lives at
`platform-gitops/infra-components/observability/eval/<candidate>/`, which is
exactly the `manifestsPath` convention `eval-candidates.yaml:36-52` was written
for and which `tests/fixtures/otel-eval-candidates.example-values.yaml:36`
already references as "created later". Each directory holds the candidate's
supporting objects (the chart-value fragment, any `VMServiceScrape`, and the
`serviceMonitor/podMonitor: false` overrides the `eval-candidates.yaml` header
at lines 14-23 demands because vmagent runs `selectAllByDefault: true` —
incident #1159).

Candidate selection, per `requirements.md`'s first open question: `tempo` (the
only `SURVIVES` row) and `agento11y` self-managed (named by the issue).
`agento11y`'s Grafana Cloud shape gets **no directory and no candidate entry** —
it is an endpoint plus a token, so its only footprint would be an
`otelCollector.backends` entry whose `headers` is an `${env:...}` expansion,
which #1280 adds at soak time. `docs/adr/0001-rubric.yaml` is not touched, so
`tests/test_adr_rubric_frozen.py`'s `EXPECTED_CANDIDATES` and the score freeze
stay exactly as they are and the acceptance criterion "no non-null rubric score
cell is committed" is satisfied by construction.

### 3. Fan-out derived from enabled candidates

`otel-collector.yaml` gains a second `range`, after the existing
`.Values.otelCollector.backends` block, over the enabled eval candidates that
declare an `otlpEndpoint`:

```gotemplate
{{- if .Values.otelCollector.eval.enabled }}
{{- range .Values.otelCollector.eval.candidates }}
{{- if and .enabled .otlpEndpoint }}
              otlp/eval-{{ .name }}:
                endpoint: {{ .otlpEndpoint | quote }}
                ... tls/headers/sending_queue/retry_on_failure, same shape as
                    the backends block at lines 241-261
{{- end }}
{{- end }}
{{- end }}
```

with the mirror in the pipeline exporter list after line 287. The `eval-`
prefix guarantees no collision with an operator-supplied `backends[].name`.

This is the change that makes "a candidate is deployed" and "a candidate
receives spans" one flag instead of two hand-synced lists. `backends` is left
untouched and still renders — the runbook's one-key-swap procedure and the
existing T2 legacy-scalar regression both keep passing unchanged — it simply
stops being the mechanism the bake-off uses.

The render test gains three cases: all flags off (no `otlp/eval-*` exporter, the
traces pipeline exporter list still exactly `["debug"]`, i.e. the existing T1
golden comparison already covers it); one flag on (exactly one extra exporter,
and a structural diff of the traces pipeline against the default render showing
the **only** difference is that one appended exporter — receivers and the
ordered processor list byte-equal); a literal (non-`${env:`) header value fails.

### 4. Redaction regression test

New `tests/test_otel_collector_redaction.py`, same plain-`python3` shape as its
two siblings. It renders the default config, reads
`config.processors.redaction.blocked_key_patterns`, compiles each with Python
`re` (every committed pattern is RE2-compatible and also valid Python, so this
evaluates the real strings rather than a paraphrase), and evaluates two fixed
key lists:

- `MUST_BE_BLOCKED = ["github_token", "authorization", "api_key", "vault.token"]`
  — hard assertion, always. All four match today.
- `MUST_SURVIVE = ["gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
  "gen_ai.usage.cache_read_input_tokens", "gen_ai.usage.reasoning_tokens"]`
  — currently blocked by pattern 1, so this half is wrapped in a declared
  expected failure:

```python
KNOWN_BROKEN_ISSUE = "mctlhq/mctl-gitops#1332"   # set to None once fixed
```

With the marker set and the keys still blocked, the test prints
`EXPECTED FAILURE (mctlhq/mctl-gitops#1332): gen_ai.usage.* still redacted by
<pattern>` and exits 0. With the marker set and the keys surviving, it **fails**
with "set `KNOWN_BROKEN_ISSUE = None`" — an xfail-strict, so the marker cannot
outlive the bug. With the marker cleared and the keys blocked, it fails
normally. The blocked half never participates in the marker, so #1332 can never
be used as cover for a weakened credential block list.

Wired into `validate-manifests.yml` as its own step next to the existing
issue-903 test steps (after line 418).

### 5. Teardown enforcement

`scripts/validate-eval-teardown-date.py`, in the house detector style:

- reads `platform-gitops/bootstrap/values.yaml`;
- if `otelCollector.eval.enabled` is not `true`, pass (the sandbox is closed;
  `teardownAfter` is then free to be `""`);
- else require `teardownAfter` to parse as `YYYY-MM-DD` via
  `datetime.date.fromisoformat`, be `>= today`, and be `<= today + 14 days`;
- `--today YYYY-MM-DD` injects the date so the selftest is deterministic;
- `--selftest` builds throwaway values files and asserts all five branches:
  disabled+empty passes, enabled+future-within-14d passes, enabled+empty fails,
  enabled+yesterday fails, enabled+today+30d fails.

Wired into `validate-manifests.yml` as `--selftest` then the real run, matching
every other detector in that job. Because the job also triggers on
`push: [main]`, an expired sandbox turns main red even with no open PR — the
same reasoning the workflow's own header comment gives for the openclaw pin
check (lines 6-16).

The one-commit teardown is a documentation deliverable, not code: `eval.enabled:
false` + every `candidates[].enabled: false` + `teardownAfter: ""` in one commit.
Because the bootstrap Application syncs with `prune: true`
(`applicationset-apps.yaml:57`) and each candidate Application carries
`finalizers: [resources-finalizer.argocd.argoproj.io]` with its own
`prune: true`, that single commit deletes the candidate Applications (and
cascades to their workloads and PVCs), then the quota, the limits, the four
NetworkPolicies and the Namespace itself.

### 6. `docs/runbooks/tracing-bake-off.md`

New runbook, structured as the procedure #1280 executes, following the section
style of `docs/runbooks/otel-collector.md`:

1. **Preconditions** — trace producers emitting (mctl-agent#38 / mctl-agents#195),
   the status of #1332 read from the CI output of
   `tests/test_otel_collector_redaction.py`, cluster headroom against the quota
   in §2, each candidate pin resolvable, and the ADR/rubric still frozen.
2. **Open the sandbox** — set `otelCollector.eval.enabled: true` and
   `otelCollector.eval.teardownAfter` to a date at most 14 days out **in the
   same commit**; the CI check refuses anything else. Then flip the named
   per-candidate flags.
3. **Declare the soak** — the window (start/end timestamps) and the target trace
   volume, written into the ADR **before** any measurement. This is the honesty
   control: a soak whose length is chosen after looking at the data is not a
   measurement.
4. **Measurement sources per rubric cell** — a table mapping each of the six
   `docs/adr/0001-rubric.yaml` dimensions to where its evidence comes from
   (`otelcol_exporter_*` series in VictoriaMetrics for exporter health;
   `kubectl top` / the quota's own `status.used` for the operations footprint;
   the candidate UI against the representative fixture
   `tests/fixtures/devloop-trace.json` submitted via the `otel-trace-fixture`
   ClusterWorkflowTemplate for trace reconstruction; `gen_ai.usage.*` counters
   for AI/agent observability — explicitly **unmeasurable while #1332 is open**,
   which is recorded as a `0`-with-reason rather than silently skipped).
5. **Score and promote** — fill the null cells, apply `decision_rule`, pick one
   of the seven `permitted_verdicts`, write the ADR Decision section.
6. **Teardown** — the one commit from §5 above.
7. **Verify nothing is left** — `kubectl get ns observability-eval` (expect
   NotFound), `kubectl -n argocd get applications | grep otel-eval` (expect
   none), `kubectl get pv | grep observability-eval` (expect none — the PVCs
   went with the namespace but a `Retain` reclaim policy would leave the PVs),
   and the collector's rendered exporter list back to `["debug"]`.

Every control is named by its exact values key. `docs/runbooks/otel-collector.md`
gets a one-line cross-reference from its "evaluation namespace" section.

## Alternatives

**A separate `eval.fanout` list instead of deriving exporters from candidates.**
Keeps `eval-candidates.yaml` and `otel-collector.yaml` decoupled and matches the
existing `otelCollector.backends` shape exactly. Dropped: it reproduces the
present defect. Two hand-synced lists is how you get a candidate that is running
and receiving nothing (silently scores 0 on every dimension) or one that is
torn down while the collector keeps exporting to a dead endpoint (queue fills,
`otelcol_exporter_send_failed_spans` climbs, and the alert fires against
`monitoring` rather than the sandbox). One flag is the fix.

**A separate `eval-quota.yaml` template file.** Cleaner file-per-object
separation, matching `helm-charts/tenant/` where the quota and limit range are
their own templates. Dropped: separation buys nothing here and costs the
strongest guarantee available — putting the quota inside the namespace file's
existing `if` makes "the namespace exists without a quota" unrepresentable in
the template, rather than a second `if` somebody can forget to flip. The tenant
chart splits them because its quota is independently toggleable per tenant;
this one is not.

**A Kubernetes-side teardown mechanism (a `Job` with a TTL, or an
`argocd.argoproj.io/sync-wave` deletion hook) instead of a CI check.** Actually
tears the namespace down rather than just complaining. Dropped for two reasons:
a self-deleting Application fights its own GitOps source of truth — ArgoCD
would resync the namespace straight back while `eval.enabled` is still `true` —
and a cron-style deletion job inside the sandbox needs RBAC to delete a
namespace, which is a far larger grant than this spike justifies. The CI check
is honest about what it is: a gate that makes the abandoned state loud, with the
teardown itself staying a reviewed commit.

**Committing the three `UNVERIFIED` candidates' manifest sets too.** Would make
#1280 purely a values edit for any of five backends. Dropped: #903's own
`stage_a` rows say the chart coordinates, licences and dependency sets for
Traceway, Langfuse and Phoenix could not be verified, and the whole point of the
`UNVERIFIED` verdict is that a pin resting on nothing must not be committed into
a repository ArgoCD treats as truth. Recorded as an open question instead.

## Platform impact

**Migrations.** None. `otelCollector.eval.quota`, `.limits` and
`candidates[].enabled`/`.otlpEndpoint` are new keys with committed defaults;
nothing reads them today. The existing `otelCollector.backends` contract is
unchanged, so `docs/runbooks/otel-collector.md`'s documented overlay shape and
the T2 legacy-scalar regression continue to hold.

**Backward compatibility — one deliberate break.**
`tests/fixtures/otel-eval-candidates.example-values.yaml`'s two candidate
entries carry no `enabled` key, so once `eval-candidates.yaml` gates on
`.enabled` they would render nothing and the existing T5 assertion "expected two
candidate Applications" would fail. The fixture must gain `enabled: true` on
both entries in the same commit. This is the correct direction (the fixture's
job is to exercise the on-state) but it is a coupled edit, and the
`kubeconform` step at `validate-manifests.yml:99-109` consumes the same fixture.
An implementer who changes the template and not the fixture gets a red CI, not
a silent regression.

**Resource impact while off:** zero. With `eval.enabled: false` the rendered
bootstrap output is byte-identical to `main`, which the existing golden-file
check (`tests/test_otel_collector_backends_render.py` T1 against
`tests/fixtures/otel-collector-config-default.yaml`) proves rather than asserts.
CI grows by two steps (one detector with a selftest, one render test), both
pure-Python against `helm template`, adding well under a minute.

**Resource impact when #1280 opens it:** bounded by the new quota —
`requests.cpu: 4`, `requests.memory: 12Gi`, 4 PVCs, 40Gi of storage, on a
three-cx43-worker cluster. That is deliberately a real bite out of the cluster,
which is why §1 of the runbook makes headroom a precondition, and why the
14-day teardown window is enforced rather than suggested.

**Risks and mitigations.**

- *An unresolvable chart pin.* The implementer may not be able to reach
  `https://grafana.github.io/helm-charts` to resolve `tempo-distributed`'s
  current version. Mitigation: a candidate whose pin cannot be verified is not
  committed; its absence is recorded in the runbook's precondition section. The
  quota, fan-out, redaction test, teardown check and runbook all land
  regardless — none of them depends on a candidate existing. Committing a
  guessed `targetRevision` would be the worst outcome and is explicitly refused.
- *The golden file drifts.* Any edit to the collector config template that
  changes the default render fails T1 with the `--write-golden` regeneration
  command printed. The new fan-out `range` is inside `{{- if
  .Values.otelCollector.eval.enabled }}`, so with the default values it emits
  nothing and the golden file needs no regeneration; if it does need one, that
  is the signal the change was not inert after all.
- *The expected-failure marker becomes permanent.* Mitigated by the
  xfail-strict direction: the moment #1332 is fixed, the test fails until the
  marker is removed. A marker that silently stayed green after the fix would be
  the failure mode worth designing against, and it cannot happen.
- *Double-scrape (#1159) from a candidate chart's own ServiceMonitor.* vmagent
  runs `selectAllByDefault: true` (`monitoring.yaml:287`), so a candidate chart
  shipping a `ServiceMonitor` preset gets discovered alongside any hand-written
  scrape. Mitigated by committing each candidate's `serviceMonitor.enabled:
  false` / `podMonitor.enabled: false` override in its
  `infra-components/observability/eval/<candidate>/` fragment, exactly as
  `otel-collector.yaml:84-87` already does for the collector itself, and as the
  `eval-candidates.yaml` header (lines 14-23) demands.
- *A credential entering the repo via a candidate's `headers`.* Mitigated by
  keeping the existing `${env:...}`-only rule and adding a render-test
  assertion that fails on a literal header value, extending
  `test_otel_collector_backends_render.py`'s existing candidate-b check to the
  eval-derived exporters.
