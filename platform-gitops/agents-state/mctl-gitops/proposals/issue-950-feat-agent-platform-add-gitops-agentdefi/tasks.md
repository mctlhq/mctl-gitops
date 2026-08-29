# Tasks: issue-950-feat-agent-platform-add-gitops-agentdefi

- [ ] 1. Add policy ceilings, approved runtimes/sandboxes, known tool/action
      classification, required policies and permission scopes. Unknown entries
      fail closed.
- [ ] 2. Add schemas for \`agents.mctl.ai/v1alpha2 ExecutionProfile\` and
      \`ReleaseBindingIntent\`. Do not add a second AgentDefinition body or a
      global \`lifecycleState\`.
- [ ] 3. Document split lifecycle authorities exactly as ADR 007 defines.
- [ ] 4. Add initial profiles for investigator, implementer and shepherd with
      explicit policyRef, permissions, bounded limits, runtime, approval and
      evidence. Compare effective options plus CWFT overrides; implementer is
      $20/2400s.
- [ ] 5. Pin canonical v1alpha2 AgentDefinitions through
      \`sourceManifest {repo,path,gitSha}\`; never mirror prompts/triggers/body.
- [ ] 6. Add only non-promotable/shadow release-intent fixtures until exact
      immutable registry versions exist. Each contains one exact compatible
      definition/profile pair.
- [ ] 7. Implement \`scripts/validate-agent-platform.py\` and wire it into
      manifest CI.
- [ ] 8. Add negative fixtures for missing owner/policy/permissions/bounds,
      unknown references, write without scope/approval, incompatible/missing/
      ambiguous/disabled versions, global lifecycleState, unapproved sandbox,
      and independent-half rollback.
- [ ] 9. Add transition tests for publish, atomic promote, deprecate, disable,
      and exact-pair rollback using a deterministic registry fake/export.
- [ ] 10. Document source-of-truth boundaries, effective-value extraction,
      and the production dependency on registry reconciliation.

## Tests

- [ ] T1. Real catalog validation exits 0.
- [ ] T2. Every negative fixture independently exits non-zero.
- [ ] T3. Existing Helm/kubeconform checks remain green.
- [ ] T4. Every ADR 007 validation expectation maps to a named test.
- [ ] T5. No running agent, CWFT, mctl-api schema, or production binding changes.
- [ ] T6. Rollback restores one recorded exact pair and rejects synthetic pairs.

## Rollback

The implementation is additive and not runtime-load-bearing. Revert the
catalog/schema/validator commit and CI step. Future operational rollback uses
the exact prior registry binding tuple.