# Tasks: issue-265-feat-context-assemble-investigator-conte

- [ ] 1. Export the single hash rule from `orchestrator/context_snapshot.py`:
      add public `hash_bytes(raw: bytes) -> str` and
      `canonical_json(payload) -> bytes` as thin aliases of the existing
      `_hash_bytes` (`:79`) and `_canonical_json` (`:83`), with a docstring
      stating these are the only hashing entry points any producer may use
      (ADR 009's "a second, disagreeing hash convention" risk).
      — DoD: both symbols importable; no behaviour change; the golden fixture
      hash assertion in `tests/test_context_snapshot.py` still passes;
      `uv run mypy .` and `uv run ruff check .` clean.

- [ ] 2. Create `orchestrator/context_assembly.py` with the data model and no
      collectors yet: `CandidateSource`, `Collector` type alias,
      `AssemblyInput`, `AssemblyConfig`, `AssemblyMetrics`, `AssemblyResult`.
      Stdlib-only; imports from `orchestrator.context_snapshot` only.
      (depends on 1) — DoD: module imports in a fresh interpreter without
      `claude_agent_sdk` in `sys.modules`; `AssemblyResult.snapshot` is a
      `ContextSnapshot` and payload text lives only on
      `AssemblyResult.rendered`.

- [ ] 3. Implement the deterministic pipeline stages in
      `context_assembly.py`: `assign_ranks`, `normalize` (UTF-8 encode +
      `hash_bytes`), `classify_freshness` (per-kind `max_age_seconds` table;
      `fresh` ≤ max/2, `aging` ≤ max, `stale` beyond; explicit `fresh` for
      content-addressed kinds; `unknown` as the unclassified fail-safe),
      `deduplicate` (by `content_hash`, lowest rank wins),
      `truncate_to_per_source_limit` (cut bytes before hashing, post-truncation
      `byte_count`, `selector["byte_range"]`), and `apply_budget` (ascending
      rank; from the first non-fitting candidate, that one and all lower ranks
      are `budget-exhausted`; sets `truncated=true`).
      (depends on 2) — DoD: every excluded candidate remains in the emitted
      `sources` list with `included=false` and a reason code from the closed
      set `{stale, duplicate-content, budget-exhausted}`; no stage mutates
      rank.

- [ ] 4. Implement the five collectors and `_COLLECTOR_ORDER`:
      `collect_inline_template`, `collect_github_issue`,
      `collect_issue_comments`, `collect_target_repo`,
      `collect_prior_proposal`, with the kinds, locators, selectors and trust
      tiers in design.md's collector table. Enforce `max_comments` (newest 20)
      and `max_candidates`, counting both drops in metrics.
      (depends on 3) — DoD: each collector returns candidates in a documented
      deterministic order; `target-repo` emits
      `byte_count=0`/`selector={"mode":"agent-directed"}`/locator
      `git+https://github.com/<repo>@<sha>`; no collector performs a network
      call other than through the existing `gh` path.

- [ ] 5. Add `comments` to the `--json` field list in `gh_issue_view`
      (`orchestrator/run_issue_investigator.py:868`) and carry them on
      `IssueData` (`:167`) as an ordered tuple of `(id, author, created_at,
      body)`; update the `selector.fields` string recorded by
      `collect_github_issue` to match the new list.
      (depends on 4) — DoD: one `gh` invocation, not two; `IssueData` stays a
      plain dataclass importable by `run_issue_poller.py` without the SDK;
      existing `tests/test_run_issue_investigator.py` stubs updated.

- [ ] 6. Implement `build_execution_correlation(mode, plan, ...)` in
      `context_assembly.py` with the declarative branch (copy off
      `resolver.ExecutionPlan`, `orchestrator/resolver.py:226-258`) and the
      legacy branch (`definition_version="legacy"` + hash of
      `agents/_manifests/issue-investigator/agent.yaml` bytes;
      `profile_version="legacy"` + hash of the canonical JSON of
      `INVESTIGATOR_MODEL`, the investigator `allowed_tools` list and
      `ISSUE_INVESTIGATOR_BUDGET_USD`; `release_revision=0`). Source
      `temporal_workflow_id` from `orchestrator.temporal.issue_ref.workflow_id_for`.
      (depends on 2) — DoD: `ExecutionCorrelation` constructs in both modes
      with no empty required field; the `resolver` import stays function-local
      so `context_assembly` remains stdlib-only at module scope.

- [ ] 7. Implement `assemble_investigator_context(...) -> AssemblyResult | None`
      — runs collectors, pipeline and `seal()` with
      `ContextStrategy("deterministic-fixed-order", "1.0.0")`,
      `RetentionPolicy("execution-record", 180)`, `step=None`,
      `evidence_refs=()`; returns `None` when mode is `off`.
      (depends on 3, 4, 6) — DoD: sealing the same inputs twice at two
      different `created_at` values yields one `snapshot_id`;
      `snapshot.validate()` passes, including the `used_sources`/`used_bytes`
      reconciliation at `context_snapshot.py:783-794`.

- [ ] 8. Add the feature gate `_context_mode()` to
      `orchestrator/run_issue_investigator.py`, structurally mirroring
      `_resolver_mode()` (`:108`): `_CONTEXT_MODES = ("off","shadow","on")`,
      `os.getenv("ISSUE_INVESTIGATOR_CONTEXT_MODE","off").strip().lower()`,
      `SystemExit` naming the allowed values, read fresh per call, plus a
      `print(f"[context] issue-investigator context_mode={mode!r}")` line.
      (depends on 7) — DoD: unset env behaves as `off`; an invalid value exits
      with a message naming all three modes.

- [ ] 9. Wire the call site into `investigate()` between staging (`:1534`) and
      prompt construction (`:1537`), resolving `_target_repository_sha`
      (`:117`) unconditionally when mode is not `off`. Wrap assembly in
      try/except: in `shadow` log `warn: context assembly failed: ...` and
      continue with `context=None`; in `on` re-raise.
      (depends on 8) — DoD: an assembly exception in `shadow` produces a normal
      proposal; the same exception in `on` fails the run.

- [ ] 10. Extend `_build_prompt` (`:1127`) with a keyword-only
      `context: AssemblyResult | None = None`. Append an `## Assembled context`
      section only when `context.mode == "on"`, rendering included
      `github-issue-comment` and `proposal-dir` sources inside
      `<context_source id=... kind=... trust=...>` blocks, each payload passed
      through `_neutralize_prompt_tags` (`:1098`) and framed with the same
      untrusted-data warning the `<issue_body>` block already carries.
      (depends on 9) — DoD: with `context=None` the returned string is
      byte-identical to the current implementation's; the existing
      `<issue_title>`/`<issue_body>` blocks are unchanged in `on` mode.

- [ ] 11. Extend `write_status_yaml` (`:979`) with an optional `snapshot`
      parameter writing the additive `context` block
      (`snapshot_id`, `content_hash`, `strategy`, `strategy_version`), and pass
      the sealed snapshot through from `investigate()` (`:1643`).
      (depends on 7) — DoD: `_status_disagreements` (`:539`) reports no
      disagreement for a status file carrying the new block; the atomic
      mkstemp/fsync/fchmod/replace write path is untouched; the file stays far
      under `MAX_STATUS_BYTES` (`:265`).

- [ ] 12. Implement `AssemblyMetrics.to_log_dict()` and emit exactly one
      `print(f"[context] context_assembly={json.dumps(..., sort_keys=True)}")`
      line, mirroring `ExecutionPlan.log()` (`orchestrator/resolver.py:290`).
      Fields per requirements.md's metrics criterion, with
      `snapshot.to_log_dict()` (`context_snapshot.py:807`) merged under
      `snapshot`.
      (depends on 7) — DoD: the emitted JSON contains no `locator`, no
      `selector` and no payload substring; latency is measured with
      `time.monotonic()` and excluded from the snapshot hash.

- [ ] 13. Documentation: add a "Context assembly" section to
      `docs/adr/009-context-snapshot-contract.md`'s follow-up table marking row
      (a) as delivered by #265 (leaving (b)–(e) open); add
      `ISSUE_INVESTIGATOR_CONTEXT_MODE` and the three budget/limit env vars to
      `.env.example`; record the new runtime context inputs under
      issue-investigator in `docs/agent-inventory.yaml`.
      (depends on 12) — DoD: `uv run pytest tests/test_agent_inventory.py` and
      `tests/test_manifest.py` pass; `orchestrator/validate_manifest.py` still
      resolves `_build_prompt` and every declared env var.

## Tests

All in `tests/test_context_assembly.py` unless stated otherwise.

- [ ] T1. Determinism: assembling a fixed candidate set twice with an injected
      frozen clock produces identical `snapshot_id` and `content_hash`; and
      sealing the same inputs at two different `created_at` values still
      produces one `snapshot_id` (the `created_at`-excluded-from-hash rule).
- [ ] T2. Freshness: table-driven over the boundaries — age = max/2 → `fresh`,
      age = max → `aging`, age = max + 1 → `stale`; a `stale` candidate stays
      in `sources` with `included=false, reason_code="stale"`; a
      content-addressed kind with `max_age_seconds=None` is `fresh`; an
      unclassified kind falls back to `unknown`.
- [ ] T3. Deduplication: two candidates with identical bytes from different
      locators — the lower rank is included, the other carries
      `reason_code="duplicate-content"`, and `budget.used_sources` counts one.
- [ ] T4. Per-source truncation: an oversized candidate is cut to
      `max_bytes_per_source`; `content_hash` equals
      `context_snapshot.hash_bytes` of the *truncated* bytes;
      `byte_count` is post-truncation; `selector["byte_range"]` is recorded;
      `budget.truncated is True`.
- [ ] T5. Budget: candidates exceeding `max_sources`/`max_bytes` are excluded
      from the first miss onward with `reason_code="budget-exhausted"`,
      `truncated=true`, and `snapshot.validate()` passes its
      `used_sources`/`used_bytes` reconciliation.
- [ ] T6. Source coverage: a representative run yields at least three distinct
      `kind` values, every one drawn from `context_snapshot.SOURCE_KINDS`, and
      every `trust.tier` from `TRUST_TIERS`; the `github-issue` and
      `github-issue-comment` sources are `untrusted`, `target-repo` is
      `authoritative` with `byte_count=0` and `selector={"mode":"agent-directed"}`.
- [ ] T7. Telemetry safety: run a collector whose payload contains the marker
      `CONTEXT-LEAK-CANARY`, capture stdout/stderr across assembly and metrics
      emission, and assert the marker, the locator and the selector appear
      nowhere in the captured output.
- [ ] T8. Hash-rule unity: the assembler's `content_hash` for a candidate
      equals `context_snapshot.hash_bytes(bytes)` over the same bytes — no
      second convention.
- [ ] T9. Feature gate, in `tests/test_run_issue_investigator.py`:
      `_context_mode()` defaults to `off` when unset; raises `SystemExit`
      naming all three modes on a bad value; `_build_prompt(..., context=None)`
      is byte-identical to `_build_prompt(...)` as it exists on `main`
      (assert against a checked-in golden prompt string).
- [ ] T10. Shadow-mode equivalence, in `tests/test_run_issue_investigator.py`:
      with `ISSUE_INVESTIGATOR_CONTEXT_MODE=shadow`, the prompt handed to
      `_run_agent` is byte-identical to the `off` prompt, and a snapshot is
      still sealed and logged.
- [ ] T11. Failure policy: a collector raising in `shadow` yields a normal
      proposal with `context=None`; the same collector raising in `on`
      propagates and fails the run.
- [ ] T12. Status correlation: `write_status_yaml` with a snapshot writes the
      `context` block; `_status_disagreements` returns `[]` for that file;
      re-reading it through `_read_published_status` (`:494`) succeeds.
- [ ] T13. Import isolation: a fresh subprocess importing
      `orchestrator.context_assembly` loads neither `claude_agent_sdk` nor
      `orchestrator.run_implementer`, in the style of
      `tests/test_worker_isolation.py`; and `tests/test_context_snapshot.py`'s
      existing isolation test still passes after task 1.
- [ ] T14. Authorization boundary: assert the `context_assembly` source text
      contains no allow/deny/permit/grant vocabulary and that nothing in the
      module imports a policy or permission symbol (mirroring ADR 009 sec. 5's
      field-name and import-direction checks).
- [ ] T15. Full suite green: `uv run pytest`, `uv run ruff check .`,
      `uv run mypy .`.

## Rollback

Three levels, cheapest first.

1. **Operational, no deploy.** Unset `ISSUE_INVESTIGATOR_CONTEXT_MODE` or set
   it to `off` in the investigator's CWFT env. `_context_mode()` is read fresh
   per call (never cached at import, exactly as `_resolver_mode()` is), so the
   next run reverts to the current code path: no collector runs, no snapshot is
   sealed, no `context` block is written, and `_build_prompt` returns the
   byte-identical string T9 pins. This is the documented default and is the
   whole point of shipping `off` as the default.
2. **Partial.** If only the prompt change is at fault, move from `on` to
   `shadow`: prompts revert to today's while metrics and correlation keep
   flowing, so the baseline the issue asks for is not lost while the rendering
   is fixed.
3. **Code revert.** The change is additive and confined to
   `orchestrator/context_assembly.py` (new), `orchestrator/context_snapshot.py`
   (two public aliases), `orchestrator/run_issue_investigator.py` (gate, call
   site, two optional parameters, one `gh --json` field), plus tests and docs.
   Reverting the commit removes the module and restores the four touched
   functions; nothing else depends on them. No migration to undo: the
   `.status.yaml` `context` block is optional and every reader ignores unknown
   keys, so already-published proposals carrying it stay valid and continue to
   be processed by the implementer, the approve operation and the reconcile
   sweep unchanged.
