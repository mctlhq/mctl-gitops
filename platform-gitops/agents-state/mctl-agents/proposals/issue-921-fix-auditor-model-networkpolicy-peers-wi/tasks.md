# Tasks: issue-921-fix-auditor-model-networkpolicy-peers-wi

- [ ] 1. Add `_peer_admits(peer, policy_ns)` to `tools/agent_isolation_audit.py`, returning `none|all|agents|unknown` as in design.md, with namespace-side and pod-side evaluation ANDed — DoD: pure function, no I/O, docstring states the Kubernetes AND-within-peer / OR-across-peers rule.
- [ ] 2. Add `_policy_admission(pol, policy_ns)` that folds every ingress rule and peer with precedence `all > unknown > agents > none`, treating an absent or empty `from` as `all` (depends on 1) — DoD: one result per policy.
- [ ] 3. Rewrite the cross-namespace branch of `check_east_west` to use `_policy_admission` (depends on 2) — DoD: `all` emits the existing `partial` row with the same text; `agents` emits an `enforced`/`low` row with field `spec.ingress[].from[].namespaceSelector+podSelector`; `unknown` emits a `not-observed`/`medium` row; `none` emits nothing.
- [ ] 4. Switch the `NETPOL` branch of `check_east_west` (the `wide` computation) to the classifier with `policy_ns=NS` (depends on 2) — DoD: `podSelector: {}` is still wide and the detail text is unchanged.
- [ ] 5. Add `SCHEMA_VERSION = 2`, emit `"schema_version"` in JSON `render`, and document the v2 meaning in the module docstring — DoD: `json.loads(out)["schema_version"] == 2`; markdown output unchanged.
- [ ] 6. Run the auditor against a current mctl-gitops `platform-gitops` checkout and paste the before and after `NetworkPolicy/*` rows into the PR description (depends on 3-5) — DoD: `allow-agent-ingress` is `enforced` with the agent-only detail; any other change is explained.

## Tests
All in `tests/test_agent_isolation_audit.py`, built in `tmp_path` like the existing fixtures:
- [ ] T1. Namespace-only peer (`namespaceSelector` = argo-workflows) gives `partial` "whole namespace". The existing `test_cross_namespace_policy_found_by_kind_not_filename` must still pass.
- [ ] T2. Pod-only peer: in a policy in namespace `vault` it gives no cross-namespace row; in the `NETPOL` file, `podSelector: {}` gives east-west `partial` (existing T1/T2 behaviour holds).
- [ ] T3. Combined peer (`namespaceSelector` argo-workflows AND `podSelector` agent label) gives `enforced`, not `partial`.
- [ ] T4. Regression fixture `ALLOW_AGENT_INGRESS`: a literal Python dict copying the mctl-gitops `allow-agent-ingress` shape (namespace `mctl-agents-egress`, port 3128). It is written into the tmp tree and never read from a gitops checkout. Result: `enforced`.
- [ ] T5. Mutation: the same fixture with `podSelector` removed from the peer gives `partial` "admits the whole argo-workflows namespace".
- [ ] T6. Multiple peers (OR): a rule with one agent-only peer and one namespace-only argo-workflows peer gives `partial`. A rule with one agent-only peer and one peer naming another namespace gives `enforced`.
- [ ] T7. Empty selectors: `namespaceSelector: {}` alone gives `partial`; `namespaceSelector: {}` with `podSelector: {}` gives `partial`; a combined peer with `podSelector: {}` gives `partial`.
- [ ] T8. Uncertainty: a `namespaceSelector` with `matchExpressions`, or a combined peer whose `podSelector` has only `{app: other}` or only `matchExpressions`, gives `not-observed`, never `enforced`.
- [ ] T9. Templated and unreadable inputs keep `not-observed` and exit code 2 (the existing tests still pass).
- [ ] T10. JSON output carries `schema_version == 2`; `test_quota_and_markdown_render` still passes.
- [ ] T11. Full module: `pytest tests/test_agent_isolation_audit.py` is green, and the repo's lint/type checks (as configured for `tools/`) are green.

## Rollback
Revert the PR. The auditor is a standalone offline CLI with no deployed state. Reverting restores the
v1 (unversioned) output and the old peer interpretation. mctl-gitops#2292 pins a revision, so it stays on
whatever revision it pinned until it chooses otherwise.
