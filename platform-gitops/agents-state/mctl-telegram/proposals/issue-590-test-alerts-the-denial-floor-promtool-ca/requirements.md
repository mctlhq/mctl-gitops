# Make the denial-floor promtool case actually pin the absolute floor

## Context

`deploy/alerts/mctl-telegram.rules_test.yaml` contains a case commented "T4b"
that claims to pin the `> 4` absolute-denial-count floor of
`MctlAgentPolicyDenialRateHigh` in `deploy/alerts/mctl-telegram.rules.yaml`.
Both of its input series step once at `t=1m` and then stay flat, so whether the
case exercises the floor at all depends entirely on how the PromQL engine
treats the left edge of a range selector. Prometheus 2.x range selectors are
closed on both ends, so the `t=0` sample is inside `[30m]` and the case does
pin the floor. Prometheus 3.0 made range selectors left-open; the `t=0` sample
falls out, both series read as the constant `1`, both rates are `0`, the share
is `0/0 = NaN`, `NaN` fails every comparison, and the case goes silent for
arithmetic reasons rather than because of the floor clause. Issue #590 reports
the second behaviour, which is what the mctl-gitops mirror (#1110) and any
Prometheus 3.x toolchain see.

This repository's `promtool-check` job in `.github/workflows/build.yml` pins
`PROM_VERSION=2.52.0`, so the case is not vacuous *today* in this repo — but it
is one toolchain bump away from becoming vacuous, and it is already vacuous in
the deployed copy's environment. A test that silently stops testing on a
version bump is exactly the hazard the file's own header warns about. The fix
is to use series that rise inside the evaluation window, so the share is real
and only the floor suppresses the alert, on every Prometheus version. This is
worth doing even though `mctl-telegram.rules.yaml` is a non-deployed mirror:
the mirror is what a future reader edits and copies from.

## User stories

- AS an on-call engineer I WANT the promtool case that claims to pin the
  denial-count floor to fail when the floor is removed SO THAT the `> 4` clause
  cannot be dropped or relaxed without CI noticing.
- AS a future editor of `mctl-telegram.rules_test.yaml` I WANT the case comment
  to describe the range-selector edge semantics SO THAT I do not reintroduce a
  flat-series input that degenerates to `NaN` under Prometheus 3.x.
- AS the maintainer of the mctl-gitops mirror I WANT this repository's test
  inputs to be byte-identical to the deployed suite's equivalent case SO THAT
  the mirror stays a faithful mirror and diffs between the two are meaningful.

## Acceptance criteria (EARS)

- WHEN `promtool test rules deploy/alerts/mctl-telegram.rules_test.yaml` runs
  against the unmodified rules extracted from
  `deploy/alerts/mctl-telegram.rules.yaml`, THE SYSTEM SHALL report SUCCESS for
  the whole suite, including the replaced denial-floor case.
- WHEN the absolute floor clause `sum by (reason)
  (increase(mctl_agent_policy_denials_total[30m])) > 4` in
  `MctlAgentPolicyDenialRateHigh` is relaxed to `> -1`, THE SYSTEM SHALL make
  the denial-floor case FAIL with `exp:[]` against a fired
  `MctlAgentPolicyDenialRateHigh{reason="unknown"}`.
- WHILE the denial-floor case is evaluated at `eval_time: 30m`, THE SYSTEM
  SHALL compute a real, non-`NaN` denial share above the `0.20` threshold
  (0.50 on both Prometheus 2.x and 3.x range semantics) and an extrapolated
  denial count below the `> 4` floor (3.0 under 2.x, approximately 3.10 under
  3.x).
- IF the case is evaluated by a Prometheus 3.x promtool with left-open range
  selectors, THEN THE SYSTEM SHALL still kill the relaxed-floor mutation —
  the case must not depend on the `t=0` sample being inside the range.
- WHEN a reader opens the replaced case, THE SYSTEM SHALL present a comment
  that states which clause suppresses the alert, the share and count the input
  produces, and the left-edge range-selector trap that the previous flat-series
  input fell into.
- WHILE this change is in review, THE SYSTEM SHALL keep the two input series
  byte-identical to the mctl-gitops case named `denials below the absolute
  floor stay silent despite a high share` introduced in mctlhq/mctl-gitops#1110.
- IF `go test ./deploy/alerts/... ./docs/...` is run after the change, THEN THE
  SYSTEM SHALL pass — the alert expressions, runbook anchors, and metric names
  are untouched.
- WHEN the PR is opened, THE SYSTEM SHALL record in the PR body that the
  `> 4` to `> -1` mutation was executed and what it produced, on the pinned CI
  promtool version.

## Out of scope

- Any change to the alert expressions in
  `deploy/alerts/mctl-telegram.rules.yaml`. The `MctlAgentPolicyDenialRateHigh`
  expression, its `0.20` share threshold, its `> 4` floor, and the
  `or vector(0)` denominator guard are all correct and stay as they are.
- The mctl-gitops copy of the rules and their unit tests, already fixed in
  mctlhq/mctl-gitops#1110.
- The other eight cases in `mctl-telegram.rules_test.yaml` (the two
  `MctlBridgeDaemonsFlapping` cases, T1, T2, T3, T4a, T5, T6, T7, T8). They were
  mutation-checked and catch what they claim.
- Deploying or changing anything in the cluster. This file is a non-deployed
  mirror; the header of `mctl-telegram.rules.yaml` records why it is kept.
- Rewriting `docs/runbook.md`, `docs/slo.md`, or any Grafana dashboard.

## Open questions

- **Should `.github/workflows/build.yml` also bump `PROM_VERSION` from `2.52.0`
  to a Prometheus 3.x release?** Measured on the clone: under promtool 2.52.0
  the *existing* case already fails the `> -1` mutation (so it is not vacuous
  in this repo's CI today); under promtool 3.5.0 it passes the mutation (the
  behaviour #590 describes). The full existing suite is green under both
  versions with the rule intact, so a bump is low-risk. It is recorded here as
  a separate, optional follow-up rather than folded into this change, because
  #590 scopes itself to the test and its comment. Recommendation: do the series
  fix first (it is version-robust either way), and open a separate issue for
  the toolchain bump.
- The issue states the case "passes whether or not the rule is correct" as an
  unconditional fact. On this repository's pinned toolchain it does not; the
  claim is true only from Prometheus 3.0 onward. The proposal proceeds with the
  fix anyway — the replacement is strictly stronger and version-independent —
  but the PR description and the new comment should state the version
  dependency accurately rather than repeating the unconditional claim.
- promtool unit-test groups support an optional `name:` field, which is how
  mctl-gitops#1110 labels its case. Whether to adopt `name:` here (instead of
  the `T4b:` comment convention the rest of this file uses) is a style call left
  to the implementer; the default is to keep the existing comment convention and
  mention the gitops case name inside the comment.
