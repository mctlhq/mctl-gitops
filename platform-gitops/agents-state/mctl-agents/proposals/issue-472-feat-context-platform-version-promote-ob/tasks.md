# Tasks: issue-472-feat-context-platform-version-promote-ob

> **Correction 2026-09-27.** This proposal is intentionally split into three
> separately approved/mergeable slices. Slice A is behaviour-neutral contract
> work. Slice B may not start until mctlhq/mctl-agents#526 has landed and can
> produce the production evidence required below. Slice C records the operator
> lifecycle and soak proof. One DevLoop approval must never authorize all three
> slices at once.

## Slice A — inert contract, catalog and validation

- [ ] 1. Write `docs/adr/019-context-strategy-release-contract.md` (019 is the
      next free number in `docs/adr/`; 016 is occupied by the shepherd merge-approval ADR and 017/018 are also taken). It fixes: the `ContextStrategyVersion` and
      `ContextStrategyBinding` shapes; the `implementationHash` encoding; the
      reuse of ADR 007's `published`/`deprecated`/`disabled` version lifecycle
      and its `publish`/`promote`/`deprecate`/`disable`/`rollback` transition
      table; the `off/observe/enforce/only` ladder; the `evidence` seam to
      mctlhq/mctl-agents#266; the source-of-truth boundary (git owns desired
      catalog state, the snapshot and the execution record own what ran); and a
      restatement of ADR 009 sec. 5 ("context relevance is never an
      authorization mechanism") as normative for everything below.
      — DoD: ADR merged with `Status: proposed`, cross-linked from ADR 009's
      follow-up table and from ADR 015's non-goal line, and it states which of
      its own decisions a follow-up may not reopen, in ADR 007/009's style.

- [ ] 2. Add ADR 009 **amendment 2** to
      `docs/adr/009-context-snapshot-contract.md` and implement it in
      `orchestrator/context_snapshot.py`: `ContextStrategy` (`:649-678`) gains
      optional `release_revision: int | None` and `content_hash: str | None`.
      `to_dict()` omits each when unset; they enter the snapshot's
      `content_hash` only when present; `from_dict` accepts them and still
      rejects every unknown key; `content_hash`, when set, is validated by the
      existing `_require_sha256`. Follow amendment 1's `conflicts` precedent
      byte-for-byte (`:866-867`, `:1202-1206`).
      — DoD: `tests/fixtures/context/investigator-snapshot.json` and its
      asserted hash are **unchanged**, and a new test proves a snapshot sealed
      without the two fields has a `snapshot_id` identical to one sealed before
      this change.

- [ ] 3. Create the catalog: `config/context-strategies/versions/
      deterministic-fixed-order/1.0.0.yaml`,
      `config/context-strategies/versions/trust-freshness-ranked/1.0.0.yaml`,
      and a **shadow-only** binding at
      `config/context-strategies/bindings/shadow/issue-investigator.yaml`
      whose revision 1 pins `deterministic-fixed-order 1.0.0` — today's
      default, made explicit, with `evidence: {kind: none}` and a reason
      recording that revision 1 is the inert baseline. Do **not** create a
      production binding in Slice A. (depends on 1)
      — DoD: the shadow binding resolves to exactly the strategy the
      investigator runs today; no behaviour changes because nothing reads it
      yet; there is no production promotion that could be mistaken for having
      passed an evidence gate.

- [ ] 4. Add `tools/context_release.py` with `publish`, `promote`, `rollback`
      and `resolve` subcommands, modelled on `tools/publish_agent_release.py`
      (argparse, `--dry-run`, non-2xx/failure returned as a value not an
      exception, per-target isolation so one bad document never half-writes the
      catalog). `publish` computes `contentHash` over the version document
      minus that field, and `implementationHash` over the declared files in
      sorted path order as length-prefixed `"<len>\n<path><len>\n<bytes>"`
      pairs — the exact encoding, and the exact ambiguity rationale,
      `publish_agent_release.prompt_hash` already documents. (depends on 3)
      — DoD: `publish` regenerates task 3's two version documents byte-for-byte
      from the committed code; `promote` and `rollback` refuse to mutate or
      drop any existing revision.

- [ ] 5. Add `orchestrator/context_release.py`: the frozen
      `ContextStrategyVersion` / `ContextStrategyBinding` /
      `ResolvedContextStrategy` types, `load_version`, `load_binding`,
      `resolve(agent, environment)`, and the pure `promote()` / `rollback()`
      document builders. Reading and hashing follow
      `resolver._read_yaml_and_hash` — parse and hash the same bytes. Every
      check is a raise naming the file and the fix, in
      `resolver.load_release_binding`'s style (`resolver.py:768-862`):
      apiVersion/kind allow-list, path-vs-`metadata.{agent,environment}`
      cross-check, positive-integer strictly-increasing gapless revisions,
      non-`disabled` lifecycle, and recomputation of both hashes against the
      files in the running image. Production promotion validation additionally
      requires `evidence.kind: context-eval`, exact strategy/version/
      `contentHash`/`implementationHash` identity, newest observation age
      <= **7 days**, at least **3 consecutive observe-mode investigations**,
      and no `hash-mismatch` verdict. Missing, stale and mismatched evidence
      have distinct closed-vocabulary refusal codes. Verdicts are a closed
      vocabulary, in `orchestrator/lifecycle/contract.py`'s style: anything
      outside it is `unknown`, never silently `ok`. (depends on 3)
      — DoD: unit tests cover every refusal path; a hash mismatch raises with
      the exact `tools/context_release.py publish` command in the message.

## Slice B — rollout wiring and observation

**Hard prerequisite: mctlhq/mctl-agents#526 is merged and available on the
running image.** Before Slice B starts, republish any strategy version whose
conservative whole-file `implementationHash` was invalidated by #526.

- [ ] 6. Add the rollout ladder to `orchestrator/context_release.py`:
      `OFF/OBSERVE/ENFORCE/ONLY`, `_ORDER`, `ENV_VAR =
      "CONTEXT_RELEASE_ROLLOUT_MODE"`, `REQUIRED_ENV_VAR =
      "CONTEXT_RELEASE_REQUIRED"`, and `mode()`, `at_least()`,
      `binding_is_observed()`, `binding_decides()`, `binding_is_sole_selector()`,
      `blocks_on_unknown()`. Copy `work_context/rollout.py`'s rules verbatim:
      an unrecognised value answers `off` and warns rather than raising, and
      each switch is read in exactly one module. Document the three-switch
      table (`ISSUE_INVESTIGATOR_CONTEXT_MODE` = does assembly happen at all;
      `CONTEXT_RELEASE_ROLLOUT_MODE` = which strategy;
      `CONTEXT_RELEASE_REQUIRED` = break-glass inside enforce/only) in the
      module docstring, as both existing ladders do. (depends on 5)
      — DoD: with the env var unset, every predicate answers the `off` value
      and no catalog file is opened.

- [ ] 7. Wire selection into `orchestrator/context_assembly.py`. Add
      `resolve_strategy_for_run(agent, config)` which, at `off`, returns
      `(config.strategy, None)` with no import of `context_release`; past
      `off`, imports `context_release` **inside the function body** — the
      deferred-import pattern `_work_context_active`/`_client`/
      `_persist_to_work_item_store` already use (`:1243`, `:1256`, `:1287`) —
      and returns the resolved strategy. At `only`, a set
      `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY` is a hard error. At `enforce`/`only`
      an unresolvable binding raises when `blocks_on_unknown()`, else falls back
      to `deterministic-fixed-order` with reason code
      `binding-unresolved-fallback-default`. (depends on 6)
      — DoD: `tests/test_worker_isolation.py` and
      `tests/test_context_snapshot.py`'s import-direction test pass unchanged,
      proving `context_assembly`'s module-scope import graph is still
      stdlib-only.

- [ ] 8. Implement the `observe` shadow pass in `assemble()`
      (`context_assembly.py:1083`): after the authoritative
      `run_pipeline(candidates, config, now)` call (`:1106`), run
      `run_pipeline(candidates, replace(config, strategy=bound), now)` on the
      same pre-pipeline candidate list — safe by `run_pipeline`'s own
      documented contract (pure, copies its candidates, ADR 015 sec. 4's
      double-run requirement, `:1008-1016`). Seal the candidate outcome locally
      only to obtain its `snapshot_id`. It must never reach `seal()`'s return
      value, `AssemblyResult.rendered` (`:1128-1130`), or
      `_persist_to_work_item_store` (`:1222`). (depends on 7)
      — DoD: a test asserts the authoritative snapshot's `content_hash` is
      byte-identical with the observe pass enabled and disabled, and a test
      asserts the persist client is called exactly once per run at `observe`.

- [ ] 9. Observability. Extend `AssemblyMetrics` (`:259`) and
      `to_log_dict()` (`:286`) with `release_mode`, `binding_revision`,
      `strategy_content_hash`, `override_active`. Add a
      `CONTEXT_STRATEGY_RELEASE` line (one resolution verdict per run) and a
      `CONTEXT_STRATEGY_COMPARE` correlation line carrying only the two
      strategy identities, binding revision and the two `snapshot_id`s.
      **Do not reimplement #526's evaluation metrics or counter-delta logic in
      this module.** When #526 yields an evaluation record/reference, include
      only that closed-vocabulary reference/verdict. Both lines use
      `_emit_snapshot_answer`'s single-`json.dumps(..., sort_keys=True)`
      shape (`:1231-1239`). (depends on 8)
      — DoD: a test asserts no `locator`, `selector` or payload byte can appear
      in either line, and a test proves release telemetry delegates evaluation
      semantics to #526 instead of maintaining a second metric implementation.

- [ ] 10. Reserve the new telemetry attribute names. Per
      `docs/observability/execution-traces.md`, any new `mctl.*` attribute must
      be listed there marked **proposed** and get a reservation PR against
      mctl-docs' `docs/reference/telemetry-attributes.md` before this issue
      closes. Add `mctl.context.strategy.name`, `.version`,
      `.content_hash`, `mctl.context.binding.revision`,
      `mctl.context.release.mode`. (depends on 9)
      — DoD: the attributes table in `docs/observability/execution-traces.md`
      lists all five as `proposed`, and the mctl-docs reservation PR is linked
      from this issue.

- [ ] 11. CI drift guard: a pytest test (not a new workflow —
      `.github/workflows/pr-validation.yml` already runs pytest, ruff and mypy)
      that recomputes every published version's `implementationHash` against
      the working tree and fails with the exact republish command when they
      disagree, plus a `tools/context_release.py resolve` preflight asserting
      both committed bindings resolve on this commit. (depends on 5)
      — DoD: deliberately editing `rank_candidates` without republishing fails
      CI with an actionable message.

## Slice C — operator documentation and promotion proof

- [ ] 12. Documentation and defaults: add the four new variables to
      `.env.example` next to the existing `ISSUE_INVESTIGATOR_CONTEXT_*` block
      (which already documents the pilot's modes and its safe rollback), all
      commented out and defaulting to today's behaviour; add a README section
      covering publish -> promote-to-shadow -> observe -> promote-to-production
      -> roll back, and the soak gate from task 13. (depends on 9)
      — DoD: an operator can run the whole lifecycle from the README with no
      code reading, and `.env.example` states that unset means unchanged
      behaviour.

- [ ] 13. Define the promotion soak gate in ADR 019 and the README:
      production promotion requires **3 consecutive observe-mode
      investigations**, all referring to the exact strategy/version/
      `contentHash`/`implementationHash` being promoted, with the newest
      observation no older than **7 days**, and with no `hash-mismatch`
      verdict. The evidence is produced by #526; task 9 carries correlation,
      not a duplicate evaluator. Promotion remains a human-reviewed PR even
      when the gate passes. (depends on 9 and mctlhq/mctl-agents#526)
      — DoD: missing evidence, evidence older than 7 days, fewer than 3
      consecutive runs, or any identity mismatch each fail with a distinct
      closed-vocabulary reason; README shows how to inspect the evidence and
      how to use `CONTEXT_RELEASE_ROLLOUT_MODE=off` for break-glass.

## Tests

- [ ] T1. Golden-fixture stability: `tests/fixtures/context/
      investigator-snapshot.json` and its asserted `content_hash`/`snapshot_id`
      are unchanged by task 2. This is the single most important test in the
      proposal — if it fails, every persisted snapshot's identity moved.
- [ ] T2. Optional-field semantics: sealing with `release_revision`/
      `content_hash` unset produces byte-identical canonical JSON to sealing
      before the change; setting them changes `content_hash`; `from_dict`
      round-trips both cases and still rejects an unknown key inside
      `strategy`.
- [ ] T3. Version loading: unknown `apiVersion`, unknown `kind`, `disabled`
      lifecycle, absent implementation file, and a tampered
      `implementationHash` each raise with a message naming the file.
- [ ] T4. Binding loading: `metadata.agent`/`metadata.environment` disagreeing
      with the path, a non-positive revision, a duplicated revision, a gap in
      the revision sequence, and an empty history each raise.
- [ ] T5. Promotion rules: a `production` promotion with
      `evidence.kind: none` is refused; the same promotion to `shadow` is
      accepted; production evidence older than 7 days, with fewer than 3
      consecutive observe runs, with `hash-mismatch`, or naming a different
      strategy/version/content/implementation hash is refused with the exact
      documented reason; promoting a `deprecated` version is refused while an
      existing binding on it still resolves.
- [ ] T6. Rollback rules: `rollback(to_revision=1)` appends a revision
      restoring revision 1's exact strategy/version/hash triple with
      `rollbackOf: 1`, leaves revisions 1..N intact, and never infers a target;
      rolling back to a revision whose version is now `disabled` is refused and
      names it.
- [ ] T7. Ladder: `off` (default) opens no catalog file and imports no YAML;
      `observe` runs two pipeline passes and lets the env var decide;
      `enforce` lets the binding decide; `only` rejects a set
      `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY`; an unrecognised mode answers `off`
      and warns without raising.
- [ ] T8. Break-glass: at `enforce` with an unresolvable binding,
      `CONTEXT_RELEASE_REQUIRED=true` (default) fails the assembly and
      `=false` falls back to `deterministic-fixed-order` with the documented
      reason code.
- [ ] T9. Observe isolation (the stage's whole safety claim): the
      authoritative snapshot is byte-identical with and without the shadow
      pass; `AssemblyResult.rendered` is unchanged; the work-item store client
      is called exactly once; the candidate snapshot is never returned.
- [ ] T10. Telemetry safety: neither new log line can carry a `locator`, a
      `selector` or any payload-derived string, asserted recursively over the
      emitted dict the way `tests/test_context_snapshot.py` already asserts the
      schema's field names.
- [ ] T11. Authorization boundary: the recursive field-name assertion (no
      `allow`/`deny`/`permit`/`grant`/`authorized` token) and the subprocess
      import-direction assertion from `tests/test_context_snapshot.py` are
      extended to `orchestrator/context_release.py`, proving no policy path
      imports it.
- [ ] T12. Isolation: `tests/test_worker_isolation.py` passes unchanged,
      proving `orchestrator/context_assembly.py`'s module-scope imports are
      still stdlib-only after task 7's deferred import.
- [ ] T13. Drift guard: a synthetic edit to a declared implementation file
      makes task 11's test fail with the republish command in its message.
- [ ] T14. End-to-end: `tools/context_release.py publish` then `promote` then
      `resolve` on a temporary catalog root yields the expected
      `ResolvedContextStrategy`, and `--dry-run` writes nothing.

## Rollback

Four tiers, fastest first. Each is independently sufficient.

1. **Instant, no deploy, no commit:** unset `CONTEXT_RELEASE_ROLLOUT_MODE` (or
   set it to `off`). The mode is read fresh per run — the same property
   `_context_mode`/`_resolver_mode`/`_capability_mode` already rely on so "an
   operator can roll back by unsetting the env var without a redeploy"
   (`run_issue_investigator.py:149-153`). `AssemblyConfig.from_env()` decides
   again, no catalog file is read, `context_release` is not even imported, and
   snapshots return to the exact bytes they have today.
2. **Keep the ladder, restore fail-open:** set `CONTEXT_RELEASE_REQUIRED=false`
   if an unresolvable binding is blocking runs during an incident. Assembly
   falls back to `deterministic-fixed-order` and continues.
3. **Audited catalog rollback:** `tools/context_release.py rollback --agent
   issue-investigator --environment production --to-revision N --reason ...`,
   merged as a PR. Appends a new revision restoring revision N's exact triple
   with `rollbackOf: N` — history is never rewritten, so what was live at any
   past moment stays answerable.
4. **Full revert:** revert the feature commits. Because every new file is
   additive and the default is `off`, reverting restores prior behaviour
   exactly — with one caveat that must be checked before reverting task 2:
   `ContextSnapshot.from_dict` rejects unknown keys, so a reverted reader will
   refuse a snapshot that was persisted **with** `strategy.release_revision`
   set. Order the revert accordingly — move the ladder to `off` first, let
   in-flight executions drain, and only then revert the schema change; or leave
   task 2 in place, since it is inert while the ladder is `off`.

The blast radius at every tier is bounded by the outer gate: with
`ISSUE_INVESTIGATOR_CONTEXT_MODE=off` — still the shipped default — no
assembly runs at all, so none of this code executes.
