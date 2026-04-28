# Tasks: clawhub-skills-allowlist

- [ ] 1. Inventory the current Layer 3 (remote) skills in all three tenants (ovk, labs, admins) — DoD: a list of all registered remote skill origins/URLs is captured, legitimate origins are identified and confirmed by each tenant's operator
- [ ] 2. Decide the allowlist enforcement mechanism in openclaw: native config vs ingress middleware (depends on 1) — DoD: the upstream changelog and openclaw configuration are reviewed for a built-in remote-skill allowlist; an approach (config-based or middleware) is chosen and the decision is captured
- [ ] 3. Add the field `skills.remoteAllowlist` to the Helm values schema and template for each tenant (depends on 2) — DoD: the field is added to the values schema with documentation; the fail-closed default (empty list = deny-all) is set explicitly in the template
- [ ] 4. Implement allowlist enforcement in the openclaw config or ingress middleware (depends on 3) — DoD: when registering a Layer 3 skill with an origin outside the allowlist the API returns 403; on an empty allowlist all registrations are blocked
- [ ] 5. Populate the allowlist for admins with origins confirmed by inventory and deploy (depends on 4) — DoD: manifests are updated in mctl-gitops, the PR passes review, ArgoCD applies the config, legitimate skills in admins work
- [ ] 6. Populate the allowlist for labs with confirmed origins and deploy (depends on 5) — DoD: same as admins; RAM is unchanged (configuration-only change)
- [ ] 7. Populate the allowlist for ovk with confirmed origins and deploy (depends on 6) — DoD: same; the production client confirms all used Layer 3 skills work
- [ ] 8. Add a CI step to mctl-gitops: detect new remote skill sources in the PR diff (depends on 3) — DoD: the CI script is added, a test demonstrates blocking a PR with a new unapproved origin and passing a PR with an origin already in the allowlist
- [ ] 9. Document the new skill source approval process (allowlist update workflow) (depends on 8) — DoD: an operator-facing instruction is added to the README or runbook; the process includes a security review and an allowlist update in values.yaml

## Tests
- [ ] T1. Attempt to register a test Layer 3 skill with an arbitrary URL `https://evil.example.com/skill` on each tenant — expected: 403, the skill is not registered
- [ ] T2. Register a test Layer 3 skill with a URL from the tenant's allowlist — expected: 200, the skill is registered and works
- [ ] T3. Verify fail-closed: remove the allowlist from the tenant's values (or set it to an empty list) — expected: all Layer 3 skill registration attempts are blocked
- [ ] T4. CI test: open a PR with a new origin in a skill manifest without adding it to the allowlist — expected: the CI step fails with an informative message
- [ ] T5. CI test: open a PR with an origin already in the allowlist — expected: the CI step passes
- [ ] T6. Verify that existing legitimate Layer 3 skills on all tenants continue to work after enabling the allowlist

## Rollback
If the allowlist causes an unexpected block of legitimate skills in production (ovk):
1. Temporarily widen the allowlist: add the blocked origin to ovk's `values.yaml` and deploy via gitops — the change applies without a restart (hot-reload)
2. If hot-reload does not take effect: perform a rolling restart of the ovk pod (the restore-state probe will recover sessions from S3)
3. Inventory and add the missing origin to the allowlist permanently
4. If the enforcement mechanism is broken and the allowlist must be fully disabled: remove the `skills.remoteAllowlist` field from values or set it to `null` — returns to pre-introduction behaviour (no restrictions)
