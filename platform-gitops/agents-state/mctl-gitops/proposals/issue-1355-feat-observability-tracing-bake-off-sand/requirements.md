# Tracing bake-off sandbox: quota, candidate manifests, fan-out, teardown guard and runbook

## Context

Issue #1355 is the reproducible config slice split out of #1280 on 2026-09-24,
after the first implementer run on #1280 ended `no-commits` because that
proposal mixed gitops/config work (writable and testable offline) with
live-cluster measurement (not). #903 already landed the inert half of the
spike: `platform-gitops/bootstrap/templates/observability/eval-namespace.yaml`
(the `observability-eval` Namespace plus four NetworkPolicies),
`eval-candidates.yaml` (one ArgoCD Application per
`otelCollector.eval.candidates` entry), the generalized `otelCollector.backends`
fan-out in `otel-collector.yaml`, the frozen rubric `docs/adr/0001-rubric.yaml`,
and four CI gates in `.github/workflows/validate-manifests.yml`.

What is still missing is everything that turns that skeleton into a sandbox an
operator can open in one commit and is forced to close again: there is no
`ResourceQuota` or `LimitRange` on `observability-eval`, so an evaluation
candidate can consume the whole three-worker preprod cluster; there is no
per-candidate flag, so `eval.candidates` is all-or-nothing and the pins #1280
needs are not committed anywhere; the fan-out is driven by a second,
hand-duplicated `otelCollector.backends` list rather than by the candidates
themselves; `otelCollector.eval.teardownAfter` is a greppable string that
nothing enforces; there is no test that the collector's `redaction` processor
keeps the `gen_ai.usage.*` token counters the AI/agent-observability rubric
dimension is scored from (that is #1332, and today's committed
`blocked_key_patterns` entry `(?i).*(...|token|...).*` does match
`gen_ai.usage.input_tokens`); and there is no operator runbook for the
procedure #1280 executes. This proposal adds exactly those six things, all
off by default, all merged inert.

## User stories

- AS a platform operator I WANT the `observability-eval` namespace to carry a
  `ResourceQuota` and a `LimitRange` the moment it exists SO THAT a candidate
  chart with a generous default `StatefulSet` cannot starve `monitoring`,
  `argo-workflows` or the tenants on the same three cx43 workers.
- AS a platform operator I WANT each bake-off candidate committed as a
  pinned, individually flagged manifest set SO THAT opening the sandbox for
  one candidate is a one-line values edit against manifests that were already
  reviewed and schema-validated, not a fresh authoring exercise under time
  pressure.
- AS a platform operator I WANT the collector's exporter fan-out derived from
  the enabled candidates SO THAT a candidate cannot be running with nothing
  sent to it, or sent spans after its flag was turned off.
- AS a platform engineer I WANT a redaction regression test wired into
  `validate-manifests.yml` SO THAT the `gen_ai.usage.*` counters and the
  credential block list are both a check rather than a claim, and #1332's
  status is visible in CI instead of in a comment.
- AS a repository owner I WANT a CI check that fails once
  `otelCollector.eval.teardownAfter` has passed while `eval.enabled` is still
  true SO THAT a two-week spike namespace cannot become silently permanent.
- AS the operator running #1280 I WANT `docs/runbooks/tracing-bake-off.md` to
  name every flag and every measurement source SO THAT the live half is a
  procedure to execute rather than a design to re-derive.

## Acceptance criteria (EARS)

### Inertness

- WHILE `otelCollector.eval.enabled` is `false` and every per-candidate flag is
  `false` THE SYSTEM SHALL render `helm template test platform-gitops/bootstrap
  -f platform-gitops/bootstrap/values.yaml` byte-identically to the same command
  on `main` before this change.
- WHILE `otelCollector.eval.enabled` is `false` THE SYSTEM SHALL render no
  `Namespace`, `ResourceQuota`, `LimitRange`, `NetworkPolicy` or ArgoCD
  `Application` targeting `observability-eval`.
- WHEN `.github/workflows/validate-manifests.yml` runs THE SYSTEM SHALL assert
  that byte-identity by comparing the default-values collector render against
  the committed golden file `tests/fixtures/otel-collector-config-default.yaml`
  (the existing T1 check in `tests/test_otel_collector_backends_render.py`) and
  by asserting the absence of every `observability-eval` object.

### Sandbox quota and limits

- WHEN `otelCollector.eval.enabled` is `true` THE SYSTEM SHALL render, into
  namespace `observability-eval`, a `ResourceQuota` whose `spec.hard` is taken
  from `otelCollector.eval.quota` and a `LimitRange` whose container defaults
  are taken from `otelCollector.eval.limits`.
- WHILE the sandbox is rendered THE SYSTEM SHALL cap
  `persistentvolumeclaims` at `4` and `requests.storage` at `40Gi`.
- WHEN the render test runs THE SYSTEM SHALL assert both of those two values
  literally, so a values edit that widens them fails CI rather than merging.
- IF an operator overrides `otelCollector.eval.quota` in a way that removes
  either of those two keys THEN THE SYSTEM SHALL fail the render test.

### Candidate manifests

- THE SYSTEM SHALL commit one manifest set per candidate whose `stage_a`
  verdict in `docs/adr/0001-rubric.yaml` is `SURVIVES` (today: `tempo` only),
  plus candidate F `agento11y` in its self-managed shape as named by the issue.
- WHILE this proposal is merged THE SYSTEM SHALL leave every per-candidate flag
  at `false`, so no candidate is enabled by this change.
- WHEN a candidate entry is committed THE SYSTEM SHALL carry a concrete,
  non-empty `targetRevision` (chart version) and, where the manifest set pins an
  image, a concrete image tag — never `latest`, never a floating range.
- WHEN candidate F is committed THE SYSTEM SHALL commit only the self-managed
  shape; the Grafana Cloud shape SHALL render no in-cluster manifests and is
  evaluated under #1280.
- IF a candidate's per-candidate flag is `true` while
  `otelCollector.eval.enabled` is `false` THEN THE SYSTEM SHALL render nothing
  for it (the namespace guard dominates) and the teardown-date check SHALL not
  fire.
- WHEN the render test runs with exactly one candidate flag on THE SYSTEM SHALL
  assert exactly one ArgoCD `Application` targets `observability-eval`.

### Collector fan-out

- WHILE every per-candidate flag is `false` THE SYSTEM SHALL render no
  candidate exporter and leave the traces pipeline's exporter list exactly
  `["debug"]` (plus `otlp/backend` when the pre-existing
  `otelCollector.backendEndpoint` scalar is set).
- WHEN exactly one candidate flag is `true` THE SYSTEM SHALL render exactly one
  additional OTLP exporter for that candidate, append it to the traces
  pipeline's exporter list, and leave every other key of the production
  pipeline — receivers, the ordered processor list, `debug`, `otlp/backend` —
  unchanged.
- WHEN a candidate exporter renders THE SYSTEM SHALL give it its own
  `sending_queue` and `retry_on_failure` block, matching the existing
  `otelCollector.backends` behaviour.
- IF a candidate entry carries `headers` THEN THE SYSTEM SHALL require every
  header value to be a `${env:...}` expansion expression, and the render test
  SHALL fail on a literal value.
- WHILE `otelCollector.backends` is non-empty THE SYSTEM SHALL keep rendering
  those exporters unchanged, so the procedure documented in
  `docs/runbooks/otel-collector.md` stays literally true.

### Redaction regression test

- WHEN `tests/test_otel_collector_redaction.py` runs THE SYSTEM SHALL render
  the collector config through `helm template` and evaluate the committed
  `redaction.blocked_key_patterns` against a fixed key list.
- THE SYSTEM SHALL assert that `github_token`, `authorization`, `api_key` and
  `vault.token` are each matched by at least one blocked pattern.
- THE SYSTEM SHALL assert that `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read_input_tokens` and
  `gen_ai.usage.reasoning_tokens` are matched by no blocked pattern.
- IF #1332 is still unfixed at merge time (today it is: the committed pattern
  `(?i).*(authorization|cookie|api[-_]?key|token|secret|password|credential).*`
  matches every `*_tokens` key) THEN THE SYSTEM SHALL commit the surviving-keys
  half as a declared expected failure that names `mctlhq/mctl-gitops#1332` in
  its output and exits `0`.
- WHEN #1332 is fixed and the four counters survive THE SYSTEM SHALL fail with
  an instruction to clear the expected-failure declaration, so the marker
  cannot outlive the bug.
- WHEN the expected failure is active THE SYSTEM SHALL still hard-fail on the
  blocked half, so the credential block list is never weakened under cover of
  #1332.
- WHEN `.github/workflows/validate-manifests.yml` runs THE SYSTEM SHALL run
  this test.

### Teardown

- WHEN `scripts/validate-eval-teardown-date.py` runs against a
  `platform-gitops/bootstrap/values.yaml` where `otelCollector.eval.enabled` is
  `true` THE SYSTEM SHALL fail if `teardownAfter` is empty, is not a
  `YYYY-MM-DD` date, is earlier than today, or is more than 14 days after today.
- WHILE `otelCollector.eval.enabled` is `false` THE SYSTEM SHALL pass
  regardless of the value of `teardownAfter`.
- WHEN the script is invoked with `--selftest` THE SYSTEM SHALL prove both
  states — a passing configuration and an expired one — against throwaway
  fixtures, matching the `--selftest`-first convention every other detector in
  `validate-manifests.yml` follows.
- THE SYSTEM SHALL document a one-commit teardown in the runbook: setting
  `otelCollector.eval.enabled: false`, every per-candidate flag `false` and
  `teardownAfter: ""` in one commit removes every candidate Application, the
  quota, the limits, the NetworkPolicies and the namespace.

### Runbook

- THE SYSTEM SHALL add `docs/runbooks/tracing-bake-off.md` covering, in order:
  the precondition check (including the state of #1332 and of the trace
  producers), opening the sandbox and setting `teardownAfter` to at most 14 days
  out, declaring the soak window and target trace volume **before** any
  measurement, the source of each rubric cell's measurement, the scoring and ADR
  promotion steps, teardown, and post-teardown verification that nothing is left
  running.
- WHEN the runbook names a control THE SYSTEM SHALL name it by its exact values
  key (`otelCollector.eval.enabled`, `otelCollector.eval.teardownAfter`,
  `otelCollector.eval.quota`, `otelCollector.eval.limits`, and each
  per-candidate flag by name).
- WHILE this proposal is merged THE SYSTEM SHALL leave every
  `dimensions[].candidates[].score` in `docs/adr/0001-rubric.yaml` null and the
  `verdict` null, as `tests/test_adr_rubric_frozen.py` already enforces.

## Out of scope

- Enabling the sandbox or any candidate in the live cluster — #1280.
- Running the soak, taking any measurement, filling any rubric cell, or
  choosing a verdict — #1280.
- The ADR decision and the promotion of `docs/adr/0001-agent-execution-trace-backend.md`
  past its skeleton state — #1280.
- Performing the actual teardown — #1280.
- Fixing #1332 itself. This proposal only makes its status a CI-visible fact.
- Creating a Grafana Cloud account, stack or token, or committing any Grafana
  Cloud endpoint or credential.
- Changing the production traces pipeline's receivers, processors or the
  `debug`/`otlp/backend` exporters.
- Emitting the fixture traces: `wft-otel-trace-fixture` already exists as a
  registered `ClusterWorkflowTemplate` and submitting it is #1280's step.

## Open questions

- **Which candidates get a manifest set.** The issue says "one manifest set per
  candidate that survives the Stage A paper screen (from the #903 rubric)".
  Today `docs/adr/0001-rubric.yaml`'s `stage_a` marks exactly one row
  `SURVIVES` (`tempo`); `traceway`, `langfuse` and `phoenix` are `UNVERIFIED`
  and `signoz` is unread by this investigation but is in the same frozen file.
  Proceeding with: `tempo` plus candidate F `agento11y` (self-managed), which
  the issue names explicitly. A reviewer who reads "survives" as "was not
  screened out" should say so; adding the three `UNVERIFIED` rows is a values
  and directory addition, not a redesign.
- **Whether candidate F belongs in the rubric.** `agento11y` is not in
  `docs/adr/0001-rubric.yaml`'s `candidates` list, and
  `tests/test_adr_rubric_frozen.py` pins `EXPECTED_CANDIDATES` to the five.
  Proceeding by NOT touching the rubric: this slice commits manifests only, and
  adding candidate F's rows (with null scores) stays with #1280, which is where
  the two-shape self-managed/cloud split was decided. If the reviewer wants the
  rubric extended here, it is one row plus one constant in the test.
- **Exact `targetRevision` pins.** #903 deliberately refused to fabricate chart
  coordinates offline. The implementer must resolve each pin from the upstream
  Helm repository index at implementation time (`grafana/tempo-distributed` from
  `https://grafana.github.io/helm-charts`, the same repoURL
  `platform-gitops/bootstrap/templates/observability/loki.yaml:11` already
  uses). If a pin cannot be resolved from a reachable source, that candidate's
  manifest set is not committed and its omission is recorded in the runbook's
  precondition section — an unverified pin in a GitOps repo is worse than a
  missing one.
- **Quota sizing beyond the two mandated caps.** The issue fixes only
  `persistentvolumeclaims: 4` and `requests.storage: 40Gi`. Proceeding with
  `requests.cpu: "4"`, `requests.memory: "12Gi"`, `limits.cpu: "8"`,
  `limits.memory: "20Gi"`, `pods: "30"`, sized from the tenant chart's
  precedent (`platform-gitops/helm-charts/tenant/values.yaml:22-35`) scaled for
  a ClickHouse/Postgres-class candidate on three cx43 workers.
- **Where the teardown-date check reads "today".** Proceeding with the system
  date at CI run time, overridable by `--today` for the selftest. This means the
  check turns red on the first CI run after the date passes, which is the
  intended behaviour, and that the `push: [main]` trigger already present in
  `validate-manifests.yml` makes it fire even with no open pull request.
