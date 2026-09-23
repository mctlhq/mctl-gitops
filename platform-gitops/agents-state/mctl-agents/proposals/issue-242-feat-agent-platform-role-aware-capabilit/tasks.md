# Tasks: issue-242-feat-agent-platform-role-aware-capabilit

**Slice 1 of 3 (revision 2, 2026-09-23).** The first implementer attempt on
2026-09-19 read revision 1 (15 tasks, three new modules, a gitops companion
PR and a benchmark) and stopped without committing: "out of scope for a
single Tier 2 implementer run". That judgement was right. This revision
keeps the contract slice only; slices 2 and 3 are listed at the end as
deferred and must not be started in this run. Requirements and design are
unchanged; the slice boundary is on tasks, not on the design.

Slice 1 delivers the ADR and the stdlib-only contract module with its
consequence table and policy-checkpoint seam. It touches no builder, no
prompt, no catalog and no worker path, so it is additive and dead code until
slice 2 wires the gateway.

- [ ] 1. Write `docs/adr/017-capability-discovery-and-gateway-contract.md` in
      the Context / Decision / Alternatives / Non-goals / Platform impact /
      Implementation map shape ADR 007 and ADR 009 use — descriptor shape and
      field owners, sealing and identity rule, the narrowing invariant,
      namespacing/collision rules, gateway routing/identity/failure semantics,
      and the boundary table row mirroring ADR 009 sec. 5. Add the one
      cross-link line to `docs/adr/009-context-snapshot-contract.md` and
      `docs/agent-inventory.yaml`. — DoD: ADR merged, names which decisions
      are normative for `#197`/`#195`/`#196` and may not be reopened.
      Numbering: 011 is already taken three times and 015/016 are claimed by the
      #199 and #198 proposals, so this ADR is 017.

- [ ] 2. Add `orchestrator/capability.py` (depends on 1): stdlib-only frozen
      dataclasses `ProviderRef`, `CapabilityDescriptor`, `CapabilitySet`,
      `ExecutionCorrelation`, `DiscoveryDecision`, `InvocationRecord`,
      `CheckpointVerdict`; `seal()`, `validate()`, `from_dict` with unknown-key
      rejection, `to_log_dict()`, `_require_sha256`, bounded string constants,
      closed reason-code/consequence vocabularies. — DoD: `capability_set_id`
      derives from `content_hash`, `created_at` excluded from the hash, module
      imports nothing outside the stdlib.

- [ ] 3. Add the `PolicyCheckpoint` protocol and `AbsentPolicyCheckpoint`
      adapter to `orchestrator/capability.py` (depends on 2) — DoD: every
      `InvocationRecord` produced with the adapter carries
      `policy_checkpoint: absent`; swapping in a real `#197` implementation
      touches exactly one construction site.

- [ ] 4. Add the checked-in consequence classification table
      (`config/capability-consequence.yaml` plus loader) mapping every
      advertised `mcp__mctl__*` tool to `read-only | mutating | consequential`,
      unclassified defaulting to `consequential` (depends on 2) — DoD: table is
      reviewed, loader is pure, default is fail-safe and tested.

## Tests

- [ ] T1. `tests/test_capability.py` — `seal()` determinism and a golden
      fixture (`tests/fixtures/capability/investigator-capability-set.json`)
      whose `content_hash` is asserted byte-for-byte; `created_at` excluded
      from the hash; `from_dict` rejects unknown keys; `locator`/`summary`
      length bounds enforced.

- [ ] T2. Narrowing invariant — every sealed member's `matched_tool_pattern` is
      an element of `plan_tools` and its `tool_name` matches that pattern; a
      constructed set containing a capability outside `plan.tools` fails
      `validate()`.

- [ ] T4. `PolicyCheckpoint` protocol: a recording fake checkpoint returning
      `denied` yields a `CheckpointVerdict` of `policy-denied` from the pure
      verdict helper, and with `AbsentPolicyCheckpoint` every `InvocationRecord`
      carries `policy_checkpoint: absent` (no gateway, no provider in this slice).

- [ ] T8. No-payload/no-authorization tests, in the style of
      `tests/test_context_snapshot.py`: recursive field-name assertion that no
      `allow`/`deny`/`permit`/`grant`/`authorized` token appears in the
      serialized schema, and a subprocess import-direction assertion that
      `orchestrator/capability.py` loads stdlib only.

- [ ] T5. Consequence table loader — `config/capability-consequence.yaml` parses,
      every advertised `mcp__mctl__*` tool name in the checked-in list has a
      class in `read-only | mutating | consequential`, an unknown name defaults
      to `consequential`, and the loader is pure (no I/O beyond the file read).

## Rollback

Slice 1 is additive: `docs/adr/017-capability-discovery-and-gateway-contract.md`,
`orchestrator/capability.py`, `config/capability-consequence.yaml` and
`tests/test_capability.py` are new files, plus one cross-link line each in
`docs/adr/009-context-snapshot-contract.md` and `docs/agent-inventory.yaml`.
Nothing imports the new module yet. Rollback is deleting the files and the
two cross-link lines; the ADR may also stand as documentation on its own.

## Deferred: slice 2 (gateway and builder) and slice 3 (mode, catalog, bench)

Not part of this run. Kept verbatim from revision 1 so the dependency
numbers stay meaningful; they are re-cut into their own tasks.md when
slice 1 has merged. Slice 2 = tasks 5-8 and 12; slice 3 = tasks 9-11 and
13-15. Task 14 (the mctl-gitops companion PR) still lands only after task
11, for the reason in the sequencing note.

- [ ] 5. Add `orchestrator/capability_gateway.py` `resolve_eligible(plan,
      correlation, providers) -> CapabilitySet` (depends on 2, 4): provider
      connection (remote `mcp.client.streamable_http`, execution-local
      registry), `fnmatch` matching against `ExecutionPlan.tools`, alias
      assignment, collision detection, sealing, structured log line. — DoD: a
      provider that fails to list raises `provider-unavailable` instead of
      sealing a short set; an unmatched advertised tool never appears in the
      set.

- [ ] 6. Add the three in-process gateway tools via `create_sdk_mcp_server` and
      `@tool` — `capability_search`, `capability_describe`, `capability_invoke`
      (depends on 3, 5) — DoD: search returns compact rows with no schemas;
      describe is capped at `MAX_DESCRIBE_IDS` and reports `not-found` for any
      id outside the sealed set; invoke checks membership, then the policy
      checkpoint, then dispatches (remote via session, local in process) and
      returns exactly one reason code on failure.

- [ ] 7. Propagate `#196` correlation metadata on every remote invocation and
      emit `#195`-shaped trace lines for set sealing and each invocation
      (depends on 5, 6) — DoD: trace output contains ids, hashes, counts,
      durations and reason codes only; a grep of the emitted lines finds no
      argument or result text.

- [ ] 8. Extend `orchestrator/options.py`:
      `build_issue_investigator_options_from_plan(..., gateway=None)` with
      `mcp_servers={"capability": ...}`, `allowed_tools` swapping
      `mcp__mctl__*` for `mcp__capability__*`, and `strict_mcp_config=True`
      when a gateway is passed (depends on 6) — DoD: `gateway=None` produces
      options byte-identical to today; no other builder changes.

- [ ] 9. Add `ISSUE_INVESTIGATOR_CAPABILITY_MODE` (`eager` default) and the
      `_capability_mode()` helper to `orchestrator/run_issue_investigator.py`,
      wired into `_run_agent` with the lazy import, the printed
      `[capability] capability_mode=...` line, and rejection of
      `legacy + discovery` at startup (depends on 8) — DoD: unset env var runs
      the unchanged path and never imports `capability_gateway`.

- [ ] 10. Add the discovery-mode-only prompt block to `_build_prompt`
      (search-then-describe-then-invoke) (depends on 9) — DoD: eager-mode
      prompt bytes are unchanged, asserted by a test.

- [ ] 11. Make `orchestrator/validate_manifest.py` mode-aware: read
      `spec.capabilityDiscovery.mode` (absent ⇒ `eager`) and compare the
      profile's `spec.tools` against the builder's `allowed_tools` for that
      mode (depends on 8) — DoD: the existing eager comparison is unchanged and
      still passes against the current catalog, with a fixture proving the
      gateway-mode comparison.

- [ ] 12. Promote `mcp` to a direct pinned dependency in `pyproject.toml` with
      the rationale comment the `httpx` entry uses (depends on 5) — DoD:
      `uv sync --frozen` unchanged, `uv.lock` untouched.

- [ ] 13. Add `tools/capability_bench.py` and the generated
      `docs/benchmarks/capability-discovery.md` (depends on 9) — DoD: records
      initial tool-schema count and serialized bytes, end-to-end input/output
      tokens, cost, turns and wall clock for one fixed issue and target SHA in
      both modes, and states the sample size.

- [ ] 14. Open the mctl-gitops companion PR adding the additive
      `spec.capabilityDiscovery` field to the `ExecutionProfile` schema, with
      the `issue-investigator-default` profile left on `mode: eager` (depends
      on 11) — DoD: mctl-gitops CI green, no mctl-agents test changes required
      by the merge.

- [ ] 15. Record the pilot's state in `docs/resolver-pilot-status.md` (or a
      sibling `docs/capability-pilot-status.md`), including what is live, what
      is blocked, and the rollback switch (depends on 13) — DoD: a reader can
      tell shipped-code from activated-behaviour, the distinction that document
      already insists on.

### Deferred tests

- [ ] T3. Exclusion is total — a provider advertising a tool outside
      `plan.tools` produces no descriptor, no search row, no describe result,
      and `capability_invoke` on its id returns `not-eligible` without any
      provider call (asserted with a recording fake provider).

- [ ] T5. Collision safety — two providers resolving to the same
      `mcp__<alias>__<tool>` name, or claiming the same alias, raise a
      `collision` error at sealing time; no silent rename or shadow.

- [ ] T6. Remote and execution-local capabilities produce the same descriptor
      shape, and a local invocation performs zero network calls (asserted by a
      transport fake that fails on use).

- [ ] T7. Correlation survives discovery to invocation — every invocation's
      metadata equals the `CapabilitySet.execution` block, which equals the
      `ExecutionPlan` pins.

- [ ] T9. Failure taxonomy — `provider-unavailable`, `provider-error`,
      `timeout`, `invalid-arguments`, `not-found` are distinct and never
      collapse into an empty-but-successful discovery.

- [ ] T10. Compatibility/no-expansion — extend `tests/test_options.py`: with
      `gateway=None` the built options equal today's byte-for-byte; in gateway
      mode the union of reachable capabilities is a strict subset of the eager
      allow-list expansion, `mcp_servers` contains no remote entry, and
      `strict_mcp_config` is set.

- [ ] T11. `tests/test_manifest.py` / `validate_manifest` — the current catalog
      (no `capabilityDiscovery` field) still validates exactly as today; a
      gateway-mode fixture validates against the gateway allow-list; a profile
      declaring a mode the builder does not implement fails loudly.

- [ ] T12. `tests/test_worker_isolation.py` — `orchestrator/capability.py` is
      importable in the worker's environment; `orchestrator/capability_gateway.py`
      is never imported at module scope by any worker-reachable module.

- [ ] T13. Mode switch — unset/`eager`/invalid values of
      `ISSUE_INVESTIGATOR_CAPABILITY_MODE` behave as documented (unchanged path,
      unchanged path, `SystemExit`), `legacy + discovery` is rejected, and the
      mode line is printed in every case, mirroring
      `tests/test_run_issue_investigator.py`'s resolver-mode coverage.

- [ ] T14. Benchmark harness unit test — `tools/capability_bench.py`'s
      measurement functions compute schema bytes and token totals from recorded
      fixture messages without invoking a model.

### Sequencing note (from revision 1)
land task 11 (mode-aware validation) before task 14 (the
catalog field), so the cross-repo equality check in
`orchestrator/validate_manifest.py` can never be red on `main` in either
repository — the exact failure `docs/resolver-pilot-status.md` records from the
budget-default change.
