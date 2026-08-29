# Tasks: issue-226-architecture-agent-platform-define-agent

- [ ] 1. Draft `docs/adr/007-agent-definition-execution-profile-contract.md`
      following the `docs/adr/005-*`/`006-*` format (Context / Decision /
      Non-goals / Implementation map), incorporating: the `AgentDefinition`
      vs `ExecutionProfile` field lists, the lifecycle state machine and
      transition table, and the four-layer source-of-truth table from
      design.md — DoD: file exists, covers all five contract points from the
      issue's Scope section, and every field/state named in it traces to a
      real file/symbol already read in this investigation (`orchestrator/manifest.py`,
      `docs/agent-inventory.yaml`, `orchestrator/temporal/activities/registry.py`,
      `orchestrator/temporal/activities/state.py`) or is explicitly marked "new".
- [ ] 2. In the ADR, add the explicit versioning/compatibility section
      covering: `apiVersion` bump path (`v1alpha1` → `v1alpha2`, additive,
      dual-support window), `AgentDefinition` version bump triggers,
      `ExecutionProfile` version bump triggers (independent of definition
      version), prompt/skill input hashing carried over unchanged from
      `docs/agent-inventory.yaml`'s `promptSources`/`runtimeContextInputs`
      split, and environment-release rollback semantics building on the
      existing `mctl_rollback_agent` "revert to from_version" behavior
      (depends on 1) — DoD: a reviewer can answer "what version fields
      change when I edit only a manifest's owner" and "...only its budget"
      from the ADR alone, with two different answers.
- [ ] 3. In the ADR, map `issue-investigator`, `implementer`, and `shepherd`
      into the new model as a table: owner, `executionProfileRef` (profile
      name — one row for the profile's model/tools/budget/timeout/sandbox/
      approval), and lifecycle state each would start in (`active`, since
      all three are already running today) (depends on 1) — DoD: every
      cell is sourced from the corresponding `agents/_manifests/<agent>/agent.yaml`
      and `docs/agent-inventory.yaml` entry, not invented; shepherd's `mcp_servers={}`
      / no-mctl-MCP-access note and implementer's `riskLevel: high` /
      "the only agent that authors code" note are both represented in the
      table (e.g. as the `approval` field being unset for investigator,
      required for implementer/shepherd's mutating steps).
- [ ] 4. In the ADR, write the migration-path section: how existing
      `agent.yaml` files, existing mctl-api registry versions, and existing
      environment releases stay valid with zero required action, and what
      the one-time, per-agent opt-in migration step to `v1alpha2` +
      profile-split looks like (depends on 1, 2) — DoD: explicitly states
      "no existing registry row is invalidated by merging this ADR" and
      lists the exact fields that move from `agent.yaml`'s `spec.toolPolicy`/
      `spec.execution` into the new profile file.
- [ ] 5. Cross-link the ADR from `docs/agent-inventory.yaml`'s header
      comment and from `docs/adr/README.md` (or the ADR index, if one
      exists — the doc's file listing showed only 005/006 with no index
      file; add a short index note there if the repo has one, otherwise
      skip) so the next reader of either finds the other (depends on 1) —
      DoD: a one-line pointer added at both ends, no content duplicated.
- [ ] 6. Circulate the ADR against the two named follow-up issues (GitOps
      catalog-schema, runtime-resolver, both children of mctlhq/.github#18)
      before either starts implementation, confirming each of their authors
      can answer the acceptance criterion "can implement the contract
      without reopening ownership or lifecycle decisions" (depends on 1-4)
      — DoD: no open ownership/lifecycle question remains unresolved in the
      ADR; any raised during circulation is folded back into task 1-4's
      output, not left as a follow-up open question.

## Tests

- [ ] T1. Documentation-only diff check: `git diff --stat` for this
      proposal's implementation touches only `docs/adr/007-*.md` (plus the
      two cross-link one-liners in task 5) — no `.py`, no `agent.yaml`,
      no `docs/agent-inventory.yaml` field value change. Enforces the
      "does not change runtime behavior" acceptance criterion mechanically.
- [ ] T2. Manual conformance check: for each of the nine EARS acceptance
      criteria in requirements.md, locate the exact ADR section/table that
      satisfies it and record the mapping (criterion -> section) in the PR
      description. A criterion with no matching section is a gap, not a
      passed test.
- [ ] T3. Re-run `uv run python -m orchestrator.validate_manifest` and
      `uv run pytest tests/test_agent_inventory.py tests/test_manifest.py`
      after this change lands, to confirm the (unmodified) manifest/inventory
      contract still passes — proves the ADR-only change had zero effect on
      the checked behavior it documents.
- [ ] T4. Have a second reviewer (or a fresh agent session) read only the
      ADR (not this requirements/design pair) and attempt to answer "which
      of `AgentDefinition`/`ExecutionProfile` would I edit to change
      implementer's budget without touching its owner or prompt" — passes
      if they answer "ExecutionProfile" without consulting this proposal's
      design.md.

## Rollback

This proposal produces only new/edited Markdown (the ADR file plus two
cross-link lines) — no code path, manifest, or registry state depends on it
existing. Rollback is `git revert` of the ADR commit (or deleting
`docs/adr/007-agent-definition-execution-profile-contract.md` and reverting
the two cross-link edits from task 5). Because no downstream issue may begin
implementation until this ADR is accepted (task 6's gate), a rollback here
can never strand an in-flight schema/resolver change — those issues simply
have not started yet. If a schema/resolver issue is later found to have
already started against a draft of this ADR before it was reverted, that
issue's own branch is the unit to roll back, not this one.
