# Design: issue-921-fix-auditor-model-networkpolicy-peers-wi

## Current state
`tools/agent_isolation_audit.py` is a read-only static auditor over a `platform-gitops` checkout. It has no
network access and starts no subprocess. Its NetworkPolicy checks are:

- `check_egress` / `_agent_egress_policies` / `_selects_agents` decide whether an Egress policy in
  `argo-workflows` selects agent pods. `_selects_agents` counts a selector only when every `matchLabels`
  entry is `AGENT_LABEL` and there are no `matchExpressions`. This is conservative proof, and it is not
  touched here.
- `check_east_west` handles two kinds of policy:
  - Policies in `NETPOL` (`argo-workflows/config/networkpolicy.yaml`). It flags a policy as "wide" when an
    ingress peer is exactly `podSelector == {}`. Other broad shapes are missed: `namespaceSelector: {}`
    with no podSelector, or `{namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: argo-workflows}}}`
    in the same namespace.
  - Other scanned policies (lines 363-371). For each one it checks
    `any((f.get("namespaceSelector") or {}).get("matchLabels", {}).get("kubernetes.io/metadata.name") == NS ...)`
    and emits `partial` "admits the whole argo-workflows namespace, agent pods included". It never reads
    `f.get("podSelector")`, which causes the false positive. A `namespaceSelector` using
    `matchExpressions`, or `namespaceSelector: {}`, is silently skipped. Silence there is an unobserved gap
    that the output presents as no finding.
- `render` emits JSON `{files_read, templates, rows}` with no version key. Markdown is a plain table.
- Tests are in `tests/test_agent_isolation_audit.py`. They build fixture trees in `tmp_path` (`_tree`,
  `_rows`, `_find`). `test_cross_namespace_policy_found_by_kind_not_filename` covers the namespace-only peer
  (`vault-in` -> `partial`).
- The repo has no `CLAUDE.md`. The only design doc is `docs/spikes/807-agent-isolation-k8s.md`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/infra-components/mctl-platform/mctl-agents-egress-proxy/networkpolicy.yaml`
  (mctl-gitops `633112e3`). `allow-agent-ingress` in namespace `mctl-agents-egress` has
  `spec.podSelector: {}`, and one ingress peer
  `{namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: argo-workflows}}, podSelector: {matchLabels: {app.kubernetes.io/name: mctl-agents}}}`
  on port 3128/TCP.
- `$MCTL_GITOPS_ROOT/argo-workflows/config/networkpolicy.yaml`: `allow-argo-workflows-ingress` with
  `from: [{podSelector: {}}, namespaceSelector traefik/kube-system/monitoring/mctl-api/admins ...]`.
- I ran `python3 -I tools/agent_isolation_audit.py --gitops-root $MCTL_GITOPS_ROOT --format json` from the
  clone. Six `NetworkPolicy/cross-namespace` `partial` rows came back: `allow-vault-ingress`,
  `allow-backstage-ingress`, `allow-mctl-api-ingress`, `allow-shared-pg-ingress`, `allow-agent-ingress` and
  `allow-otel-collector-ingress`. There were also three templated `not-observed` rows. East-west is `partial`
  and egress is `absent`. JSON top-level keys: `files_read`, `rows`, `templates` (no version).
- I did not read the bodies of the other five cross-namespace policies. This proposal only requires that
  they stay reported when their peers really are namespace-wide. Task 5 re-runs the auditor to confirm
  that.
- mctl-gitops was searched for an existing consumer or baseline of this auditor
  (`agent_isolation_audit`, `isolation_baseline`). Nothing was found. #2292 is not merged in this checkout,
  so its expected baseline format could not be observed (see Open questions in requirements.md).
- No MCP tools were needed. The auditor's input is gitops files, not a running service.

## Proposed solution
All changes go into `tools/agent_isolation_audit.py` and its test module.

1. **Peer classifier.** Add a pure function
   `_peer_admits(peer: dict, policy_ns: str | None) -> str` that answers "which argo-workflows pods does
   this one peer admit?". It returns one of:
   - `"none"`: the peer provably does not select `argo-workflows`. Cases: `ipBlock`; a namespaceSelector
     whose `matchLabels["kubernetes.io/metadata.name"]` names another namespace; a pod-only peer in a policy
     whose namespace is not `argo-workflows`.
   - `"all"`: the peer selects `argo-workflows` (or every namespace) and its pod side is absent or `{}`.
   - `"agents"`: the peer selects `argo-workflows` and the pod side's `matchLabels` contain the
     `AGENT_LABEL` pair. Extra labels or expressions only narrow the set, so the result is still a subset
     of agent pods.
   - `"unknown"`: the auditor cannot decide. Examples: the namespace side uses `matchExpressions` without a
     decisive `kubernetes.io/metadata.name` label; the pod side has selectors that neither include nor
     exclude the agent label; a pod-only peer in a policy with no `metadata.namespace`.

   Namespace side:
   - Absent `namespaceSelector`: the peer means the policy's own namespace.
   - `{}`: every namespace.
   - A `matchLabels` name equal to `NS`: selects `argo-workflows`. Any other labels or expressions alongside
     it are ignored, because ignoring them can only over-approximate (report broader). That is the safe
     direction for an auditor.
   - A name different from `NS`: `none`.
   - Anything else: `unknown`.

   This reproduces the Kubernetes rule that the selectors inside one peer are ANDed. The peers in a `from`
   list are ORed, and an absent or empty `from` admits all sources.
2. **Rule/policy aggregation.** Add `_policy_admission(pol, policy_ns) -> str`. It folds every peer of every
   ingress rule with the precedence `all > unknown > agents > none`, so OR across peers keeps the broadest
   result. A rule with an empty or absent `from` counts as `all`.
3. **`check_east_west`, cross-namespace branch.** Replace the inline `any(...)` with `_policy_admission`:
   - `all`: the existing `partial` row, with the same primitive, field and detail text, so existing baselines
     stay stable.
   - `agents`: an `enforced` row, severity `low`, field `spec.ingress[].from[].namespaceSelector+podSelector`,
     detail `admits only agent pods (app.kubernetes.io/name=mctl-agents) from argo-workflows`.
   - `unknown`: a `not-observed` row, severity `medium`, detail `peer selector not statically decidable`.
     This replaces today's silent skip and never turns into `enforced`.
   - `none`: no row, as today.
4. **`check_east_west`, `NETPOL` branch.** Compute `wide` with the same classifier and `policy_ns = NS`, so
   that `podSelector: {}`, `namespaceSelector: {}` and a self-namespace selector are all recognised as
   namespace-wide. Detail text is unchanged.
5. **Schema version.** Add `SCHEMA_VERSION = 2` and the top-level key `"schema_version": SCHEMA_VERSION` in
   the JSON `render`. Document in the module docstring that version 2 means peers are evaluated as the
   intersection of namespaceSelector and podSelector, and that unversioned output is v1. Markdown output is
   unchanged.

This keeps the module's existing style: small pure helpers, `Row` tuples, and conservative proof before
`enforced` (the same posture as `_selects_agents`).

## Alternatives
- **Add only `and not f.get("podSelector")` to the existing `any(...)`.** This is the smallest diff, but
  any podSelector, including an unrelated or empty one, would silence the row. `podSelector: {}` would be
  treated as narrow, and the auditor would still skip `matchExpressions` and `namespaceSelector: {}`.
  Rejected, because it trades one misclassification for others.
- **Use a Kubernetes label-selector library, or evaluate against live pod labels.** That would be exact,
  but the auditor is deliberately offline and dependency-light (no Kubernetes client, no network; checked by
  `test_t7_pure_and_deterministic`). Rejected.
- **Report agent-only admission as `partial`, with different text.** That keeps the false positive the
  issue asks to remove, and it blocks #2292 from treating the egress proxy as clean. Rejected. Whether
  agent-only reachability of a namespace should be its own primitive is recorded as an open question.

## Platform impact
- No migrations and no runtime service changes. The auditor is a CLI run against a checkout.
- Output changes:
  - The `allow-agent-ingress` row flips from `partial` to `enforced`.
  - Previously silent undecidable peers now appear as `not-observed`.
  - Previously missed `namespaceSelector: {}` peers now appear as `partial`.
  - JSON gains `schema_version`. Consumers that compare full JSON documents must accept the new key. #2292
    is the only planned consumer, and it pins this version.
- Risk: the classifier is too generous with `agents`. Mitigation: only an exact `AGENT_LABEL` pair in
  `matchLabels` qualifies, and a mutation test (podSelector dropped, which must give `partial`) plus a
  non-agent-label test (which must not give `enforced`) guard it.
- Risk: the other five cross-namespace rows change status. Mitigation: task 5 re-runs the auditor against
  the gitops checkout, and the PR description records the before and after rows.
