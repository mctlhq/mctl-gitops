# Tasks: issue-528-feat-context-platform-472-slice-c-produc

Preflight (before task 1): confirm mctlhq/mctl-agents#526 and Slice B (#527)
are merged and on the running image, then run
`uv run pytest tests/test_context_release.py -k "not_drifted or committed_shadow_binding"`.
If either guard fails, republish the affected version documents
(`python tools/context_release.py publish --strategy <name> --version <version>`,
no `--lifecycle`) and append one shadow binding revision **before** starting —
the issue's hard dependency about hashes #526 invalidated.

- [ ] 1. Add `EvalMetrics.from_dict`, `OutcomeLink.from_dict` and
      `EvalRecord.from_dict` to `orchestrator/context_eval.py`, exact inverses
      of the existing `to_dict()`/`to_log_dict()`, reusing
      `EvidenceIdentity.from_dict` and `work_context.snapshots.StoreRef.from_dict`.
      `EvalRecord.from_dict` raises `ValueError` for a payload whose
      `record_kind != RECORD_KIND` or whose `verdict` is outside `VERDICTS`.
      No new import; the module stays stdlib-only, clock-free and env-free.
      — DoD: `EvalRecord.from_dict(r.to_log_dict()) == r` holds for a record
      with and without `store_ref`, `metrics` and `outcome`; the existing
      import-direction test in `tests/test_context_eval.py` still passes.

- [ ] 2. Extend `orchestrator/context_release.py`'s catalog types (depends on 1):
      add `PROMOTION_ENVIRONMENTS = {"shadow", "production"}` and
      `EVIDENCE_FREE_ENVIRONMENTS = {"shadow"}`; give
      `ContextStrategyBindingRevision` the optional `evidence_observed_at` and
      `evidence_observations` fields, omitted from `to_dict()` when `None`;
      teach `load_binding()` that a `context-eval` revision requires non-empty
      `ref`, `evaluatorVersion`, `observedAt` and a positive integer
      `observations`, while a `none` revision must carry neither `observedAt`
      nor `observations` — both failing closed with `unknown`, naming the field.
      — DoD: the committed shadow binding still loads and `to_dict()` round-trips
      revisions 1-5 byte-identically; a `context-eval` revision missing any of
      the four fields raises `unknown` naming it.

- [ ] 3. Implement the production evidence gate in
      `orchestrator/context_release.py` (depends on 2): a pure
      `assess_production_evidence(*, version, records, evidence_evaluator_version, now)`
      that imports `orchestrator.context_eval` **inside the function body**,
      builds an `EvidenceIdentity` from the loaded `ContextStrategyVersion`,
      and calls `assess_evidence(..., policy=FreshnessPolicy(
      ADR019_V1_FRESHNESS_WINDOW_SECONDS, ADR019_V1_MIN_CONSECUTIVE_OBSERVATIONS))`.
      Fixed precedence: non-`context-eval` kind -> `evidence-missing`; no
      records -> `evidence-missing`; a matching-identity record with
      `verdict: "hash-mismatch"` -> `hash-mismatch`; evaluator-version
      disagreement -> `evidence-mismatch`; then `missing`/`mismatched`/`stale`/
      `insufficient-observations` -> `evidence-missing`/`evidence-mismatch`/
      `evidence-stale`/`evidence-insufficient`; `fresh` -> accepted. Every
      message repeats #526's own `reason_code`, the counted observations and
      the window in seconds. No env var, no clock read, no network.
      — DoD: each of the six refusal paths raises `ContextReleaseError` with the
      documented distinct `.code`; `grep -n "getenv\|environ" orchestrator/context_release.py`
      still returns nothing.

- [ ] 4. Rewire `context_release.promote()` (depends on 3): add
      `evidence_records` and `now` keyword arguments; refuse an environment
      outside `PROMOTION_ENVIRONMENTS` as `unknown` naming both supported ones;
      reorder to argument validation -> environment allow-list ->
      `load_version()` -> `published` lifecycle check
      (`version-not-promotable`) -> evidence gate for environments not in
      `EVIDENCE_FREE_ENVIRONMENTS` -> append one revision recording
      `kind: context-eval`, `ref`, `evaluatorVersion`, `observedAt` and
      `observations`. `shadow` behaviour is unchanged. Update the module and
      function docstrings: the Slice A "always refused until #526" paragraphs
      are now false.
      — DoD: a `production` promotion with fresh evidence appends exactly one
      revision and mutates no prior one; the same call with
      `evidence_kind="none"` still raises `evidence-missing`; `promote()` still
      writes nothing.

- [ ] 5. Add the evaluation reference to `CONTEXT_STRATEGY_COMPARE` in
      `orchestrator/context_assembly._emit_strategy_compare` (depends on 1):
      four new keys — `record_kind`, `evaluator_name`, `evaluator_version`,
      `metrics_contract_version` — read through a deferred
      `from orchestrator import context_eval` inside the function, all four
      `null` if that import fails. No counter delta, no ratio, no "which
      strategy won". Update the function docstring, which currently says this is
      "added in Slice C".
      — DoD: an `observe` run with a resolved, differing bound strategy emits the
      four keys; the line still carries no `locator`, `selector` or payload byte;
      a simulated `ImportError` yields four nulls and does not fail the run.

- [ ] 6. Extend `tools/context_release.py promote` (depends on 4): `--evidence-file
      PATH` (JSONL of `context_eval` records, a bare JSON array also accepted),
      parsed with `EvalRecord.from_dict`; `--evidence-ref` required whenever
      `--evidence-kind context-eval`; `now=datetime.now(UTC)` passed into
      `promote()`; an unparsable file exits non-zero with `unknown:` and the
      offending line number. `--dry-run` prints the gate outcome — status,
      reason code, observations counted, newest observation age, window and
      minimum in force — and writes nothing.
      — DoD: `promote --environment production --evidence-file <fresh>.jsonl --dry-run`
      prints the passing gate and writes no file; the same with stale evidence
      exits non-zero naming `evidence-stale`; `--help` exits 0.

- [ ] 7. Write the README `### Context strategy release` section (depends on 6),
      placed directly after "### Context evaluation": the full ladder
      publish -> promote-to-shadow -> soak -> build the evidence file -> inspect
      with `--dry-run` -> promotion PR -> `rollback --to-revision N` ->
      break-glass `CONTEXT_RELEASE_ROLLOUT_MODE=off`, with runnable commands;
      the soak gate stated in operator terms (3 consecutive store-backed
      observations of the exact strategy/version/`contentHash`/
      `implementationHash`, newest at most 7 days old, no `hash-mismatch`); an
      explicit note that the `observe` shadow pass is never itself a counted
      observation and how to produce observations that are; and the
      refusal-reason table.
      — DoD: an operator can run the whole lifecycle from the README with no code
      reading; every command in the section is copy-pasteable and correct for the
      merged CLI.

- [ ] 8. Audit `.env.example`'s `ISSUE_INVESTIGATOR_CONTEXT_*` /
      `CONTEXT_RELEASE_*` block (depends on 7): every lifecycle variable
      (`ISSUE_INVESTIGATOR_CONTEXT_MODE`, `..._STRATEGY`, `..._EVAL`,
      `CONTEXT_RELEASE_ROLLOUT_MODE`, `CONTEXT_RELEASE_REQUIRED`) commented out,
      each stating that unset means unchanged behaviour, each cross-referencing
      the new README section; keep and strengthen the existing "there is
      deliberately no variable for the freshness window or minimum observation
      count" note, naming #528 as the consumer of those constants.
      — DoD: no uncommented new variable; `.env.example` states that unset means
      unchanged behaviour for every one of them.

- [ ] 9. Amend `docs/adr/019-context-strategy-release-contract.md` (depends on 3,
      5, 7): delete the sec. 5 note deferring the compare line's evaluation
      reference and name the four keys that shipped; record the refusal
      precedence table and the `assess_evidence` status -> verdict mapping as the
      soak gate's normative definition; record the production `evidence` block's
      `observedAt`/`observations` fields; update the Slice C sentences in the
      header and "Platform impact" that say production promotion is refused
      outright; link the README runbook. Reopen nothing listed under "What this
      ADR may not be reopened to change".
      — DoD: the ADR describes the shipped behaviour with no sentence still
      claiming production promotion is unconditionally refused; the 7-day/3-run
      constants remain ADR-only, with no env var.

- [ ] 10. Republish the catalog and pin it (depends on 5 — must be the LAST code
      task): `python tools/context_release.py publish --strategy
      deterministic-fixed-order --version 1.0.0` and the same for
      `trust-freshness-ranked`, both without `--lifecycle`, then append one
      shadow binding revision with `promote --agent issue-investigator
      --environment shadow --reason "republish pins after issue-528 Slice C"`.
      Ship no `production` binding.
      — DoD: `tests/test_context_release.py::test_published_catalog_hashes_are_not_drifted`,
      `::test_committed_shadow_binding_resolves` and
      `::test_committed_catalog_has_no_production_binding` all pass on the final
      commit.

- [ ] 11. Full quality gate (depends on 10): `uv run ruff check`,
      `uv run mypy`, `uv run pytest`.
      — DoD: all three clean; no new `noqa` without an inline reason.

## Tests

- [ ] T1. `EvalRecord.from_dict` round-trips `to_log_dict()` exactly, including
      a record with `store_ref=None`, `metrics=None` and `outcome=None`, and
      rejects a payload with a foreign `record_kind` or an unknown `verdict`.
- [ ] T2 (T5, production half — `evidence.kind: none`). A `production` promotion
      with `evidence_kind="none"` is refused as `evidence-missing`; the *same*
      promotion to `shadow` is accepted and appends one revision.
- [ ] T3 (T5 — stale). Production evidence whose newest store-backed observation
      is 7 days + 1 second old is refused as `evidence-stale`; the same evidence
      one second inside the window passes.
- [ ] T4 (T5 — insufficient). Two consecutive observations are refused as
      `evidence-insufficient`; three are accepted. Two attempts of one store
      execution count once (the `_observation_key` rule), so three *attempts* of
      two executions are still `evidence-insufficient`.
- [ ] T5 (T5 — hash-mismatch). A record carrying `verdict: "hash-mismatch"` for
      the promoted identity is refused as `hash-mismatch`, not as
      `evidence-insufficient` — pinning the precedence, since `assess_evidence`
      would otherwise drop it silently.
- [ ] T6 (T5 — identity). Evidence naming a different strategy, a different
      version, a different `contentHash` or a different `implementationHash` is
      refused as `evidence-mismatch` in each of the four cases; a mismatched
      `evidence.evaluatorVersion` is also `evidence-mismatch`.
- [ ] T7 (T5 — lifecycle). Promoting a `deprecated` version to `production` is
      refused as `version-not-promotable` *while* `resolve()` on an existing
      binding already pointing at that version still returns `ok`; a `disabled`
      version is refused as `version-disabled`.
- [ ] T8. A passing production promotion records `kind: context-eval`, a
      non-empty `ref`, the `evaluatorVersion`, the newest `observedAt` and the
      counted `observations`; every prior revision is byte-identical; revisions
      stay 1..N with no gap.
- [ ] T9. An environment outside `{shadow, production}` (e.g. `staging`) is
      refused as `unknown` naming both. Replaces
      `test_non_shadow_promotion_is_refused_even_when_not_named_production`'s
      `evidence-missing` expectation; update, do not duplicate.
- [ ] T10. Policy constants are ADR-only: `context_release` reads no environment
      variable (source scan), and the gate's window/minimum are exactly
      `context_eval.ADR019_V1_FRESHNESS_WINDOW_SECONDS` /
      `ADR019_V1_MIN_CONSECUTIVE_OBSERVATIONS`.
- [ ] T11. `orchestrator/context_release.py` imports `orchestrator.context_eval`
      only inside a function body — a source scan asserting no module-scope
      import, mirroring the existing safety-invariant/import-direction tests in
      `tests/test_context_snapshot.py` and `tests/test_context_eval.py`.
- [ ] T12. `CONTEXT_STRATEGY_COMPARE` carries the four evaluation-reference keys
      and still carries no counter delta, ratio, `locator`, `selector` or
      payload-derived byte; with `context_eval` unimportable the four keys are
      `null` and the run still succeeds.
- [ ] T13. CLI end to end on a temp catalog: `promote --environment production
      --evidence-file` with fresh evidence writes the revision; `--dry-run`
      writes nothing and prints the gate outcome; stale evidence exits non-zero
      naming `evidence-stale`; a malformed evidence line exits non-zero with
      `unknown:` and the line number; `--evidence-kind context-eval` without
      `--evidence-ref` is rejected.
- [ ] T14. Guards after task 10: published catalog hashes are not drifted, the
      committed shadow binding resolves, and no production binding is shipped.

## Rollback

Nothing in this slice changes runtime behaviour while
`CONTEXT_RELEASE_ROLLOUT_MODE` is unset or `off`, which is the default and what
production runs today — so the blast radius of a revert is the CLI, the catalog
and two log-line keys.

1. **Break-glass, no deploy.** Set `CONTEXT_RELEASE_ROLLOUT_MODE=off` on the
   investigator. No binding is loaded, no catalog file is opened, and
   `AssemblyConfig.from_env()` decides exactly as it did before Slice B. This
   neutralises any bad promotion instantly and is the first move in an incident.
2. **Undo one promotion, keep the lifecycle.**
   `python tools/context_release.py rollback --agent issue-investigator
   --environment production --to-revision <N> --promoted-by <you> --reason "..."`
   appends a revision restoring revision `N`'s exact
   `(strategy, version, contentHash, implementationHash)` tuple. Append-only:
   nothing is deleted, and the bad revision stays in git for the post-mortem.
3. **Undo the slice.** Revert the merge commit. `promote()` returns to refusing
   every non-`shadow` environment as `evidence-missing`, the compare line loses
   four keys, and the catalog reverts to its pre-slice hashes — which is
   self-consistent, because task 10's republish is part of the same commit
   range. Re-run `uv run pytest tests/test_context_release.py` after the revert
   to confirm the hash guard is green on the reverted tree.
4. **If the revert lands but the hash guard fails** (someone edited
   `context_assembly.py` in between), run
   `python tools/context_release.py publish --strategy <name> --version 1.0.0`
   for both strategies with no `--lifecycle` and append one shadow revision —
   the documented repair, and exactly what revisions 2-5 of the committed
   binding already are.
