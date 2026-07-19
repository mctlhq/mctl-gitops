# Design: mctl-agents-image-tag-stale-post-slug-fix

## Confidence: MEDIUM

The root cause (stale image, patched code not deployed) is corroborated
directly from files in this repo (merged proposal + unbumped tag +
five post-merge failures). What is NOT verified is the exact released tag
that contains the fix, because the `mctl-agents` application source is not
checked out in this environment (only `mctl-gitops` is, per
`agents-state/OPERATOR.md`). The implementer must resolve that one value
before applying.

## Diagnosis
`incident-argo-id-slug-collision` (merged 2026-07-19T20:01:11Z, PR #61,
commit `e316c46`) fixed a bug where the incident-responder derived a
proposal-directory slug as `"incident-" + incident_id[:8]`. Every
argo-workflows-sourced incident ID has the form
`argo-mctl-agents-<workflow>-<ts>-<ts>`, so `incident_id[:8]` is always the
literal string `argo-mct` for this incident source — collapsing every such
incident onto the single slug `incident-argo-mct`. That directory already
existed (created 2026-07-17 for an unrelated `mctl-agents-implement`
failure) and is still `status: in-progress`, so every subsequent
incident-responder tick that touched an argo-workflows-typed incident hit
the same occupied path and the CronWorkflow failed end-to-end.

The code fix is merged, but the CronWorkflowTemplate still pins the
pre-fix image (`ghcr.io/mctlhq/mctl-agents:1.17.0`), and five
incident-responder ticks after the merge (20:47, 21:17, 21:47, 22:17,
22:47Z) all still failed — the deploy step (task 6 of the original
proposal: "bump the image tag ... once the fix is released") was never
carried out. This is a one-line gitops config change, not a code change,
so it belongs in `mctl-gitops`, not `mctl-agents`.

## Proposed Fix
File: `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-run.yaml`
Line ~171, `image:` field:

- Current value: `ghcr.io/mctlhq/mctl-agents:1.17.0`
- New value: the earliest `mctl-agents` release tag that contains commit
  `e316c46341b6fcc3b767a2035c09cee6fcd055d2` (PR #61). Determine this by
  checking the `mctl-agents` repo's tags/releases (`git tag --contains
  e316c46...` or the GHCR tag list) — implementer has access to the
  `mctl-agents` source and registry that this environment does not.
  - If no tag has been cut yet containing that commit, this proposal is
    blocked on a release being cut first; implementer should note that in
    the PR description rather than guessing a version number.

## Scope
Minimal: bump one `image:` tag in one file. Do not touch
`agents-state/mctl-gitops/proposals/incident-argo-mct/` — it is a separate,
still-open proposal for a different, older incident and must not be
overwritten or reinterpreted (per the prior proposal's explicit scope note,
still valid).
