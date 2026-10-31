# Pin the corrected agent-isolation auditor in mctl-gitops CI and gate PRs against a versioned baseline

## Context

Spike mctlhq/mctl-agents#807 (decision `HARDEN_IN_PLACE`) produced `tools/agent_isolation_audit.py` in
mctl-agents. It is an offline, read-only auditor. It reads the agent ClusterWorkflowTemplates, RBAC,
NetworkPolicies, quota and execution profiles under `platform-gitops/` and emits one matrix row per
primitive and agent step, with status `enforced|partial|absent|not-observed`. mctl-gitops CI already runs
`scripts/validate-agent-pod-security.py` (mctl-gitops#1717) in the `validate` job of
`.github/workflows/validate-manifests.yml`, but that only covers pod/container `securityContext`. Nothing in
mctl-gitops CI stops a PR from regressing the rest of the matrix. Examples: dropping
`automountServiceAccountToken: false` from an agent CWFT, adding a binding to `mctl-agents-runner`, widening a
NetworkPolicy peer, or adding an agent step without the controls its peers have.

Follow-up (g) asks for one immutable, corrected auditor version to be pinned in mctl-gitops CI and run against
each PR's `platform-gitops/` tree. Its output is compared with a committed, versioned baseline. The gate fails
on regressions, on new steps that lack peer controls, and on objects that drop into `not-observed`. Gaps that
are already accepted stay visible but do not fail just for existing. The hard prerequisite is
mctlhq/mctl-agents#921, which fixes how the auditor reads a peer that combines `namespaceSelector` and
`podSelector`. That bug is a known false positive on `allow-agent-ingress` in
`platform-gitops/infra-components/mctl-platform/mctl-agents-egress-proxy/networkpolicy.yaml`. #921 was OPEN
when this proposal was written, so no blocking gate may be built on the auditor before it lands.

## User stories

- AS a platform maintainer I WANT a mctl-gitops PR that weakens agent isolation to fail CI SO THAT the #807
  matrix cannot regress silently.
- AS a reviewer I WANT each baseline change to show whether it came from GitOps state or from an auditor/schema
  upgrade SO THAT I can judge whether a diff is a real posture change or an oracle change.
- AS a security owner I WANT open isolation gaps listed in the baseline with their owning issue SO THAT they
  stay visible and are not normalized into "green".
- AS an operator I WANT a documented, single-file pin and upgrade procedure SO THAT the CI oracle only changes
  through a reviewed PR.

## Acceptance criteria (EARS)

- WHEN a pull request or push to `main` runs `validate-manifests.yml` THE SYSTEM SHALL run the vendored, pinned
  auditor against the checked-out `platform-gitops/` tree and compare its JSON output with
  `scripts/agent-isolation/baseline.json`.
- THE SYSTEM SHALL consume exactly one auditor revision. The revision is recorded in
  `scripts/agent-isolation/auditor.pin.json` as source repo, full 40-hex commit SHA (a commit that contains the
  #921 fix), vendored path(s), and the SHA-256 of each vendored file.
- WHEN the SHA-256 of any vendored auditor file differs from `auditor.pin.json` THE SYSTEM SHALL fail the job.
- WHEN a PR changes `auditor.pin.json` or the vendored auditor THE SYSTEM SHALL fetch the pinned file(s) from
  the pinned commit of the source repo and fail unless they are byte-identical to the vendored copy.
- IF `baseline.json` records an auditor SHA-256 or commit that differs from `auditor.pin.json` THEN THE SYSTEM
  SHALL fail with an "auditor upgraded without re-baselining" error.
- IF the auditor exits non-zero (including exit 2 for unreadable input), prints output that is not valid JSON,
  or prints output that does not match the expected row schema THEN THE SYSTEM SHALL fail the job.
- IF `baseline.json` is absent, has an unknown or incompatible `schema_version`, or contains a duplicate row
  key THEN THE SYSTEM SHALL fail closed and SHALL NOT start from an empty baseline.
- IF the auditor output contains a duplicate row key THEN THE SYSTEM SHALL fail.
- WHEN a gate-owned baseline row has status `enforced` and the current row has any other status, or is missing,
  THE SYSTEM SHALL fail with a regression error naming the row key.
- WHEN a baseline row with a recognized status (`enforced`, `partial`, `absent`) is currently `not-observed` or
  missing THE SYSTEM SHALL fail. `not-observed` SHALL never count as clean and SHALL never satisfy an expected
  `enforced` row.
- WHEN a gate-owned baseline row is an accepted gap (`partial` or `absent`, with an `issue`) and the current
  status is the same THE SYSTEM SHALL pass and SHALL list the row in the job summary as an open gap.
- WHEN an accepted gap gets worse (`partial` to `absent`) THE SYSTEM SHALL fail.
- WHEN an accepted gap improves (to `enforced`) THE SYSTEM SHALL fail with "gap closed: update the baseline in
  this PR", so that closing a gap and updating the baseline land in the same PR.
- WHEN the current output contains a row key that is not in the baseline THE SYSTEM SHALL fail with an
  "unbaselined row" error.
- WHEN the current output contains an agent-step scope that is not in the baseline THE SYSTEM SHALL also report
  every peer-required primitive (one that is `enforced` for every baselined agent step) that the new step does
  not have as `enforced`.
- WHILE validating `baseline.json` THE SYSTEM SHALL require every non-`enforced` row to carry a non-empty
  `issue`, and every row to carry an `owner` of `agent-isolation-gate` or `validate-agent-pod-security`.
- WHILE a row is owned by `validate-agent-pod-security` THE SYSTEM SHALL record it in the baseline but SHALL NOT
  compare it in the isolation gate. `scripts/validate-agent-pod-security.py` stays the only check for those
  rows.
- THE SYSTEM SHALL never write `baseline.json` in CI. Regeneration SHALL happen only through an explicit local
  `--regenerate` command whose output a human commits.
- WHEN the gate's `--selftest` runs THE SYSTEM SHALL prove that the pinned auditor reports a combined
  `namespaceSelector`+`podSelector` peer fixture as narrower than a namespace-only peer (no #921 false
  positive). It SHALL also prove the gate fails on each of these mutations of a copy of the real tree:
  (1) `automountServiceAccountToken: false` removed from one agent CWFT; (2) the `allow-agent-ingress` peer
  widened to the whole namespace; (3) a new `agent_image` step added without the peer controls. It SHALL prove
  the current tree passes.
- IF a selftest mutation is owned by `validate-agent-pod-security` THEN THE SYSTEM SHALL prove that the composed
  gate (pod-security validator plus isolation gate) fails, without adding that check to the isolation gate.

## Out of scope

- Fixing the auditor itself (that is mctlhq/mctl-agents#921) or adding auditor checks for new primitives.
- Closing any of the #807 gaps G1-G6. This proposal only records them as accepted gaps.
- Changing `scripts/validate-agent-pod-security.py` checks.
- Any change to cluster state, CWFTs, NetworkPolicies, RBAC or quota manifests.
- Live-cluster verification (namespace labels, CNI enforcement). The auditor is static.

## Open questions

- mctlhq/mctl-agents#921 was OPEN on 2026-10-31. Implementation is blocked until it merges. The pinned commit
  must be at or after that merge, and the implementer must record the exact SHA.
- The exact JSON output contract after #921 (top-level shape, whether it exposes `auditor_version` /
  `schema_version`, the row key fields and how agent-step scopes are named) is unknown here. The design assumes
  rows `{primitive, scope, status, severity, source, field, detail, recommendation}` from the #807 design and a
  key of `(primitive, scope, field)`. If #921 exposes a version or schema, the baseline records it. If it does
  not, the baseline records `null` and the pin's SHA-256 is the version.
- Whether the auditor is a single self-contained file or imports sibling modules in `tools/`. The pin lists
  every vendored file either way.
- Whether #921 emits a row for the egress-proxy `allow-agent-ingress` policy. Mutation (2) needs one. If no row
  is emitted, the selftest fails, and the gap goes back to #921 rather than into a local check.
- The initial accepted-gap set and its owning issues (G1-G6 from the #807 report, plus any follow-up issues
  opened since) must be confirmed from the pinned auditor's real output when the baseline is generated.
