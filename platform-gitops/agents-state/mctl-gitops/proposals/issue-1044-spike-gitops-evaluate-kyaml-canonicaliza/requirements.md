# Spike: evaluate KYAML canonicalization for machine-generated Kubernetes manifests

## Context

Issue mctlhq/mctl-gitops#1044 asks for a bounded experiment: would canonical
KYAML output (the stricter YAML subset Kubernetes introduced for `kubectl -o
kyaml`) make machine-generated Kubernetes manifests in mctl safer, more
deterministic and easier to review? The concern is that AI agents write YAML
that means the same thing but looks different each time, and can coerce
scalars by accident (`on`/`off`, `0123`, `1e3`, timestamps, `~`/`null`,
unquoted IDs). The spike must end with one written recommendation, ADOPT,
LIMITED or REJECT, naming the exact artifact classes where KYAML should or
should not be used.

The repository has a large corpus maintained by hand (`platform-gitops/services/*/*/values.yaml`,
Helm charts, ClusterWorkflowTemplates). It is validated by `helm lint` /
`helm template` + `kubeconform -strict` in `.github/workflows/validate-manifests.yml`
and by `yamllint` (relaxed, `truthy: disable`) in `.github/workflows/yamllint.yml`.
Workflow steps change values files with yq v4.52.4, which ships in
`platform-gitops/images/mctl-workflow-tools/Dockerfile`. The spike must not
rewrite any of that corpus. It produces fixtures, a test harness and a
report only.

## User stories

- AS a platform reviewer I WANT agent-generated manifests to come out in one
  stable, unambiguous form SO THAT a PR diff shows only real changes.
- AS a platform engineer I WANT proof that canonicalization never changes a
  Kubernetes value's type or content SO THAT adopting it cannot change what
  is deployed without anyone noticing.
- AS a maintainer of the yq/shell workflow steps I WANT to know if KYAML
  output still works with `yq` v4 and the existing scripts SO THAT adopting
  it does not break `tpl-git-commit` or `release-deploy`.
- AS the person deciding adoption I WANT a measured ADOPT/LIMITED/REJECT
  report with exact paths SO THAT any follow-up implementation issue is
  narrow and pinned.

## Acceptance criteria (EARS)

- WHEN the spike harness runs THE SYSTEM SHALL process at least 5
  fixtures under `tests/fixtures/kyaml-spike/`. They cover: a manifest an
  agent wrote from scratch, a manifest an agent modified, a Helm-rendered
  `base-service` validation fixture, an ambiguous-scalar manifest, and a
  noisy list/map formatting variant.
- WHEN the harness canonicalizes a fixture THE SYSTEM SHALL use exactly one
  formatter binary, pinned by version and sha256: kubectl, at a version
  that supports `-o kyaml`. A wrong or missing binary SHALL fail the run,
  not skip it.
- WHEN a fixture and its canonical KYAML output are both parsed THE SYSTEM
  SHALL assert semantic equivalence: the parsed data trees are equal, and
  every scalar keeps its type (string/int/float/bool/null).
- WHEN the ambiguous-scalar fixture is canonicalized THE SYSTEM SHALL assert
  that quoted string-like values (for example `"on"`, `"off"`, `"yes"`,
  `"0123"`, `"1e3"`, `"2026-11-04"`, `"null"`, `"~"`, numeric-looking IDs,
  `"true"` in env values and annotations) are still strings in the output,
  and that a multiline string keeps its bytes exactly.
- WHEN two or more semantically equivalent variants of one manifest are
  canonicalized THE SYSTEM SHALL record whether they converge to byte-identical
  output, and the report SHALL state the result per fixture.
- WHEN the same fixture is canonicalized repeatedly (at least 3 runs) with the
  pinned formatter THE SYSTEM SHALL produce byte-identical output with a
  matching sha256.
- WHEN canonical output is produced THE SYSTEM SHALL run it through the
  repository's existing validation: `kubeconform -strict` with the
  `KUBECONFORM_VERSION` and `CRD_SCHEMA_LOCATION` from `validate-manifests.yml`,
  `yamllint` 1.35.1 with the relaxed config from `yamllint.yml`, and yq v4.52.4
  reads/writes of the kind used in `tpl-git-commit.yaml`. It SHALL record
  pass/fail for each.
- WHEN raw diff noise is measured THE SYSTEM SHALL report changed-line counts
  for the variant pairs and the modification pair, both before and after
  canonicalization.
- IF a fixture is invalid YAML or not a Kubernetes object THEN THE SYSTEM
  SHALL record that the formatter exits non-zero with no partial output, and
  the harness SHALL treat a zero exit on invalid input as a failure.
- WHEN canonicalization drops comments or custom formatting THE SYSTEM SHALL
  record this explicitly in the report.
- WHILE the spike is in progress THE SYSTEM SHALL leave every existing file
  under `platform-gitops/` untouched (no reformat of values, templates or
  workflows).
- WHEN the spike completes THE SYSTEM SHALL contain
  `docs/spikes/1044-kyaml-canonicalization.md` with measured results, the
  runtime cost per fixture and for the full run, a compatibility matrix, and
  exactly one of ADOPT, LIMITED or REJECT, naming the artifact classes in and
  out of scope.
- IF the recommendation is ADOPT or LIMITED THEN THE SYSTEM SHALL list, in the
  report, the follow-up implementation issue to file. That issue SHALL name the
  formatter version pin and the CI drift test. It is not implemented in this
  spike.

## Out of scope

- Reformatting any existing hand-maintained YAML (`values.yaml`, Helm
  templates, ClusterWorkflowTemplates, bootstrap/ArgoCD charts).
- Replacing Helm, kubeconform/OpenAPI schema validation or yamllint.
- Semantic application diffing (tracked in `mctl-api#249`).
- Changing the `mctl-workflow-tools` image or bumping its pinned kubectl
  (v1.33.12). The spike uses its own pinned binary.
- Adding the harness as a required CI gate. At most it runs on demand or in
  an optional job. Gating is a decision for the follow-up issue.
- Using KYAML in any deploy path, ArgoCD sync, or agent runtime.

## Open questions

- Which formatter is canonical? The issue does not say. This proposal picks
  `kubectl -o kyaml` from an upstream kubectl release new enough to support
  it, because that is the reference implementation. The exact minimum version,
  and whether a feature-gate env var (e.g. `KUBECTL_KYAML=true`) is still
  needed at the pinned version, must be checked against the kubectl release
  notes during task 1. It is not assumed here.
- `kubectl -o kyaml` formats objects it has parsed (via `--dry-run=client -o kyaml`
  or `create --dry-run`). Whether it accepts non-Kubernetes YAML (Helm values)
  or multi-document streams without a cluster is not known. The harness will
  record what it observes. Helm values are out of the adoption surface anyway.
- The issue lists "agent-generated standalone manifests" as a candidate
  surface. This clone has no committed directory of standalone manifests
  written by agents: agents mostly edit `values.yaml`, including
  `extraObjects`, through PRs or yq. So the "created by an agent" and
  "modified by an agent" fixtures will be synthetic but realistic, written in
  the style of `extraObjects` entries (e.g. the CronJob in
  `services/admins/umami/values.yaml`). The reviewer should confirm this
  stand-in is acceptable.
- ArgoCD compatibility can only be shown offline, by schema validation and by
  checking that canonical output is a valid YAML stream. No live ArgoCD sync
  is run, because this is a read-only spike.
