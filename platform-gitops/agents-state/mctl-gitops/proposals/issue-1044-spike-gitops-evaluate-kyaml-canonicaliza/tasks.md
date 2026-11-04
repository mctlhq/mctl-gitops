# Tasks: issue-1044-spike-gitops-evaluate-kyaml-canonicaliza

- [ ] 1. Choose and pin the KYAML formatter — DoD: the kubectl release notes
  show the first version with `-o kyaml`, and whether it needs a feature-gate
  env var at that version. The chosen upstream kubectl version and its
  linux-amd64 sha256 are recorded as `PINNED_KUBECTL_VERSION` /
  `PINNED_KUBECTL_SHA256` in `scripts/kyaml-spike.py`. The offline invocation
  (no kubeconfig, no cluster) that emits KYAML for a file is confirmed
  manually. The paths of `tests/fixtures/kyaml-spike/` are confirmed to be
  outside `yamllint.yml` and `no-root-yaml.yml` coverage.
- [ ] 2. Add fixtures `tests/fixtures/kyaml-spike/01-agent-created`,
  `02-agent-modified`, `03-helm-rendered` (values-test.yaml only),
  `04-ambiguous-scalars` (+ `expected-types.json`), `05-list-map-noise`,
  `06-invalid` (depends on 1) — DoD: at least 5 valid cases plus the invalid
  set. Every ambiguous scalar listed in design.md is present and quoted as a
  string where Kubernetes requires a string. No file under `platform-gitops/`
  is modified.
- [ ] 3. Implement `scripts/kyaml-spike.py` (depends on 1, 2) — DoD: it
  verifies the pinned binary, canonicalizes each fixture, and runs the
  semantic/type check (including `expected-types.json`), the convergence
  check, the 3-run sha256 determinism check, diff-noise counts, the
  kubeconform/yamllint/yq compatibility checks and the invalid-input checks.
  It emits JSON (`--out`) and a markdown table, records formatter-added
  fields, and fails closed on a missing tool unless `--allow-missing` is
  passed. It supports `--selftest`.
- [ ] 4. Add `tests/test_kyaml_spike_semantics.py` (depends on 3) — DoD: it
  runs the harness self-test and asserts that the detector fires on an
  injected type coercion and on a zero exit for invalid input. It passes
  locally with the pinned tools.
- [ ] 5. Add `.github/workflows/kyaml-spike.yml`, `workflow_dispatch` only
  (depends on 3, 4) — DoD: it installs helm v3.16.4, kubeconform
  `0.8.0`, yq v4.52.4, yamllint 1.35.1 and the pinned kubectl, all verified by
  sha256 where a digest exists. It runs the test and the harness and uploads
  the JSON artifact. It is not added to required checks, and actions are
  pinned by commit SHA like the existing workflows.
- [ ] 6. Run the experiment and write `docs/spikes/1044-kyaml-canonicalization.md`
  (depends on 5) — DoD: the report has a STATUS line with exactly one of
  ADOPT/LIMITED/REJECT, tool versions + digests, a per-fixture results table,
  a compatibility matrix (ArgoCD marked offline-only), notes on comment loss,
  CI/runtime cost, failure behaviour, the JSON-baseline comparison, and an
  explicit in-scope/out-of-scope list of artifact classes and paths.
- [ ] 7. If ADOPT or LIMITED: draft the follow-up implementation issue text
  in the report (depends on 6) — DoD: the text names the single generation or
  validation path, the formatter version pin, and a CI drift test. The issue
  itself is filed by a human. If REJECT: the report states why.

## Tests

- [ ] T1. Type preservation: every path in
  `04-ambiguous-scalars/expected-types.json` keeps its type and exact value
  after canonicalization. The multiline strings match byte for byte.
- [ ] T2. Detector self-test: an injected unquoted `on` / `0123` in the
  canonical output is reported as a type change and fails the run.
- [ ] T3. Determinism: 3 consecutive canonicalizations of each fixture give
  identical sha256 values.
- [ ] T4. Convergence: the textual variants in `01` and `05` are compared and
  the result is recorded. The harness must not crash on non-convergence; the
  report states it.
- [ ] T5. Compatibility: the canonical output of `03-helm-rendered` passes
  `kubeconform -strict` with the `CRD_SCHEMA_LOCATION` from
  `validate-manifests.yml`. yamllint relaxed passes, or each failure is
  recorded. A yq v4.52.4 read and `strenv` edit succeed.
- [ ] T6. Invalid input: every `06-invalid` file makes the formatter exit
  non-zero with empty stdout. A zero exit fails the harness.
- [ ] T7. Boundary: `git diff --stat origin/main -- platform-gitops/` is
  empty for the spike PR.

## Rollback

All changes are additive and isolated: fixtures under
`tests/fixtures/kyaml-spike/`, `scripts/kyaml-spike.py`,
`tests/test_kyaml_spike_semantics.py`, the dispatch-only
`.github/workflows/kyaml-spike.yml` and the report in `docs/spikes/`. No
deploy, sync or required check depends on them. To roll back, revert the
spike PR. No cluster, Vault or ArgoCD state needs to be cleaned up.
