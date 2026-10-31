# Fix the agent-isolation auditor to evaluate NetworkPolicy peers as namespaceSelector AND podSelector

## Context
`tools/agent_isolation_audit.py` (#807) flags any cross-namespace NetworkPolicy ingress peer whose
`namespaceSelector` names `argo-workflows` as "admits the whole argo-workflows namespace, agent pods
included". It does this without looking at a `podSelector` in the same peer. Under Kubernetes
NetworkPolicy semantics, a single peer carrying both selectors admits the intersection: pods matching
`podSelector` inside namespaces matching `namespaceSelector`. Run against the current mctl-gitops
checkout, the auditor reports the egress proxy's `allow-agent-ingress` policy (namespace
`mctl-agents-egress`) as namespace-wide, although its peer selects only `app.kubernetes.io/name: mctl-agents`
pods. That is a false positive.

mctlhq/mctl-gitops#2292 wants to make auditor regressions blocking in GitOps PR CI, and it pins an
auditor revision to do that. Before then, the auditor has to model peers correctly. Its JSON output also
needs an explicit schema version, so the consumer can pin the interpretation it compares against.

## User stories
- AS a platform operator I WANT the auditor to evaluate a combined namespace+pod peer as an intersection SO THAT a deliberate agent-only allowance (the #2159 egress proxy) is not reported as namespace-wide admission.
- AS the mctl-gitops CI maintainer I WANT a versioned JSON output SO THAT I can pin the peer interpretation my baseline was recorded against.
- AS a security reviewer I WANT genuinely broad peers and unparseable selectors still reported SO THAT the fix cannot hide a real isolation gap.

## Acceptance criteria (EARS)
- WHEN an ingress peer has `namespaceSelector` selecting `argo-workflows` AND a `podSelector` whose `matchLabels` contain `app.kubernetes.io/name: mctl-agents` THE SYSTEM SHALL classify the peer as admitting agent pods only, and SHALL NOT emit the "admits the whole argo-workflows namespace" `partial` row for it.
- WHEN an ingress peer has `namespaceSelector` selecting `argo-workflows` and no `podSelector`, or an empty `podSelector: {}` THE SYSTEM SHALL classify the peer as admitting the whole namespace and SHALL emit the existing `NetworkPolicy/cross-namespace` `partial` row.
- WHEN an ingress peer has an empty `namespaceSelector: {}` (all namespaces) and no `podSelector`, or an empty one THE SYSTEM SHALL classify it as admitting the whole `argo-workflows` namespace.
- WHEN an ingress peer has only a `podSelector` THE SYSTEM SHALL resolve it against the policy's own namespace, and SHALL NOT treat it as admitting `argo-workflows` pods unless the policy is in `argo-workflows`.
- WHEN a rule lists several peers in `from` THE SYSTEM SHALL treat them as a union (OR), and the broadest classification found SHALL determine the row.
- IF a peer selecting `argo-workflows` has a `podSelector` the auditor cannot prove selects only agent pods, or does not select them at all (for example `matchExpressions` only, or unrelated labels) THEN THE SYSTEM SHALL emit a `not-observed` row naming the policy, never `enforced`.
- IF a `namespaceSelector` uses `matchExpressions`, or labels other than `kubernetes.io/metadata.name`, so that the auditor cannot decide whether it selects `argo-workflows` THEN THE SYSTEM SHALL emit a `not-observed` row rather than skipping the peer.
- WHEN the `podSelector` is removed from the `allow-agent-ingress` regression fixture THE SYSTEM SHALL report the policy as admitting the whole namespace (`partial`).
- WHILE input files are unreadable or templated THE SYSTEM SHALL keep the current `not-observed` and exit-code-2 behaviour unchanged.
- WHEN `--format json` is used THE SYSTEM SHALL include a top-level integer `schema_version` equal to `2`. The previous, unversioned output is implicitly version 1.
- WHEN the full test module `tests/test_agent_isolation_audit.py` runs THE SYSTEM SHALL pass, including every pre-existing test unchanged in intent.

## Out of scope
- Changing any NetworkPolicy in mctl-gitops.
- Closing gaps that are currently accepted in a baseline, such as the other five `NetworkPolicy/cross-namespace` `partial` rows on today's checkout.
- Duplicating the pod-security validator.
- Modelling `ipBlock` peers, ports, or egress-side cross-namespace peers in this change.
- Rendering Helm templates (they stay `not-observed`).

## Open questions
- Status of an agent-only admission row. The proposal emits an `enforced` row of severity `low` whose detail says the policy admits only agent pods, as an explicit agent allowance. This means the namespace-wide-admission property holds. It does not judge whether agents should reach that destination at all. Should agent-only admission into a namespace other than the egress proxy be flagged by a separate, later primitive? This proposal does not do that.
- Whether mctl-gitops#2292 also wants `schema_version` in `--format md` output. The proposal adds it to JSON only, because the markdown is a pure table and an existing test asserts its first line.
