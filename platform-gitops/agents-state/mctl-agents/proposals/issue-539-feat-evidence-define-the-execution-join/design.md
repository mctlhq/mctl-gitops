# Design: issue-539-feat-evidence-define-the-execution-join

## Current state

### The evidence envelope accepts only `we_`

`orchestrator/execution_evidence.py` implements ADR 018's Tier A contract:
frozen dataclasses, `seal()` as the only identity-filling constructor,
`from_dict` with `_reject_unknown_keys`, `_safe()` redaction before hashing,
and a derived `completeness`. The join block is three fields
(`execution_evidence.py:245-270`):

```python
@dataclass(frozen=True)
class ExecutionJoin:
    execution_id: str
    work_item_id: str = ""
    trace_id: str = ""
```

and the only validation is one-sided (`execution_evidence.py:869-874`):

```python
def _check_execution_join(join: ExecutionJoin) -> None:
    if join.execution_id and not join.execution_id.startswith(EXECUTION_ID_PREFIX):
        raise ExecutionEvidenceError(...)
```

`EXECUTION_ID_PREFIX = "we_"` (`execution_evidence.py:83-84`) is a deliberate
duplicate of `orchestrator/work_context/snapshots.py:39`, pinned equal by
`tests/test_execution_evidence.py:508-513` (T11). `work_item_id` and
`trace_id` are unvalidated. Required-block enforcement keys on the single
field (`execution_evidence.py:1041`):

```python
_check("execution", True, not execution.execution_id)
```

### Only investigator runs hold a `we_`

`we_` is minted exclusively by mctl-api. `orchestrator/work_context/executions.py:4-15`
is explicit: "mctl-api is the identity authority … Nothing here ever invents
one locally." The one entry point is
`work_context.executions.resolve_identity(item, execution_id_flag, client,
attach=True)` (`executions.py:203`), reached through
`WorkItemClient.attach_execution` (`client.py:291`) or
`fulfil_execution_request` (`client.py:359`).

`grep -l work_context orchestrator/run_*.py` matches only
`run_issue_investigator.py`. Concretely:

| Driver | Identity obtained |
| --- | --- |
| `orchestrator/run_issue_investigator.py` | `ex-` at `:2536-2543`; `we_` via `resolve_identity` at `:2311-2313` |
| `orchestrator/run_implementer.py` | `ex-` only — `load_from_environment(executor_type="implementer", ...)` at `:3849-3851` |
| `orchestrator/run_shepherd.py` | `ex-` only — `load_from_environment(...)` at `:3953-3955`, passed to `process_one(..., execution_id=execution_context.context_id)` at `:4083` |

### Every governed mutation is stamped with `ex-`

`ExecutionContext.context_id` is `"ex-" + content_hash[7:23]`
(`orchestrator/execution_identity.py:651`, re-derived and compared at `:812`).
The literal `"ex-"` is not exported as a named constant at either site.

- `policy_checkpoint.current_identity()` returns
  `ExecutionIdentity(execution_id=ctx.context_id, ...)`
  (`policy_checkpoint.py:641`); `request_for()` stamps it onto every
  `ActionRequest` (`:678-682`); `decision_record()` emits it as the first key
  of every `POLICY_DECISION` line (`:551-552`). So a `POLICY_DECISION`'s
  `execution_id` is always `ex-`, never `we_`.
- `action_approvals.intent_for()` copies `request.execution_id` straight into
  `ActionIntent.execution_id` (`action_approvals.py:140-148`), the first field
  of the `intent_hash` mctl-api binds an `aar_` to (`:98-128`), and
  `redeem()` refuses outright when it is blank (`:416-419`). So `aar_`
  approvals are bound to `ex-` too, and `ActionIntent.work_item_id` is left
  empty in this slice (`:138-139`).
- `usage_ledger.py:59-66` documents the overload in prose; the only check is
  `_EXECUTION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")`
  (`:176`), which accepts `we_`, `ex-` and a bare sha256 hex identically.
  ADR 012 records the same at `docs/adr/012-...:153`.

### The resulting hole

`ExecutionJoin` is the only structure in the repository that *demands* a
`we_`. Because implementer runs, shepherd runs (including the #519/#524 gated
merge), policy decisions and approvals carry only `ex-`, no valid envelope can
be sealed for any of them today — exactly the executions #199 most needs.

### Test and fixture baseline

`tests/test_execution_evidence.py` is T1..T14. Relevant:
`test_golden_fixture_round_trips_and_hash_and_id_match_literals` (`:218`)
asserts `evidence.to_dict() == raw` plus the hardcoded literals
`sha256:624602c7…` and `ev-624602c79c9fe0cf` against
`tests/fixtures/evidence/investigator-evidence.json` (the only fixture, whose
`execution` block has exactly three keys). T5 (`:272`) parametrizes redaction
over `sorted(ee.BLOCK_NAMES)` and plants credentials into
`execution.trace_id`. T11 (`:508`) pins prefix equality with owning modules.
There is **no** negative test on `ExecutionJoin` at all today.

Conventions: no root `CLAUDE.md`; `CONTRIBUTING.md:33-56` and `LLMS.md:24-30`
give `uv run pytest tests/`, `uv run ruff check orchestrator config tests`,
`uv run mypy`, Conventional Commits, English, no emoji, line length 120.
ADR amendments are made **in place** — `docs/adr/009-context-snapshot-contract.md:328`
and `:405` are appended `## Amendment N — <title> (<issue>)` sections; a new
ADR number is reserved for a new contract (and `docs/adr/` already has three
files numbered `011-*`, so minting a number is unattractive).

## Proposed solution

**Adopt the issue's model (B): an explicit two-identity join, as two
distinct, typed fields on `ExecutionJoin`, staying within
`evidence.mctl.ai/v1alpha1` as an additive optional field.**

### 1. `ExecutionJoin` gains one typed field

```python
@dataclass(frozen=True)
class ExecutionJoin:
    execution_id: str = ""            # canonical work execution, `we_` ONLY
    work_item_id: str = ""
    trace_id: str = ""
    runtime_execution_id: str = ""    # ADR 011 ExecutionContext id, `ex-` ONLY
```

`execution_id` becomes defaulted so a runtime-only envelope is constructible;
requiredness is enforced by `seal()`, not by the dataclass signature, which is
already how every other block in this module works
(`execution_evidence.py:236-241`).

New module constants, alongside the existing deliberate duplicates
(`execution_evidence.py:83-96`):

```python
#: orchestrator/execution_identity.py's seal() context id prefix (ADR 011)
RUNTIME_EXECUTION_ID_PREFIX = "ex-"
_RUNTIME_EXECUTION_ID_PATTERN = re.compile(r"ex-[0-9a-f]{16}")
#: Which identity an envelope is primarily retrieved by.
EXECUTION_REF_KINDS = frozenset({"work", "runtime"})
```

`_reject_unknown_keys` in `ExecutionJoin.from_dict` gains
`runtime_execution_id` and nothing else.

### 2. Symmetric, cross-rejecting validation

`_check_execution_join` becomes two-sided:

```python
def _check_execution_join(join: ExecutionJoin) -> None:
    if join.execution_id:
        if join.execution_id.startswith(RUNTIME_EXECUTION_ID_PREFIX):
            raise ExecutionEvidenceError(
                "execution.execution_id carries a runtime ExecutionContext id "
                f"{join.execution_id!r}; put it in execution.runtime_execution_id"
            )
        if not join.execution_id.startswith(EXECUTION_ID_PREFIX):
            raise ExecutionEvidenceError(...)
    if join.runtime_execution_id:
        if join.runtime_execution_id.startswith(EXECUTION_ID_PREFIX):
            raise ExecutionEvidenceError(
                "execution.runtime_execution_id carries a work execution id "
                f"{join.runtime_execution_id!r}; put it in execution.execution_id"
            )
        if not _RUNTIME_EXECUTION_ID_PATTERN.fullmatch(join.runtime_execution_id):
            raise ExecutionEvidenceError(...)
```

The runtime field is checked against the **full derived shape**
(`ex-` + 16 lowercase hex) rather than a bare prefix, mirroring
`_EVIDENCE_ID_PATTERN` (`execution_evidence.py:146`), because
`execution_identity.seal()` produces exactly that shape and a looser check
would let arbitrary text through into `to_dict()`. `execution_id` keeps a
prefix-only check because `we_` ids are ULIDs minted by mctl-api whose body
shape this repository does not own.

### 3. Primary retrieval identity

The envelope's own primary key stays `evidence_id` (content-derived,
`execution_evidence.py:818`). For *execution-scoped* retrieval the amendment
names a derived, typed pair — never one overloaded column:

```python
@property
def primary_execution_ref(self) -> tuple[str, str]:
    """(kind, id) with kind in EXECUTION_REF_KINDS. `work` wins when both
    identities are present. Derived, never stored, never hashed — the same
    rule `ExecutionEvidence.completeness` follows."""
    if self.execution_id:
        return ("work", self.execution_id)
    if self.runtime_execution_id:
        return ("runtime", self.runtime_execution_id)
    return ("", "")
```

Tier B (mctl-api#409) indexes on the **pair** — two typed columns,
`primary_execution_kind` and `primary_execution_id` — so an `ex-` and a `we_`
are never comparable as one untagged value, which is precisely the defect
`usage_ledger.execution_id` and `model_usage_records.execution_id` already
carry. Stability holds per envelope because both inputs are hashed fields of
an immutable, content-addressed document: attaching a `we_` later produces a
*new* envelope with a new `ev-`, never a mutation of this one.

`to_log_dict()` gains `primary_execution_kind` only (a two-value closed slug),
keeping ADR 018's "codes and counts, never ids or lists" trace surface.

### 4. Completeness for a runtime-only run

One line in `_check_required_blocks` (`execution_evidence.py:1041`):

```python
_check("execution", True, not (execution.execution_id or execution.runtime_execution_id))
```

So an implementer or shepherd run with an `ex-`, an outcome and at least one
policy decision seals `COMPLETE` with no gap; an envelope with neither
identity still raises unless a `Gap(block="execution", required=True)` accounts
for it. `BLOCK_NAMES` is unchanged — the runtime identity lives inside the
existing `execution` block, so gaps, redaction (T5) and `Requirements` all keep
working untouched.

### 5. Hash neutrality — why `v1alpha1` is enough

`_content_payload` already states the absent-when-empty rule at **block**
level (`execution_evidence.py:984-991`, citing
`context_snapshot.py:1174-1207`). This amendment extends the identical rule to
one **leaf**: a blank `runtime_execution_id` never enters the hashed bytes.

Two changes implement it, and together they make the hashed `execution` block
a pure function of the dataclass in every path:

1. `ExecutionJoin.to_dict()` emits `runtime_execution_id` **only when
   non-blank**. This is what `_content_payload` (and therefore
   `recompute_content_hash`) and `ExecutionEvidence.to_dict()` both use.
2. `seal()` prunes a blank `runtime_execution_id` from
   `safe_payload["execution"]` before building `clean_execution` and before
   hashing. This covers the one path where a blank can reappear after
   `to_dict()`: `_safe()` rewrites a dropped leaf to `_REDACTED_LEAF = ""`
   (`execution_evidence.py:159-168`) rather than omitting it.

Verified against the live module: sealing a `we_`-only join today produces a
hashed `execution` block of exactly
`{"execution_id": ..., "trace_id": ..., "work_item_id": ...}`. With the prune,
that block is byte-identical after the change, so
`tests/fixtures/evidence/investigator-evidence.json` keeps
`sha256:624602c79c9fe0cf…` and `ev-624602c79c9fe0cf`, and
`test_execution_evidence.py:218`'s `to_dict() == raw` still holds with the
fixture file **unedited**.

Therefore the change is a backward-compatible additive optional field:
`API_VERSION` stays `evidence.mctl.ai/v1alpha1` and `SUPPORTED_API_VERSIONS`
gains no entry. Bumping would force Tier B to implement two document shapes
and two conformance suites on day one, for a contract that has no persisted
data yet, and would make every existing fixture a legacy artefact. The ADR
states this explicitly, as the issue's deliverable 1 requires.

### 6. Prefix-drift test needs a named constant

`"ex-"` is a bare literal at `execution_identity.py:651` and `:812`, so the
T11 equality test cannot be written — the same gap `SNAPSHOT_LOCAL_ID_PREFIX`
documents at `execution_evidence.py:88-91`. Fix it properly: export
`CONTEXT_ID_PREFIX = "ex-"` from `orchestrator/execution_identity.py`, use it
at both sites and add it to that module's `__all__`. A pure,
behaviour-preserving extraction, exactly like ADR 018's own
`orchestrator/redaction.py` move. The evidence module still duplicates the
literal (its docstring pins it to three intra-repo imports and
`execution_identity` pulls `os`/`json`/`hmac`/`pathlib`); the test imports both
and asserts equality, extending
`test_prefixes_agree_with_their_owning_modules`.

### 7. ADR 018 amendment

Append `## Amendment 1 — the execution join: `we_` and `ex-` as two typed
fields (mctlhq/mctl-agents#539)` to
`docs/adr/018-execution-evidence-envelope-contract.md`, following ADR 009's
appended-section precedent verbatim. It states: the chosen model and why (A)
was rejected; the exact four-field `ExecutionJoin` table; that
`primary_execution_ref` is the named execution-scoped retrieval identity and
`evidence_id` remains the envelope's own key; the deterministic linkage rule
(policy decisions and `aar_` approvals bind to `runtime_execution_id`, work
executions to `execution_id`); the completeness rule; and the `v1alpha1`
justification. It also edits sec. 1's `ExecutionJoin` line and sec. 5's
execution-identity boundary row in place, since `018:346-350` names those as
the things a follow-up must not silently reopen — an amendment is the
sanctioned vehicle.

### 8. Golden vectors (Tier B conformance fixtures)

Three committed fixtures under `tests/fixtures/evidence/`, each verified for
literal `content_hash`, literal `ev-`, `to_dict()` round-trip and
`recompute_content_hash()` agreement:

| Fixture | Join | Represents |
| --- | --- | --- |
| `investigator-evidence.json` (existing, unchanged) | `we_` only | investigator run, `("work", "we_…")` |
| `implementer-evidence.json` (new) | `ex-` only | implementer run: `policy_decisions` + `approvals` bound to the `ex-`, `("runtime", "ex-…")` |
| `shepherd-evidence.json` (new) | both | #519/#524 gated merge: `we_` attached and `ex-` runtime, `("work", "we_…")` |

Naming follows the repo's `tests/fixtures/<domain>/<role>-<domain>.json`
convention (`tests/fixtures/identity/investigator-context.json`,
`tests/fixtures/capability/investigator-capability-set.json`). mctl-api#409
ports all three verbatim.

## Alternatives

1. **Model (A): resolve implementer and shepherd runs to a canonical `we_`.**
   Dropped. It is the larger change and it weakens the contract. A `we_`
   exists only because mctl-api minted it for a `(work_item_id, engine,
   engine_ref)` triple (`work_context/executions.py:4-15`); obtaining one for
   every shepherd tick means a network round trip and a work item for runs
   that legitimately have none (an incident-responder sweep, a reconcile pass,
   a local run). Either mctl-agents starts minting — the "no second execution
   authority" the issue forbids — or every governed mutation becomes
   unrecordable when the store is unreachable, turning an evidence contract
   into an availability dependency. It would also not remove the need for the
   `ex-` field: policy decisions and `aar_` intents are hash-bound to the
   runtime id (`action_approvals.py:120-148`), so dropping it would break the
   deterministic linkage the issue requires. Model (B) keeps (A) available as
   a purely additive *producer* change later: attach a `we_`, and the envelope
   simply carries both.
2. **A new top-level optional block `runtime_execution` beside `execution`.**
   Dropped. It needs no new hashing machinery (the block-level
   absent-when-empty rule at `execution_evidence.py:984-991` already covers
   it) and would add a `BLOCK_NAMES` member, but it splits one join across two
   blocks, gives the redaction test (T5) and `Requirements` a block that is
   never independently required, and makes "which block is the join" ambiguous
   for Tier B. The issue asks for two typed *fields*, and the leaf-level prune
   costs about ten lines.
3. **Bump to `evidence.mctl.ai/v1alpha2`.** Dropped. Nothing is persisted yet
   (Tier B is unbuilt), so there is no migration a version bump would buy.
   `SUPPORTED_API_VERSIONS` would carry two entries, `from_dict`/`seal` would
   need per-version branching, and mctl-api#409 would have to ship two
   conformance suites on day one. The prune rule makes the change provably
   hash-neutral, which is the condition under which this repository has always
   grown a contract additively (ADR 009's two amendments did the same).
4. **Overload `ExecutionJoin.execution_id` to accept either prefix, as
   `SNAPSHOT_ID_PREFIXES` accepts `cs_`/`cs-`.** Dropped. That precedent is
   two *spellings of the same referent* (a store snapshot id and its local
   seal). `we_` and `ex-` name different things owned by different authorities
   with different lifetimes, and the issue explicitly forbids overloading.
   This is exactly the defect `usage_ledger.py:59-66` already carries, and
   `_EXECUTION_ID_RE` (`:176`) shows where it ends: a regex that cannot tell
   the two apart, so no consumer can either.
5. **Let mctl-api#409 settle the join inside the storage layer.** Dropped —
   the issue names this as the failure mode to avoid, and ADR 018 alternative
   4 already recorded the principle: the contract is defined where the
   evidence is produced.

## Platform impact

**Migrations.** None. No schema, no database, no gitops file, no Helm value,
no ArgoCD application. Nothing is persisted by this module.

**Backward compatibility.** Fully additive and hash-neutral.
`orchestrator/execution_evidence.py` still has no importer —
`run_issue_investigator.py`, `run_implementer.py`, `run_shepherd.py` and
`orchestrator/temporal/workflows/dev_loop.py` are untouched, so the module
stays inert as ADR 018 requires. `investigator-evidence.json` keeps its bytes,
its `content_hash` and its `ev-`. The one edit outside the evidence module is
extracting `CONTEXT_ID_PREFIX = "ex-"` in
`orchestrator/execution_identity.py`; it is a literal-to-constant substitution
at two sites, covered by `tests/test_execution_identity.py`, which must pass
unchanged.

**Resource impact.** Nil at rest. At seal time: one extra dict key check and
one extra regex `fullmatch` on a 19-character string. No network call, no file
handle, no new dependency in `pyproject.toml`; the module stays stdlib-only
(T8/T9 keep asserting it).

**Risks and mitigations.**

- *The prune rule silently changes an existing hash.* The highest-value risk.
  Mitigated by keeping `investigator-evidence.json` and
  `test_execution_evidence.py:218`'s two hardcoded literals unedited — if the
  hashed `execution` block moves by one byte, that test fails. Reinforced by a
  new test that seals a `we_`-only join with and without an explicitly blank
  `runtime_execution_id` and asserts identical `content_hash`.
- *`seal()` and `recompute_content_hash()` disagree after a redaction.*
  `_safe()` rewrites a dropped leaf to `""` rather than omitting it
  (`execution_evidence.py:159-168`), so without the `seal()`-side prune a
  redacted `runtime_execution_id` would hash as present and recompute as
  absent. Mitigated by pruning in `seal()` after `_safe()` and before both
  `clean_execution` and the hash, and by extending T5's per-block redaction
  round-trip parametrization to cover the new field.
- *The two identities are inconsistent — a `we_` and an `ex-` from different
  runs.* Not detectable inside a payload-free contract; the linkage lives in
  the work-item layer. Mitigated by the amendment stating that the producer
  owns pair consistency and the contract validates shape only, and by the
  precedence rule making the `we_` authoritative when both are present.
- *Someone re-overloads the field later.* Mitigated by the symmetric
  cross-rejection and by two negative tests that fail if either direction of
  the check is deleted — the issue's acceptance criterion.
- *Prefix drift between `ex-` here and in `execution_identity.py`.* Mitigated
  by the extracted `CONTEXT_ID_PREFIX` constant and the extended T11 equality
  test.
- *Tier B indexes the pair as one column anyway.* Mitigated by shipping the
  `ex-`-only and both-identities golden vectors as the conformance fixtures
  mctl-api#409 ports, so a single-column implementation fails them.

**Security.** Unchanged. No new authorization-shaped field name is
introduced — `runtime_execution_id`, `primary_execution_ref` and
`primary_execution_kind` contain none of `allow`/`deny`/`permit`/`grant`/
`authorized`, so T10 keeps passing. Both identities are bounded, non-secret,
content-derived ids, and both pass through `_safe()` before hashing like every
other leaf. The envelope remains strictly non-authoritative.

**Follow-ups named, not built here.**

1. The #199 evidence producer: seal an envelope at the end of a governed
   implementer/shepherd workflow, populating `runtime_execution_id` from
   `execution_identity.load_from_environment()` and `execution_id` from
   `work_context.executions.resolve_identity()` when one exists.
2. De-overload `usage_ledger.execution_id` (`:59-66`, `:176`) and mctl-api's
   `model_usage_records.execution_id` into the same two typed fields, so the
   ledger stops being the counter-example this contract cites.
3. Optionally attach a `we_` for implementer and shepherd runs (the issue's
   model (A) as a producer-side enhancement). Purely additive under model (B);
   no contract change required.
4. Tighten `ExecutionJoin.trace_id` to ADR 011's 32-lowercase-hex shape. Held
   back because the existing golden fixture uses a Temporal workflow id there,
   and changing it would move a hash this proposal promises not to move.
