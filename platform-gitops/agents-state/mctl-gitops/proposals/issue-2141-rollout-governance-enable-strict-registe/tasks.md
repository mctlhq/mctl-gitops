# Tasks: issue-2141-rollout-governance-enable-strict-registe

- [ ] 1. Pin the revisions. Record the mctl-gitops `main` SHA, the `image.tag` in `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` (4.122.0 at investigation), the mctl-api commit of that tag, and the mctl-api chart SHA Argo renders (`targetRevision: main`). — DoD: all four values are posted on #2141.
- [ ] 2. (depends on 1) Prove that #721 is deployed. Run `gh api repos/mctlhq/mctl-api/compare/329f17c6c238494947bfe3bcb59a9b5702760a93...<tag>`, which must return `ahead` or `identical`, and check that `admins-mctl-api` is Healthy/Synced. — DoD: both results are recorded.
- [ ] 3. (depends on 1) Determine the effective `ACTION_APPROVAL_MAX_DECISION_AGE` from the live Deployment/pod env (all env sources). An empty value means 24h. Determine the start time of the first #721-capable (4.117.0+) pod. Capture the current boot line `action approval policy` on both replicas. — DoD: the max-age, the window `[start, now]` (at least the max-age), and the boot lines (`require_registered_policy=false`, `registered_rules=[dev-loop.human-approval@v1]`) are recorded. If any of these is unobservable, record a blocker and stop.
- [ ] 4. (depends on 3) Inventory the producers from the authoritative work-items action-approval store, read-only. Count rows by `policy_rule_id`, `policy_version` and state within the window. Also count all `pending` rows, and `approved` rows with `fresh_until > now()`. Classify each group against `governance.Policies`. — DoD: a table is posted on #2141. Every executable group is `ok`, or the result is recorded as no-go. If the store is not reachable, record a blocker and stop.
- [ ] 5. (depends on 4) Check live approvals for incomplete context. Count `pending` rows, and live `approved` rows, that lack mandatory decision context under the #721 contract. — DoD: the count is 0, or the result is recorded as no-go.
- [ ] 6. (depends on 2-5, all clean) Open a PR that adds `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY: "true"`, with the reason, evidence and rollback comment, to the `env:` block of `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`, after `MCTL_AGENT_RECEIPT_GATE`. Make no other change (no image or `ROLLOUT_MARKER` bump). — DoD: the PR diff is that single entry plus its comment, and `validate-manifests.yml` and `claude-review.yml` pass.
- [ ] 7. (depends on 6, merged) Let Argo CD sync normally. — DoD: `admins-mctl-api` is Healthy/Synced on the merge SHA, the image tag is unchanged, and 2/2 replicas are ready.
- [ ] 8. (depends on 7) Capture the strict-mode boot evidence. — DoD: every new pod logs `action approval policy` with `require_registered_policy=true` and `registered_rules=[dev-loop.human-approval@v1]`.
- [ ] 9. (depends on 8) Run the negative fail-closed proof. Send one admin create-action-approval request with an unregistered `policy_rule_id` (for example `rollout-2141.unregistered-probe`). — DoD: the request gets 422 `approval_policy_unregistered`, no row is stored, and nothing is decided or spent.
- [ ] 10. (depends on 8) Run the positive check. The next normal governed DevLoop approval (`dev-loop.human-approval@v1`) is granted and spent with no policy refusal. — DoD: the workflow id and outcome are recorded.
- [ ] 11. (depends on 1-10) Post the evidence bundle on #2141, link it to mctl-api#721, and close the issue. If any gate failed, leave the issue open with the blocking gap instead. — DoD: the comment contains every item from the issue's "Evidence / closure" list.

## Tests

- [ ] T1. `helm template mctl-api <mctl-api chart at pinned SHA> -f <inline values extracted from mctl-api.yaml>` renders `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY=true` in the Deployment env, and otherwise produces the same manifest as before.
- [ ] T2. `yamllint` and `validate-manifests.yml` pass on the changed file.
- [ ] T3. The Argo diff for `admins-mctl-api` shows exactly one env addition before sync.
- [ ] T4. The boot line on all replicas reports strict mode on and the expected rule (task 8).
- [ ] T5. The negative probe returns 422 `approval_policy_unregistered` (task 9).
- [ ] T6. A governed DevLoop approval succeeds under strict mode (task 10).

## Rollback

One GitOps edit. In a PR, remove the `ACTION_APPROVAL_REQUIRE_REGISTERED_POLICY: "true"` line (and its comment) from `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`, or set it to `"false"` (`killSwitchOn` treats empty, `false` and `off` as off). Merge it and let Argo CD resync `admins-mctl-api`. Use `git revert <flip-commit>` for the simplest form. The new pods log `require_registered_policy=false`. No data rollback is needed: strict mode stores nothing, and refused approvals were never spent. Approvals refused at spend while strict mode was on carry `reapproval_required=true` and are re-approved normally. Trigger the rollback if pods are not Healthy, if the boot line is missing or wrong, if `approval_policy_unavailable` appears, or if any legitimate DevLoop approval is refused.
