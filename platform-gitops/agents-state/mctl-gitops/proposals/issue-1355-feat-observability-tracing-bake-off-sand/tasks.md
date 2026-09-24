# Tasks: issue-1355-feat-observability-tracing-bake-off-sand

- [ ] 1. Add `otelCollector.eval.quota` and `otelCollector.eval.limits` to
      `platform-gitops/bootstrap/values.yaml`, with the sizing from design.md
      §"Proposed solution" 1 — including the two mandated caps
      `persistentvolumeclaims: "4"` and `requests.storage: "40Gi"` — and a
      comment naming #1355 and #1280 in the style of the surrounding
      `otelCollector.eval` block (lines 34-43).
      DoD: `helm lint platform-gitops/bootstrap` passes; keys are present and
      every value is a quoted string, matching
      `helm-charts/tenant/values.yaml:22-35`.

- [ ] 2. Append a `ResourceQuota` (`observability-eval-quota`) and a
      `LimitRange` (`observability-eval-limits`) to
      `platform-gitops/bootstrap/templates/observability/eval-namespace.yaml`,
      INSIDE the existing `{{- if .Values.otelCollector.eval.enabled }}` block
      that opens at line 9 and closes at line 147 (depends on 1).
      DoD: `helm template` with default values emits neither object; with
      `--set otelCollector.eval.enabled=true` both render into namespace
      `observability-eval`; `kubeconform -strict` accepts both.

- [ ] 3. Add per-candidate flags: give each `otelCollector.eval.candidates[]`
      entry an `enabled` field, and wrap the body of the `{{- range
      .Values.otelCollector.eval.candidates }}` loop in
      `eval-candidates.yaml` (line 25) in `{{- if .enabled }}` / `{{- end }}`.
      Leave the outer `eval.enabled` guard untouched.
      DoD: with `eval.enabled=true` and every candidate `enabled: false`, no
      `Application` targets `observability-eval`; with one on, exactly one does.

- [ ] 4. Update `tests/fixtures/otel-eval-candidates.example-values.yaml` to set
      `enabled: true` on both `candidate-a` and `candidate-b` (depends on 3).
      This is the coupled edit called out in design.md "Platform impact" —
      without it the existing T5 assertion "expected two candidate
      Applications" and the `kubeconform` eval-overlay step at
      `.github/workflows/validate-manifests.yml:99-109` both break.
      DoD: `python3 tests/test_otel_collector_backends_render.py` passes
      unchanged.

- [ ] 5. Resolve and commit the candidate pins (depends on 3). For `tempo`:
      chart `tempo-distributed` from `https://grafana.github.io/helm-charts`
      (the repoURL `bootstrap/templates/observability/loki.yaml:11` already
      uses), version resolved from the live Helm repo index at implementation
      time. For candidate F: `agento11y` self-managed shape only. Both committed
      with `enabled: false`.
      DoD: each entry has a concrete non-empty `targetRevision` and (where the
      manifest set pins an image) a concrete tag — never `latest`, never a
      range. A pin that CANNOT be resolved from a reachable source is NOT
      committed; record the omission in task 11's precondition section instead.

- [ ] 6. Create `platform-gitops/infra-components/observability/eval/<candidate>/`
      per committed candidate (depends on 5), matching the `manifestsPath`
      convention `eval-candidates.yaml:36-52` was written for. Each directory
      carries the candidate's chart-value fragment including
      `serviceMonitor.enabled: false` and `podMonitor.enabled: false` — vmagent
      runs `selectAllByDefault: true` (`monitoring.yaml:287`), the #1159
      double-scrape shape the `eval-candidates.yaml` header (lines 14-23)
      already warns about.
      DoD: the `Validate raw manifests` step's `kubeconform` run over
      `platform-gitops/infra-components` accepts every new file (note the
      step's existing `values.yaml` ignore pattern at line 278).

- [ ] 7. Add the candidate-derived fan-out to
      `platform-gitops/bootstrap/templates/observability/otel-collector.yaml`
      (depends on 3): a `range` over enabled `eval.candidates` with an
      `otlpEndpoint`, emitting `otlp/eval-<name>` exporters after the existing
      `.Values.otelCollector.backends` block (line 241-261), plus the mirror in
      the traces pipeline exporter list after line 287. Whole thing nested
      inside `{{- if .Values.otelCollector.eval.enabled }}`. Leave
      `backendEndpoint` and `backends` untouched.
      DoD: default render is byte-identical to
      `tests/fixtures/otel-collector-config-default.yaml` (T1 passes with NO
      `--write-golden` regeneration); with one candidate on, exactly one extra
      exporter appears.

- [ ] 8. Write `scripts/validate-eval-teardown-date.py` in the house detector
      style (closest template: `scripts/validate-openclaw-version-pin.py`).
      Reads `platform-gitops/bootstrap/values.yaml`; passes when
      `otelCollector.eval.enabled` is not true; otherwise requires
      `teardownAfter` to be a `YYYY-MM-DD` date, `>= today`, and
      `<= today + 14 days`. `--today YYYY-MM-DD` injects the date;
      `--selftest` proves the detector fires.
      DoD: executable, `python3 -m pip install pyyaml` is its only dependency,
      and `--selftest` exercises all five branches listed in T3 below.

- [ ] 9. Write `tests/test_otel_collector_redaction.py` (plain `python3`, the
      `check()`/`failures` shape of `tests/test_otel_collector_backends_render.py`).
      Renders the default collector config, compiles
      `processors.redaction.blocked_key_patterns` with Python `re`, hard-asserts
      `github_token`/`authorization`/`api_key`/`vault.token` are blocked, and
      asserts the four `gen_ai.usage.{input,output,cache_read_input,reasoning}_tokens`
      keys survive — that half guarded by `KNOWN_BROKEN_ISSUE =
      "mctlhq/mctl-gitops#1332"`, xfail-strict per design.md §4.
      DoD: passes today (expected-failure path prints the #1332 line, exit 0);
      fails loudly if the marker is set but the counters survive; fails normally
      if the marker is cleared while they are still blocked.

- [ ] 10. Extend `tests/test_otel_collector_backends_render.py` with the new
      assertions (depends on 2, 3, 7): quota/limits rendered only when enabled
      and carrying `persistentvolumeclaims: "4"` and `requests.storage: "40Gi"`
      literally; per-candidate enablement; fan-out off/on with a structural diff
      of the traces pipeline; `${env:...}`-only headers on eval exporters.
      DoD: the file still runs as `python3 tests/test_otel_collector_backends_render.py`
      with no pytest dependency, and every pre-existing T1/T2/T5 check still
      passes.

- [ ] 11. Write `docs/runbooks/tracing-bake-off.md` with the seven sections in
      design.md §6 (preconditions, open the sandbox + set `teardownAfter` ≤ 14
      days, declare soak window and trace volume before measuring, the
      per-rubric-dimension measurement-source table, score and promote,
      one-commit teardown, post-teardown verification). Name every control by
      its exact values key: `otelCollector.eval.enabled`,
      `otelCollector.eval.teardownAfter`, `otelCollector.eval.quota`,
      `otelCollector.eval.limits`, and each `candidates[].enabled` by candidate
      name (depends on 5).
      DoD: every item under the issue's Acceptance list has a named home in the
      runbook, and the "unmeasurable while #1332 is open" caveat is explicit on
      the `ai_agent_observability` row.

- [ ] 12. Add a cross-reference from `docs/runbooks/otel-collector.md`'s "The
      evaluation namespace and the fixture emitter (issue #903 / #1280)"
      section (line 206) to the new runbook (depends on 11).
      DoD: one sentence, no other change to that file.

- [ ] 13. Wire the two new checks into
      `.github/workflows/validate-manifests.yml` (depends on 8, 9): a step
      running `scripts/validate-eval-teardown-date.py --selftest` then the real
      run (the `--selftest`-first convention stated at lines 154-159, 168-171,
      205-207, 228-231), and a step running
      `python3 tests/test_otel_collector_redaction.py`, both placed with the
      other issue-903 steps (after line 418), each with the explanatory comment
      the file's steps all carry.
      DoD: `yamllint` passes (`.github/workflows/yamllint.yml`), and both steps
      appear in the `validate` job.

## Tests

- [ ] T1. **Inertness.** `helm template test platform-gitops/bootstrap -f
      platform-gitops/bootstrap/values.yaml` on the branch is byte-identical to
      the same command on `main`. Enforced by the existing golden-file check
      (`tests/test_otel_collector_backends_render.py` T1 against
      `tests/fixtures/otel-collector-config-default.yaml`) plus a new assertion
      that no `ResourceQuota`, `LimitRange`, `Namespace` or `Application`
      touching `observability-eval` renders by default.

- [ ] T2. **Quota and limits.** With `eval.enabled=true`: one
      `ResourceQuota observability-eval-quota` and one `LimitRange
      observability-eval-limits`, both in `observability-eval`; `spec.hard`
      contains `persistentvolumeclaims: "4"` and `requests.storage: "40Gi"`
      asserted literally; the `LimitRange` has a `type: Container` entry with
      `default`, `defaultRequest` and `max`.

- [ ] T3. **Teardown-date detector.** `scripts/validate-eval-teardown-date.py
      --selftest` proves five branches: (a) `enabled: false` + empty
      `teardownAfter` passes; (b) `enabled: true` + a date 7 days out passes;
      (c) `enabled: true` + `teardownAfter: ""` fails; (d) `enabled: true` +
      yesterday fails — the "date has passed while eval.enabled is still true"
      case the issue names; (e) `enabled: true` + 30 days out fails the ≤14-day
      bound. Both states of the issue's acceptance item are (b) and (d).

- [ ] T4. **Per-candidate enablement.** `eval.enabled=true` with every
      `candidates[].enabled: false` renders zero `Application`s into
      `observability-eval`; flipping exactly one renders exactly one, with
      `automated.prune: true` and no `selfHeal` key (the existing T5
      invariants); a per-candidate flag `true` while `eval.enabled: false`
      renders nothing.

- [ ] T5. **Fan-out on/off.** All flags off: no `otlp/eval-*` exporter and the
      traces pipeline exporter list is exactly `["debug"]`. One flag on:
      exactly one extra exporter, present in the pipeline list, carrying its own
      `sending_queue` and `retry_on_failure`; and a structural comparison of the
      traces pipeline against the default render shows the ONLY difference is
      that appended exporter — `receivers` and the ordered `processors` list
      byte-equal. A candidate `headers` value not starting with `${env:` fails.

- [ ] T6. **Redaction.** `github_token`, `authorization`, `api_key`,
      `vault.token` are each matched by at least one committed
      `blocked_key_patterns` entry (hard, always). The four
      `gen_ai.usage.*_tokens` keys are matched by none — currently an expected
      failure naming `mctlhq/mctl-gitops#1332`, which flips to a hard failure
      the moment the counters survive while the marker is still set.

- [ ] T7. **Rubric freeze unbroken.** `python3 tests/test_adr_rubric_frozen.py`
      still passes: `docs/adr/0001-rubric.yaml` is not edited by this proposal,
      so every `dimensions[].candidates[].score` stays null, `verdict` stays
      null, and `EXPECTED_CANDIDATES` still matches — the issue's "no non-null
      rubric score cell is committed" criterion, satisfied by construction.

- [ ] T8. **Schema validity of the on-state.** The existing eval-overlay
      `kubeconform` step (`validate-manifests.yml:99-109`) accepts the render
      with the updated fixture from task 4, now including the `ResourceQuota`,
      the `LimitRange` and the per-candidate `Application`s.

## Rollback

Every deliverable is inert with the shipped values, so rollback is graded
rather than all-or-nothing:

1. **Nothing is running.** With `otelCollector.eval.enabled: false` and every
   `candidates[].enabled: false` — the state this proposal merges in — reverting
   the PR changes no cluster state at all. Confirm with `git revert` followed by
   `python3 tests/test_otel_collector_backends_render.py`, which will report the
   default render still matching the golden file.
2. **A CI gate is wrong, not the manifests.** If
   `scripts/validate-eval-teardown-date.py` or
   `tests/test_otel_collector_redaction.py` turns out to fire incorrectly,
   remove its step from `.github/workflows/validate-manifests.yml` in a one-line
   commit. That unblocks every PR in the repo immediately (both run in the
   required `validate` job) without reverting the manifests, the quota or the
   runbook.
3. **The template change is wrong.** Reverting task 7's fan-out `range` and
   task 3's `{{- if .enabled }}` restores the #903 behaviour exactly; task 4's
   fixture edit must be reverted in the same commit or T5 breaks the other way.
4. **A sandbox is already live (the #1280 case).** Do not revert — run the
   documented one-commit teardown instead: `otelCollector.eval.enabled: false`,
   every `candidates[].enabled: false`, `teardownAfter: ""`. Reverting the
   templates while ArgoCD is holding live candidate Applications would orphan
   them: the `Application` objects vanish from the render while their workloads,
   PVCs and the namespace remain, and the prune that would have removed them no
   longer has a source to prune from. Verify afterwards with the checks in
   `docs/runbooks/tracing-bake-off.md` §7.
