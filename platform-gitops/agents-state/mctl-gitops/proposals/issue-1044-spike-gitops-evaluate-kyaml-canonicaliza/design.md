# Design: issue-1044-spike-gitops-evaluate-kyaml-canonicaliza

## Current state

How YAML is produced and validated in this repository today:

- Validation in CI: `.github/workflows/validate-manifests.yml` installs Helm
  `v3.16.4` and kubeconform `0.8.0` (`KUBECONFORM_VERSION`). It renders every
  `platform-gitops/services/*/*/values.yaml` through
  `platform-gitops/helm-charts/base-service` and validates the result with
  `kubeconform -strict` against the default schemas plus a pinned datreeio
  CRD catalog commit (`CRD_SCHEMA_LOCATION`). The bootstrap and argocd charts
  are rendered and checked the same way, and several Python validators
  (`scripts/validate-*.py`, PyYAML) parse the rendered streams. Many
  `tests/test_*.py` scripts run as plain `python3` steps.
- Lint: `.github/workflows/yamllint.yml` runs yamllint `1.35.1` with
  `extends: relaxed` and `truthy: disable`. The inline comment says Helm values
  "legitimately use bare yes/no/on/off". The repository therefore accepts YAML
  1.1-style ambiguous scalars today and relies on Helm/Go-template quoting.
- Machine writes to YAML: `platform-gitops/argo-workflows/cluster-templates/tpl-git-commit.yaml`
  (`commit-service`) edits `values.yaml` in place with `yq eval -i`
  (`.env[strenv(KEY)] = strenv(VALUE)`, ingress/tls/probes/envFrom/dbSecret
  edits). Other templates (`wft-deploy-service.yaml`,
  `wft-provision-database.yaml`, `wft-add-custom-domain.yaml`,
  `wft-remove-custom-domain.yaml`) and `gitops-bump.yaml` /
  `release-deploy.yaml` do similar edits. The yq/shell boundary is covered by
  `scripts/validate-yq-interpolation.py` and `tests/test_tpl_git_commit_yq.py`.
  The latter runs the template's loop with real yq against fixtures, and is
  the pattern this spike's harness follows.
- Tool pins: `platform-gitops/images/mctl-workflow-tools/Dockerfile` pins
  yq `v4.52.4`, helm `v3.16.4` and kubectl `v1.33.12`, all by sha256. The
  template comments say the yq calls rely on v4 semantics.
- Hand-written manifests inside values: `base-service` renders raw objects from
  `.Values.extraObjects` (`templates/extra-objects.yaml`). For example,
  `services/admins/umami/values.yaml` embeds a `batch/v1` CronJob. These are the
  closest existing thing to "standalone manifests written by agents".
- Fixtures and spike reports: `tests/fixtures/` (e.g.
  `otel-eval-candidates.example-values.yaml`) and `scripts/tests/fixtures/`
  (e.g. `deploy-intent/valid/*.yaml`). Spike reports live in `docs/spikes/`
  (`2262-cloudflare-ai-gateway-mctl-support.md`, with a STATUS line plus measured
  sections).
- KYAML today: `grep -ri kyaml` over the clone finds no references. No tool in
  the repo emits KYAML. The pinned kubectl v1.33.12 predates `-o kyaml`, so the
  spike needs a separately pinned, newer kubectl.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/` (listing): tenants `admins`, `karabu`, `labs`,
  `namax66` with their services. None of them carry KYAML or generated
  standalone manifest artifacts. This spike changes no deployed service, so I
  did not need any per-service config.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml` (read): ordinary
  hand-maintained values with comments and plain scalars (`APP_ENV: production`).
  This confirms values files carry comments that humans rely on, and that a
  canonicalizer would strip them.
- No mctl MCP tool calls were made. The spike touches no tenant runtime, so
  service status, logs and config are irrelevant to it.

## Proposed solution

Add a self-contained spike: fixtures, a harness and a report. Nothing is
wired into a deploy or sync path.

1. Fixtures in `tests/fixtures/kyaml-spike/`, at least 5 cases, each a small
   directory:
   - `01-agent-created/`: a from-scratch standalone manifest (CronJob +
     ConfigMap in the style of umami's `extraObjects`) in two textual variants
     that mean the same thing: block vs flow style, different key order,
     different quoting style, and `---`/indent differences.
   - `02-agent-modified/`: a `before.yaml` and an `after.yaml` where the agent
     made one real change (image tag + one env var) but also reflowed lists and
     requoted strings. This measures how much of the raw diff noise
     canonicalization removes.
   - `03-helm-rendered/`: `helm template test platform-gitops/helm-charts/base-service`
     rendered from a small `values-test.yaml` in the fixture dir (not a real
     service's values, so tenant changes cannot break it). The render is
     generated at test time, not committed.
   - `04-ambiguous-scalars/`: a ConfigMap + Deployment env + annotations with
     quoted `"on"`, `"off"`, `"yes"`, `"no"`, `"y"`, `"0123"`, `"0x1F"`,
     `"1e3"`, `"1_000"`, `"2026-11-04"`, `"2026-11-04T00:00:00Z"`, `"null"`,
     `"~"`, `""`, a 20-digit numeric ID, `"true"`, a `.inf`-like string, and a
     literal block `|` plus folded block `>-` multiline string with trailing
     spaces and blank lines. There is also an `expected-types.json` that
     records the intended type of each leaf by path.
   - `05-list-map-noise/`: the same Deployment with containers/ports/env lists
     written in flow and block form, maps in different key orders, and
     comments.
   - `06-invalid/`: a duplicate key, a tab-indented line, a non-object
     document and a truncated document. These test failure behaviour.

2. Harness at `scripts/kyaml-spike.py` (Python 3 + PyYAML, matching the
   existing validators; stdlib otherwise):
   - It resolves the formatter from `KYAML_KUBECTL` (path). It checks that
     binary's version string against a constant `PINNED_KUBECTL_VERSION`, and
     its sha256 against `PINNED_KUBECTL_SHA256`. A mismatch fails.
   - It canonicalizes each fixture document with
     `kubectl create --dry-run=client -o kyaml -f <file>`, or the equivalent
     offline invocation confirmed in task 1, with no kubeconfig
     (`KUBECONFIG=/dev/null`), so no cluster is contacted.
   - Semantic check: it parses input and output with a type-preserving loader
     (PyYAML `SafeLoader`, plus a strict YAML 1.2 core-schema comparison done by
     reading the KYAML, which is explicitly quoted) and compares the trees
     recursively, including Python types. For `04` it also checks every path in
     `expected-types.json`. Note: `kubectl create` may add fields
     (`creationTimestamp: null`, empty `status`). The harness records these as
     "formatter-added fields" and strips only that known set before comparing.
     The report then lists the set; it is not silently ignored.
   - Convergence: it compares the canonical bytes of the variants in each
     case.
   - Determinism: it runs each canonicalization 3 times and checks that the
     sha256 values are equal.
   - Diff noise: it computes `difflib.unified_diff` changed-line counts on raw
     input pairs and on canonical pairs.
   - Compatibility: it pipes canonical output to `kubeconform -strict`
     (same flags as `validate-manifests.yml`), to `yamllint -c` (the relaxed
     config copied from `yamllint.yml`) and to `yq` v4.52.4. The yq checks are
     a read of `.spec.template.spec.containers[0].image`, an in-place
     `.metadata.labels.x = strenv(V)` edit, and a re-parse. The harness then
     records whether yq's re-emitted output is still KYAML. This matters
     because yq writes block YAML and would undo canonicalization on any
     yq-edited path. Tools not on PATH are reported as "not observed" and make
     the run fail unless `--allow-missing` is passed.
   - Failure behaviour: for `06-invalid` it expects a non-zero exit and empty
     stdout.
   - Output: a JSON results file (`--out`) plus a markdown table to stdout,
     and wall-clock time per step.

3. Unit-style test `tests/test_kyaml_spike_semantics.py`. It runs the harness
   in `--selftest` mode against the fixtures, and proves the detector fires: a
   deliberately corrupted canonical output (an unquoted `on` injected) must be
   reported as a type change. This follows the repo's existing "--selftest
   first: a detector never seen to fire is not known to work" convention from
   `validate-manifests.yml`.

4. Optional, non-required CI job `kyaml-spike` triggered with
   `workflow_dispatch` only. It can live in a new
   `.github/workflows/kyaml-spike.yml`, so required checks are not touched. The
   job downloads the pinned kubectl by sha256, kubeconform at
   `KUBECONFORM_VERSION`, yq v4.52.4 by the sha256 already in the
   workstation-tools Dockerfile, yamllint 1.35.1 and helm v3.16.4. It then runs
   the harness and uploads the JSON as an artifact. This gives CI runtime cost
   numbers without making the spike a gate.

5. Report `docs/spikes/1044-kyaml-canonicalization.md`, in the
   `2262-...md` structure: STATUS line with ADOPT/LIMITED/REJECT, tool
   versions + sha256, a per-fixture results table (converged, deterministic,
   types preserved, diff lines before/after), a compatibility matrix
   (kubeconform, yamllint, yq read/write, helm-rendered input, kubectl
   apply-dry-run parse, ArgoCD = offline-only), comment loss, runtime cost, and
   failure behaviour. Its recommendation section names the artifact classes in
   and out of scope. The prior expectation, to be confirmed or overturned by
   the data:
   - possibly in: generated validation/evidence artifacts and fixtures that
     are hashed or diffed (e.g. canonical render attached to PR evidence);
   - out: `values.yaml`, Helm templates, ClusterWorkflowTemplates and
     anything edited by `yq` (comment loss, yq re-emits block YAML, and
     yamllint/truthy are already tuned for Helm values).

Why this way: the harness reuses the repo's existing validation tools at their
already-pinned versions, so "compatible with current validation" is measured
against the real thing. Keeping it in `tests/` + `scripts/` + `docs/spikes/`
with a dispatch-only job matches the issue's boundary: no corpus rewrite, and
nothing in deploy paths.

## Alternatives

- Use `yq -o yaml` / `yq -P` as the canonicalizer. Dropped as the primary
  formatter because it is not KYAML: it emits ordinary block YAML and keeps
  YAML 1.1 ambiguity in output style. The spike still runs yq as a
  compatibility consumer, and the report can note yq's normalization as a
  baseline for comparison.
- Canonicalize to JSON (`kubectl -o json` / `yq -o json`). JSON removes
  scalar ambiguity entirely and is byte-stable. It was dropped as the
  question under test, because the issue asks specifically about KYAML. It
  is recorded as the comparison baseline in the report, and may be the better
  answer for evidence hashes.
- Bump kubectl in `mctl-workflow-tools` and run the spike inside an Argo
  workflow. Dropped: it changes a sha256-pinned image that carries the gitops
  deploy key and Vault tokens (see the Dockerfile header), which is a large
  blast radius for a P3 spike. A standalone pinned binary in a dispatch-only
  job isolates the experiment.
- Write a Python KYAML emitter. Dropped: a second implementation would not
  show that the upstream tool behaves the same way, and it would need its own
  maintenance.

## Platform impact

- Migrations: none. No existing file under `platform-gitops/` changes.
- Backward compatibility: nothing changes. The new workflow is
  `workflow_dispatch` only and is not a required check. `validate-manifests.yml`
  and `yamllint.yml` are untouched. The new fixtures live under `tests/`, which
  yamllint (scoped to `platform-gitops`) does not lint. Fixtures in
  `06-invalid/` are intentionally invalid YAML, so they must stay outside any
  path that yamllint or `no-root-yaml.yml` covers. Task 1 verifies this.
- Resources: one extra kubectl download (about 50 MB) per dispatch run. The
  harness runtime is expected to be seconds. It is measured and reported.
- Risks and mitigations:
  - kubectl adds or drops fields when it re-serializes an object. Mitigation:
    an explicit, reported list of formatter-added fields, and every other
    difference fails the semantic check.
  - The KYAML feature is alpha/beta at the pinned version and its output may
    change between releases. Mitigation: pin by version + sha256, and record
    the stability caveat in the report. Any ADOPT requires a drift test in the
    follow-up issue.
  - Supply chain: the downloaded binary is verified by sha256 before use, as in
    the workflow-tools Dockerfile.
  - The spike could be read as an approval to reformat. Mitigation: the report
    states the boundary explicitly, and adoption only happens through a
    separate, narrowly scoped issue.
