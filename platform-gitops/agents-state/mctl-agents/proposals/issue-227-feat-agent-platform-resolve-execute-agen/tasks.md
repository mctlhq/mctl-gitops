# Tasks: issue-227-feat-agent-platform-resolve-execute-agen

- [ ] 1. Add v1alpha2 AgentDefinition parsing while preserving v1alpha1 and
      unknown-version hard failure.
- [ ] 2. Migrate only the canonical issue-investigator manifest to v1alpha2
      with \`executionProfileRef {name,compatibility}\`.
- [ ] 3. Add a #950-schema-compatible profile under
      \`tests/fixtures/resolver/profiles/\`, not a new production catalog.
      Include explicit policyRef, permissions, $3 budget, 7200s timeout,
      runtime, approval and evidence.
- [ ] 4. Add a release fixture with
      \`bindingSource: compatibility-fixture\`, \`promotable: false\`, exact
      definition/profile hashes and a deterministic fixture revision.
- [ ] 5. Implement frozen ExecutionPlan with exact versions/revision/source,
      model-policy version, prompt/skill hashes, tools, policy/permissions,
      limits, runtime/sandbox, target SHA, approval and evidence.
- [ ] 6. Implement \`execute(agent, task)\`; check definition compatibility
      against the concrete selected profile version and fail closed before
      Argo for every invalid v1alpha2 state.
- [ ] 7. Add explicit
      \`ISSUE_INVESTIGATOR_RESOLVER_MODE=legacy|declarative\`, default legacy.
      Declarative errors never fall back silently.
- [ ] 8. Drive investigator options/CWFT submission from one resolved plan and
      emit a structured snapshot without changing caller shape.
- [ ] 9. Preserve slug/idempotency, proposal triplet, status source, issue
      comment and stop-at-proposed behavior.
- [ ] 10. Add options-builder equivalence, deterministic snapshot, policy/
      permission, failure-before-submit, fixture isolation, and rollback tests.
- [ ] 11. Document production activation as blocked on #950 real registry
      binding resolution and removal of compatibility fixtures.

## Tests

- [ ] T1. v1alpha1 remains valid; unknown versions fail.
- [ ] T2. Valid v1alpha2 definition/profile resolves.
- [ ] T3. Missing/ambiguous/disabled/incompatible/unknown/unbounded/unapproved
      cases fail before Argo.
- [ ] T4. Compatibility is evaluated against the selected profile version.
- [ ] T5. Same fixture/task/target SHA produces identical immutable plan.
- [ ] T6. Legacy and declarative options are equivalent.
- [ ] T7. Proposal remains proposed and caller contract is unchanged.
- [ ] T8. Fixture cannot be interpreted as promotable registry state.
- [ ] T9. Explicit legacy rollback reproduces current behavior.

## Rollback

Set resolver mode to legacy. If code rollback is required, revert the resolver,
fixtures and investigator v1alpha2 migration together; untouched v1alpha1
agents continue to load.