# Design: issue-528-feat-context-platform-472-slice-c-produc

> **Correction 2026-09-28 (before approval).** ADR 019 requires production
> evidence from **>= 3 consecutive observe-mode investigations**. As first
> written, this proposal collected it by making the candidate authoritative:
> binding it in `shadow` at `enforce`, which on the production investigator
> resolves `AGENT_ENVIRONMENT`/`production` and never reaches the shadow
> binding (`context_assembly.py:1176`), or setting
> `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY=<candidate>`. Either way it is production
> exposure before the gate. Both paths are removed. Production soak evidence
> now comes only from Slice B's **non-authoritative observe candidate**,
> evaluated in the same production investigation as
> `evidence_kind: observe-candidate`. It carries its own `execution_ref`,
> never a borrowed `store_ref`, because the candidate is never persisted. The
> candidate does not serve the investigation that evaluates it.

## Current state

**The release catalog and its loader (Slice A).**
`orchestrator/context_release.py` (821 lines) parses
`config/context-strategies/versions/<name>/<version>.yaml` and
`config/context-strategies/bindings/<environment>/<agent>.yaml`, recomputing
`implementationHash` over the declared implementation files
(`compute_implementation_hash`, the length-prefixed encoding
`tools/publish_agent_release.py` already uses) and `contentHash` over the
document's own canonical JSON (`compute_content_hash`, via
`context_snapshot.canonical_json`/`hash_bytes`). Every failure is a
`ContextReleaseError` whose `.code` is drawn from the closed `VERDICTS`
frozenset (`context_release.py:89-111`): `ok`, `evidence-missing`,
`evidence-mismatch`, `evidence-stale`, `evidence-insufficient`,
`version-not-promotable`, `version-disabled`, `hash-mismatch`, `unknown`. All
four `evidence-*` codes exist today but only `evidence-missing` is ever
raised.

`promote()` (`context_release.py:595-676`) is a pure builder that appends one
revision and returns a new `ContextStrategyBinding`; it never writes. Its
Slice A body refuses `environment != "shadow"` unconditionally with
`evidence-missing` (`:631-638`) and refuses any `evidence_kind != "none"`
with the same code (`:644-649`), before `load_version()` is even called.
`rollback()` (`:679-731`) restores an exact prior revision's
`(strategy, version, contentHash, implementationHash)` tuple with
`rollbackOf` recorded. `ContextStrategyBindingRevision`
(`:143-180`) carries `evidence_kind`/`evidence_ref`/
`evidence_evaluator_version` and emits them under
`evidence: {kind, ref, evaluatorVersion}`.

The committed catalog holds two published versions
(`deterministic-fixed-order/1.0.0.yaml`, `trust-freshness-ranked/1.0.0.yaml`)
and one shadow binding with five revisions — revisions 2-5 are pure
"republish pins after ..." entries, which is the established mechanism when a
hashed implementation file changes.
`tests/test_context_release.py::test_published_catalog_hashes_are_not_drifted`
and `::test_committed_shadow_binding_resolves` are the CI guard;
`::test_committed_catalog_has_no_production_binding` asserts no production
binding is shipped.

**The rollout ladder (Slice B).** `orchestrator/context_rollout.py` gives
`mode()`/`at_least()`/`binding_decides()`/`blocks_on_unknown()` over
`CONTEXT_RELEASE_ROLLOUT_MODE` (`off`/`observe`/`enforce`/`only`, unrecognised
answers `off` and warns) and `CONTEXT_RELEASE_REQUIRED`.
`context_assembly.assemble()` (`context_assembly.py:1334-1430`) resolves the
binding, optionally re-collects and re-runs `run_pipeline` under the bound
strategy as a non-authoritative `observe` pass whose snapshot is sealed into a
local and discarded, then emits `CONTEXT_STRATEGY_RELEASE` always and
`CONTEXT_STRATEGY_COMPARE` when an observe candidate snapshot exists
(`_emit_strategy_compare`, `:1285-1309`). That compare line deliberately
carries only the two strategy identities, the binding revision and the two
`snapshot_id`s; its docstring names the missing half as "that evaluation
semantic belongs to mctlhq/mctl-agents#526, added in Slice C". ADR 019's sec. 5
note says the same.

**The evaluator (#526).** `orchestrator/context_eval.py` is stdlib-only, reads
no clock, no env var, no network. It defines `EvalRecord` (with `to_log_dict()`
and `to_dict = to_log_dict`), `EvidenceIdentity` (which carries
`strategy_content_hash`/`strategy_implementation_hash` — supplied by the
caller from #472's catalog, never read by that module), `FreshnessPolicy`,
ADR 019's constants `ADR019_V1_FRESHNESS_WINDOW_SECONDS = 604_800` and
`ADR019_V1_MIN_CONSECUTIVE_OBSERVATIONS = 3`, and
`assess_evidence(records, *, expected, now, policy) -> EvidenceAssessment`
(`context_eval.py:791-895`) with a fixed precedence: `missing` (empty, or
newest record's `evidence_kind == "none"`), `mismatched`
(declared-identity, `catalog-identity-unavailable`, `catalog-identity-mismatch`),
`stale` (`observation-older-than-window`, `observed-at-unparseable`),
`insufficient-observations`, else `fresh`. Observations are counted per
`(work_item_id, execution_id)` via `_observation_key`; a record without a
`store_ref`, or with `verdict != "evaluated"`, is never an observation.
`EvidenceAssessment` is explicitly "a status only — deciding that `fresh`
permits a production promotion is #528's".

`EvidenceIdentity.from_dict`, `CaseLabels.from_dict` and
`work_context.snapshots.StoreRef.from_dict` exist; `EvalRecord`,
`EvalMetrics` and `OutcomeLink` have **no** `from_dict` — there is currently
no way to read a printed `context_eval=` record back into a typed object.

**Where records come from.** `run_issue_investigator._emit_context_eval`
(`:2046-2072`) prints one `[context] context_eval={...}` line per run when
`ISSUE_INVESTIGATOR_CONTEXT_EVAL=on`, with `evidence_kind: "live"`, the
authoritative snapshot's `store_ref`, and the catalog identity loaded through a
deferred `context_release.load_version` import (`_load_catalog_identity`,
`:2024-2043`). `orchestrator/run_context_eval.py` replays an already-stored
snapshot read-only out of mctl-api and prints the same record shape with
`evidence_kind: "stored-replay"` and `--json` for the bare payload.

**Docs.** `.env.example:65-110` documents the assembly pilot, the evaluation
switch and the two `CONTEXT_RELEASE_*` variables, all commented out, and
explicitly states there is no variable for the window or the observation
count. `README.md`'s "### Context evaluation" section (`:635-713`) ends with
"**What #472 requires**", pointing at `assess_evidence` and saying the
promotion decision is #528's. There is **no** README section for the release
lifecycle itself — nothing documents publish/promote/rollback for an operator.

## Proposed solution

Five code edits and three documentation edits, in dependency order.

### 1. `orchestrator/context_eval.py` — make a printed record readable again

Add `EvalMetrics.from_dict`, `OutcomeLink.from_dict` and `EvalRecord.from_dict`
(reusing the existing `EvidenceIdentity.from_dict` and
`StoreRef.from_dict`), each an exact inverse of the corresponding
`to_dict()`/`to_log_dict()`. `from_dict` rejects a payload whose
`record_kind != RECORD_KIND` and whose `verdict` is outside `VERDICTS`, raising
`ValueError` — the evidence file is operator input, so it is validated, not
trusted. The module stays stdlib-only, clock-free and env-free; no new import.

This is the smallest change that lets Slice C consume #526's evidence without
either re-deriving the record shape in `context_release.py` (two copies of one
schema) or making `context_release.py` talk to mctl-api.

### 1b. `orchestrator/context_eval.py` — the `execution-observed` provenance mode

- `EVIDENCE_KINDS` gains `"observe-candidate"`.
- A new frozen `ExecutionRef(work_item_id, execution_id)` with
  `to_dict`/`from_dict`, and `EvalRecord.execution_ref: ExecutionRef | None =
  None`, emitted by `to_log_dict()` only when set, so every existing record keeps
  its shape. `evaluate()` accepts `execution_ref=` and refuses it unless
  `evidence_kind == "observe-candidate"` and `store_ref is None`. The inverse
  holds too: an `observe-candidate` evaluation refuses a `store_ref`.
- Verification for an `observe-candidate` record is the document identity only;
  `IdentityCheck.store_ok` stays `None` (not applicable), never `True`.
- `_observation_key` returns `(work_item_id, execution_id)` from `store_ref` for
  a stored record, or from `execution_ref` for an `observe-candidate` record,
  else `None`. Retries of one investigation stay one observation, and the
  freshness anchor rule (newest counted observation) applies unchanged.
- ADR 015 sec. 1 names two provenance modes: `store-backed` (`store_ref`,
  store match) and `execution-observed` (`execution_ref`, document identity
  only, `observe-candidate` only). Sec. 7 step 5 counts both by execution.

### 1c. `orchestrator/context_assembly.py` + live emitter — evaluate the candidate

- `AssemblyResult` gains `observe_candidate: ContextSnapshot | None = None`,
  set only when the `observe` shadow pass sealed a candidate. It is never
  rendered, returned as `snapshot`, or persisted: the store call still takes
  `result.snapshot` only (Slice B's T9 stays exactly as it is).
- `run_issue_investigator._emit_context_eval` prints, after the authoritative
  record, one more record for `result.observe_candidate` with
  `evidence_kind="observe-candidate"`, the candidate strategy's catalog identity
  (`_load_catalog_identity(candidate.strategy.name, candidate.strategy.version)`)
  and `execution_ref` from `candidate.work_context` (only for a `we_` execution).
  It is best-effort, like the authoritative record: a failure warns and never
  fails the investigation.

### 2. `orchestrator/context_release.py` — the production gate

- New constants next to the existing vocabularies:

  ```python
  PROMOTION_ENVIRONMENTS = frozenset({"shadow", "production"})
  EVIDENCE_FREE_ENVIRONMENTS = frozenset({"shadow"})
  ```

  An environment outside `PROMOTION_ENVIRONMENTS` is refused as `unknown`
  (this module cannot classify it), replacing Slice A's blanket
  `evidence-missing`.

- `ContextStrategyBindingRevision` gains `evidence_observed_at: str | None`
  and `evidence_observations: int | None`, both omitted from `to_dict()` when
  `None` — the same omitted-when-unset discipline ADR 009 amendment 1's
  `conflicts` and this dataclass's own `rollbackOf` already use, so revisions
  1-5 of the committed shadow binding stay byte-identical.

- `load_binding()` gains two evidence-shape checks: a `context-eval` revision
  must carry non-empty `ref`, `evaluatorVersion`, `observedAt` and a positive
  integer `observations`; a `none` revision must carry neither `observedAt` nor
  `observations`. Both fail closed with `unknown`, naming the field, in the
  existing `_require_str_field` style.

- A new pure helper:

  ```python
  def assess_production_evidence(
      *, version: ContextStrategyVersion, records: Sequence[Any],
      evidence_evaluator_version: str | None, now: datetime,
  ) -> ProductionEvidenceVerdict   # (code, reason_code, observations, newest_age_seconds, observed_at)
  ```

  Before anything else it keeps only `evidence_kind == "observe-candidate"`
  records (`PRODUCTION_EVIDENCE_KINDS`). A `live` record of a run where the
  candidate was authoritative is dropped, so "we already rolled it out" can
  never pass as soak evidence. An empty remainder is `evidence-missing`.

  It imports `orchestrator.context_eval` **inside the function body** — the
  same deferred-import discipline `run_issue_investigator._load_catalog_identity`
  and `run_context_eval._load_catalog_identity` already use in the opposite
  direction, and the reason `context_eval`'s own docstring gives for never
  importing `context_release` at module scope. It builds
  `EvidenceIdentity(strategy_name=version.name, strategy_version=version.version,
  ranker_name=version.ranker_name, ranker_version=version.ranker_version,
  strategy_content_hash=version.content_hash,
  strategy_implementation_hash=version.implementation_hash, ...)` and calls
  `assess_evidence(records, expected=..., now=now,
  policy=FreshnessPolicy(ADR019_V1_FRESHNESS_WINDOW_SECONDS,
  ADR019_V1_MIN_CONSECUTIVE_OBSERVATIONS))`.

  Fixed refusal precedence, so a reason is never order-dependent:

  | # | Condition | `ContextReleaseError.code` |
  |---|---|---|
  | 1 | `evidence_kind != "context-eval"` (including `none`) | `evidence-missing` |
  | 2 | no records supplied | `evidence-missing` |
  | 3 | any record whose declared strategy+version match the promotion carries `verdict: "hash-mismatch"` | `hash-mismatch` |
  | 4 | supplied `evidence.evaluatorVersion` differs from the records' `evaluator_version` | `evidence-mismatch` |
  | 5 | `assess_evidence -> missing` | `evidence-missing` |
  | 6 | `assess_evidence -> mismatched` | `evidence-mismatch` |
  | 7 | `assess_evidence -> stale` | `evidence-stale` |
  | 8 | `assess_evidence -> insufficient-observations` | `evidence-insufficient` |
  | 9 | `assess_evidence -> fresh` | accepted |

  Check 3 runs before the assessment on purpose: `assess_evidence` filters
  `verdict != "evaluated"` records out of `usable` entirely, so without it a
  hash-mismatched soak would surface as `evidence-insufficient` and hide the
  real fault, which the task 13 DoD requires to be distinct. Every refusal
  message carries #526's own `reason_code`, the observation count and the
  window in seconds, so the operator sees both layers' answers.

- `promote()` is reordered and extended. New keyword arguments:
  `evidence_records: Sequence[Any] | None = None` and `now: datetime | None =
  None`. New order: argument validation -> environment allow-list ->
  `load_version()` (which already raises `version-disabled` and `hash-mismatch`)
  -> lifecycle `published` check (`version-not-promotable`) -> for an
  environment not in `EVIDENCE_FREE_ENVIRONMENTS`, the gate above -> append.
  `load_version()` must move ahead of the evidence gate because the gate's
  `expected` identity *is* the version document's `contentHash`/
  `implementationHash`. `shadow` keeps exactly today's behaviour: `evidence_kind
  = "none"`, a recorded reason, no records, no clock read. A `shadow` promotion
  that supplies `context-eval` evidence is accepted and records it (evidence is
  never *forbidden*, only *required* for production).

  `promote()` still never writes and still never reads a clock: `now` is an
  argument, `promoted_at` stays a caller-supplied string.

### 3. `orchestrator/context_assembly.py` — the compare line's evaluation reference

`_emit_strategy_compare` gains four keys — `record_kind`, `evaluator_name`,
`evaluator_version`, `metrics_contract_version` — read through a deferred
`from orchestrator import context_eval` inside the function, wrapped so an
ImportError yields four `null`s rather than failing a run that already
completed. Nothing else changes: no counter delta, no ratio, no "which
strategy won". This is task 9's Slice C part and exactly the correlation task
13 asks for ("task 9 carries correlation, not a duplicate evaluator"); an
operator joins a compare line to its `context_eval=` records by `snapshot_id`
and now knows which evaluator version and metric contract those records were
produced under.

Because `orchestrator/context_assembly.py` is a hashed implementation file for
both published strategies
(`IMPLEMENTATION_FILES_BY_STRATEGY`, `context_release.py:72-74`), this edit
invalidates both `implementationHash`es. The slice therefore ends with a
republish of both version documents and one appended shadow binding revision
pinning the new hashes — the identical mechanism revisions 2-5 already record.

### 4. `tools/context_release.py` — the operator surface

`promote` gains `--evidence-file PATH` (JSONL, one `context_eval` record per
line; a bare JSON array is also accepted) and keeps `--evidence-kind`,
`--evidence-ref`, `--evidence-evaluator-version`. The CLI reads the file,
parses each line with `context_eval.EvalRecord.from_dict`, and passes the
records plus `now=datetime.now(UTC)` into `promote()`. An unparsable file
exits non-zero with `unknown:` and the offending line number. `--dry-run`
prints the gate outcome — status, reason code, counted observations, newest
observation age, the window and minimum in force — and writes nothing; that is
also the documented "how to inspect the evidence" command, so no second
inspection subcommand is added. `--evidence-ref` becomes required whenever
`--evidence-kind context-eval` is used.

### 5. Documentation

- **`README.md`**: a new `### Context strategy release` section directly after
  "### Context evaluation", covering the full ladder with runnable commands:
  `publish` -> `promote --environment shadow` (the candidate) -> soak (the
  production investigator at `CONTEXT_RELEASE_ROLLOUT_MODE=observe` with
  `ISSUE_INVESTIGATOR_CONTEXT_EVAL=on` and a store execution per run; the
  default strategy stays authoritative and the candidate is never served) ->
  build the evidence file from the `[context] context_eval=` log lines whose
  `evidence_kind` is `observe-candidate` -> inspect with `promote --dry-run` ->
  open the promotion PR -> `rollback --to-revision N` -> break-glass
  `CONTEXT_RELEASE_ROLLOUT_MODE=off`. It states plainly that making the
  candidate authoritative (a binding at `enforce`, or
  `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY`) produces no soak evidence and is itself
  a production change, and prints the refusal-reason table.
- **`.env.example`**: audit the `ISSUE_INVESTIGATOR_CONTEXT_*` /
  `CONTEXT_RELEASE_*` block so each of the four lifecycle variables
  (`ISSUE_INVESTIGATOR_CONTEXT_MODE`, `ISSUE_INVESTIGATOR_CONTEXT_STRATEGY`,
  `ISSUE_INVESTIGATOR_CONTEXT_EVAL`, `CONTEXT_RELEASE_ROLLOUT_MODE`, plus the
  break-glass `CONTEXT_RELEASE_REQUIRED`) is commented out, says what unset
  means, and cross-references the new README section. The existing "no variable
  for the window or the observation count" note stays and is strengthened to
  name #528 as the consumer.
- **`docs/adr/019-context-strategy-release-contract.md`**: a Slice C amendment
  that (a) removes the sec. 5 note deferring the compare line's evaluation
  reference and states which four keys shipped, (b) records the refusal
  precedence table and the `assess_evidence` status -> verdict mapping as the
  soak gate's normative definition, (c) records the production `evidence`
  block's two new fields (`observedAt`, `observations`), and (d) points at the
  README runbook. It does not reopen any of the fields listed under "What this
  ADR may not be reopened to change".

## Alternatives

1. **Have `context_release.py` read the evidence itself from mctl-api.**
   Rejected: it would drag `orchestrator.work_context.client`, HTTP and a token
   into a pure catalog module that today opens only local YAML, and it would
   make the gate untestable without a fake server and unreviewable in a PR. The
   evidence file keeps the gate's input a reviewable artifact that the promotion
   PR can reference, and keeps "no network, no clock" true of both
   `context_release` and `context_eval`.
2. **Re-derive the record shape inside `context_release.py` instead of adding
   `EvalRecord.from_dict`.** Rejected: two copies of one schema, drifting on the
   next ADR 015 field. `context_eval.py` already owns three `from_dict`s
   (`EvidenceIdentity`, `CaseLabels`, and `StoreRef` next door), so the fourth
   belongs there and is covered by a round-trip test.
3. **Emit full counter deltas and a "winner" verdict on `CONTEXT_STRATEGY_COMPARE`,
   as ADR 019 sec. 5's original paragraph described.** Rejected for this slice:
   it would reimplement in `context_assembly.py` the arithmetic
   `context_eval._compute_metrics` already owns, against a shadow snapshot that
   is deliberately never persisted — a second, disagreeing metric, which is the
   exact failure ADR 019's own note warns about. The evaluator reference gives
   the correlation the task asks for at none of that cost.
4. **Ship a `production` binding in this PR so the path is exercised end to end.**
   Rejected: no 3-run, 7-day evidence exists on the running image yet, and
   `test_committed_catalog_has_no_production_binding` encodes the deliberate
   choice that a production promotion is its own reviewed PR by an operator, not
   a side effect of merging the gate that guards it.
5. **A separate `docs/operations/context-strategy-release.md` runbook, like
   `docs/operations/usage-collector.md`.** Rejected: task 12's DoD explicitly
   says "from the README", and two operator documents for one lifecycle diverge.
   The ADR links to the README section instead.

## Platform impact

- **Migrations:** none. No mctl-api table, no route, no GitOps schema change, no
  agent manifest change, no new secret, no new network call. The two new
  `evidence` fields are additive and omitted when unset.
- **Backward compatibility:** `CONTEXT_RELEASE_ROLLOUT_MODE` still defaults to
  `off`, so the investigator's prompt bytes, sealed snapshots and `snapshot_id`s
  are unchanged until an operator moves a variable. Shadow promotion behaviour
  is byte-identical to Slice A. Two existing tests change expectation on
  purpose and are called out in `tasks.md`:
  `test_production_promotion_is_always_refused_as_evidence_missing` (still true
  for `evidence.kind: none`, now for a stated reason rather than
  unconditionally) and
  `test_non_shadow_promotion_is_refused_even_when_not_named_production`
  (`evidence-missing` -> `unknown`).
- **Resource impact:** the gate runs only in the CLI, off the request path: one
  file read and one pure pass over a handful of records. The compare line grows
  by four short string fields and is emitted only at `observe` with a resolved,
  differing bound strategy. No change at `off`.
- **Risks and mitigations:**
  - *Implementation-hash churn.* Editing `context_assembly.py` invalidates both
    strategies' `implementationHash`. Mitigated by making the republish +
    shadow-revision append an explicit, ordered task with the CI guard
    (`test_published_catalog_hashes_are_not_drifted`) as its DoD — the same
    dance revisions 2-5 already record. It must be the **last** code task, or it
    is immediately stale.
  - *The gate turns into "we checked what we already rolled out".* Mitigated by
    the gate counting `observe-candidate` records only, and by a regression test
    that three `live` records of an authoritative candidate are refused.
  - *The candidate leaks into the investigation it is measured in.* Unchanged
    Slice B invariant, now also covering `AssemblyResult.observe_candidate`: a
    test asserts it never reaches the prompt, `snapshot`, `rendered` or the
    store client.
  - *A hand-edited evidence file passes the gate.* The evidence file is operator
    input. Mitigated by `EvalRecord.from_dict` validating `record_kind`/`verdict`,
    by the identity match being against the catalog's own
    `contentHash`/`implementationHash` (not against anything in the file), by
    observations being keyed on store execution ids, and above all by promotion
    remaining a reviewed PR: the revision records `ref`, `evaluatorVersion`,
    `observedAt` and `observations` for a reviewer to check against mctl-api.
    Fabricating evidence is possible only by also fabricating a git-reviewed
    commit — the same trust boundary every other catalog change in this repo has.
  - *The gate silently loosens.* Mitigated by the policy constants being imported
    from `context_eval.ADR019_V1_*` with no env-var override, and a test that
    asserts `context_release` reads no environment variable for either.
  - *A production binding resolves a strategy the running image does not
    implement.* Unchanged mitigation: `resolve()` recomputes
    `implementationHash` against the files in the image and fails closed, and
    `tools/context_release.py resolve` stays the CI preflight.
  - *An operator cannot get out fast.* `CONTEXT_RELEASE_ROLLOUT_MODE=off`
    removes the binding from the decision path with one variable and no catalog
    change; `rollback --to-revision N` restores an exact prior revision. Both are
    documented in the README section with copy-pasteable commands.
- **Security / safety invariant:** unchanged and re-asserted. Nothing this slice
  adds is readable by a policy, capability-eligibility or authorization path;
  `context_release` still must not be imported by a policy module, and the new
  `context_eval` import is deferred inside a function body. The compare line
  gains only ids, names and versions — no `locator`, no `selector`, no byte
  derived from a retrieved payload (ADR 009 sec. 5, ADR 015 sec. 3).
