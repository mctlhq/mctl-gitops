# Design: issue-520-feat-evidence-define-and-seal-the-govern

## Current state

### The governance contracts that already exist, and who owns each record

Every record the evidence envelope must join is already canonical somewhere, and
each has exactly one owner:

| Record | Prefix / key | Owner in this clone |
| --- | --- | --- |
| Execution | `we_` | `orchestrator/work_context/snapshots.py:39` (`EXECUTION_ID_PREFIX`), `work_context/executions.py` (attach), `work_context/contract.py:166` (`ExecutionRef`) |
| Context snapshot | `cs_` (store) / `cs-` (local seal) | `orchestrator/work_context/snapshots.py:42`, `orchestrator/context_snapshot.py:1245` |
| Execution request | `xr_` | `orchestrator/work_context/execution_requests.py:32` (`REQUEST_ID_PREFIX`), states at `:38-42` |
| Model usage | `(session_id, result_uuid, model_key)` | `orchestrator/usage_ledger.py:27` — "mctl-api derives the row id from (session_id, result_uuid, model_key)"; posted to `/api/v1/usage/records` (`usage_ledger.py:100`) |
| Human approval | `aar_` | `orchestrator/action_approvals.py:47` (`ID_PREFIX`), states `:59-63`, `ActionIntent.intent_hash` `:120` |
| Policy decision | `action_digest` | `orchestrator/policy_checkpoint.py:165` (`Decision`), codes `:77-98`, `UNDECIDED_CODES` `:103`, emitted as `POLICY_DECISION` lines (`:105`) and as the `mctl.policy.decision` span event (`orchestrator/tracing.py:604-607`) |
| Generated artifact | name + kind | `orchestrator/tracing.py:638-641` (`ARTIFACT_WRITE_EVENT`, `record_artifact`) |

### The seam that is already cut for this work

`orchestrator/context_snapshot.py:728-745` defines:

```python
@dataclass(frozen=True)
class EvidenceRef:
    """A pointer into the #199 evidence store — `{evidence_id, kind}` only.
    No payload field exists; `from_dict` rejects any other key."""
    evidence_id: str
    kind: str
```

ADR 009 (`docs/adr/009-context-snapshot-contract.md:91`, `:137`, `:231`) states the
same rule from the other side: snapshots carry `evidence_refs` and nothing else,
because "evidence has exactly one owner". So the envelope's identity type already
has a consumer, and that consumer needs no change.

### The two primitives that must not be reinvented

`orchestrator/context_snapshot.py:117-144` declares the single hashing and
canonicalization rule for the repository, and says so explicitly:

```python
def _hash_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()

def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
```

exposed publicly as `hash_bytes` / `canonical_json` precisely so that "a caller
outside this module never has a reason to invent its own hashing" — ADR 009's
"a second, disagreeing hash convention creeps in" risk. `policy_checkpoint.py:52`
already imports them rather than re-deriving them.

The content-addressed sealing pattern is `context_snapshot.seal()`
(`:1210-1263`): a `_content_payload()` that excludes `content_hash`, `snapshot_id`
and `created_at`, a hash over its canonical JSON, an id of
`"cs-" + content_hash[7:23]`, a `validate()` call, and a companion
`recompute_content_hash()` (`:1266`) for golden-fixture tests. `[7:23]` is the
first 16 hex characters of the digest, since `"sha256:"` is 7 characters.

This is not a one-off: the same `_content_payload` / `seal` / `recompute_content_hash`
shape with the same `"<prefix>-" + content_hash[7:23]` id rule appears four times
already, and a fifth instance is exactly what this issue asks for:

| Seal | File:line | Id |
| --- | --- | --- |
| `context_snapshot.seal` | `context_snapshot.py:1245` | `"cs-" + content_hash[7:23]` |
| `execution_identity.seal` | `execution_identity.py:651` | `"ex-" + content_hash[7:23]` |
| `capability.seal` | `capability.py:885` | `"cap-" + content_hash[7:23]` |
| `human_input.seal_request` | `human_input.py:545` | `"hir-" + request_hash[7:23]` |
| **this proposal** | new | `"ev-" + content_hash[7:23]` |

Two hash conventions in the repo are deliberately *different* and must be carried,
never re-derived: `action_approvals.intent_hash` (`:120`) uses a length-prefixed
field encoding matching mctl-api's Go `IntentHash`, not canonical JSON; and
`work_context/contract.py:537` `execution_id_for` emits bare hex with no `sha256:`
prefix. The envelope stores these as opaque strings.

### The redaction precedent

`orchestrator/tracing_sdk.py:56-152` is the repository's redaction guard: a key
allowlist (`_ALLOWED_KEY`), a denylist applied on top (`_DENIED_KEY`, which refuses
`prompt`, `arguments`, `body`, `content`, `payload`, `diff`, `stdout`, ... suffixes),
a `token`-in-key rule, a credential-**shape** screen applied to every string value
regardless of key (`_CREDENTIAL_VALUE`: `ghp_`, `github_pat_`, `sk-`, `hvs.`, JWTs,
PEM private keys, `bearer`, basic-auth URLs), and a length cap
(`MAX_ATTRIBUTE_CHARS = 256`). Its docstring fixes the policy that the evidence
module must inherit: *dropped, never masked* — "a masked value is a present
attribute that reads like data, an absent one is honest".

That module imports `opentelemetry` (`Status`, `StatusCode`), so it cannot today be
imported by a stdlib-only module.

Two things follow that matter for this issue. First, **`_safe()` does not exist in
this repository.** There is no `_safe*` redaction helper anywhere in `orchestrator/`
— the only `_safe_`-prefixed functions are error-swallowing task wrappers in
`run_all.py:38,67` and a parser in `temporal/activities/deploy_state.py:175`. The
`_safe()` the issue asks to keep is PR #483's, which never landed. Tier A therefore
*defines* it rather than preserving it.

Second, the repository already contains a **declared-but-unimplemented redaction
contract** that says so out loud — `context_snapshot.py:296-324`:

```python
@dataclass(frozen=True)
class Redaction:
    """Whether the bytes hashed into `ContextSource.content_hash` were
    redacted before hashing. `rules` records rule ids, never matched text;
    `dropped_bytes` records volume only. No redaction helper exists in this
    repository yet (ADR 009 sec. 8) — this is a contract for one, not a
    claim about current behaviour."""
```

`rules` records rule ids and `dropped_bytes` records volume only. That is the shape
the evidence module's redaction accounting should match, so the two contracts
describe redaction the same way.

Finally, `orchestrator/human_input.py:46` already reserves the consumer-side prefix:

```python
CONTEXT_REF_PREFIXES = ("github:", "gitops-file:", "context_snapshot:", "evidence:")
```

enforced in `seal_request` at `:516-518`. So a second seam for `ev-` ids exists and,
like `EvidenceRef`, needs no change.

### What does NOT exist

There is no `orchestrator/evidence_store.py`, no `_evidence/` tree, and no evidence
module of any kind in this clone. PR #483's code never landed on `main`
(`git log`: HEAD is `c1925eb`, the release-please merge for #503). So Tier A is a
greenfield addition, not a repair.

### Module conventions to match

`pyproject.toml`: Python `>=3.12,<3.13`, ruff `line-length = 120`,
`target-version = "py312"`, mypy configured but not `strict`. Every contract module
uses `from __future__ import annotations`, frozen dataclasses with `to_dict()` /
`from_dict()`, a module-level `XxxError(ValueError)` for fail-closed validation,
closed vocabularies as module-level `frozenset`s, `_require_str` / `_require_int` /
`_require_sha256` / `_reject_unknown_keys` helpers, and a long module docstring
citing the issue and ADR. Tests are plain `pytest` functions in one
`tests/test_<module>.py` (74 in `tests/test_context_snapshot.py`, 26 in
`tests/test_policy_checkpoint.py`).

## Proposed solution

### Shape

Two files of new code, one behaviour-preserving extraction, one ADR, one test file.

```
orchestrator/redaction.py            NEW  stdlib-only; the credential/value screen,
                                          extracted verbatim from tracing_sdk.py
orchestrator/tracing_sdk.py          EDIT imports from orchestrator.redaction;
                                          no behaviour change
orchestrator/execution_evidence.py   NEW  the Tier A contract
docs/adr/018-execution-evidence-envelope.md  NEW
tests/test_execution_evidence.py     NEW
```

Nothing else is touched. No caller is rewired. The module ships inert and additive,
the way `context_snapshot.py` shipped under ADR 009.

### `orchestrator/redaction.py` (extraction, behaviour-preserving)

Move `_CREDENTIAL_VALUE`, `_DENIED_KEY`, `_TOKEN_KEY`, `MAX_ATTRIBUTE_CHARS`,
`_scalar_allowed` and `value_allowed` out of `tracing_sdk.py` into a stdlib-only
module (`re` only). `tracing_sdk.py` re-imports them, so `key_allowed`,
`redact_attributes`, `GuardedExporter` and every existing tracing test behave
identically. This exists so the evidence module can apply the *same* credential
screen while remaining importable by the Temporal worker, the pollers and the SDK
hooks — the stdlib-only constraint `policy_checkpoint.py:39-41` states.

Exported for evidence use: `contains_credential(text) -> bool`,
`safe_scalar(value, *, max_chars) -> bool`.

### `orchestrator/execution_evidence.py`

Stdlib-only. Imports exactly three things from the repository, each to avoid a
duplicated rule:

```python
from orchestrator.context_snapshot import canonical_json, hash_bytes   # the one hash rule
from orchestrator.policy_checkpoint import UNDECIDED_CODES, VERDICTS   # the canonical undecided set
from orchestrator.redaction import contains_credential, safe_scalar    # the one credential screen
```

Prefix constants (`we_`, `cs_`/`cs-`, `xr_`, `aar_`) are imported from their owning
modules where that import is free of heavy dependencies
(`work_context.execution_requests.REQUEST_ID_PREFIX`,
`action_approvals.ID_PREFIX`); where the owning module pulls `httpx` or a client,
the prefix is declared once with a comment naming the owner, and a test asserts the
two agree, so drift is caught rather than hidden.

#### Blocks

All frozen dataclasses, all references, no payloads:

- `ExecutionJoin` — `execution_id` (`we_`-validated), `work_item_id`, `trace_id`.
- `SnapshotRef` — `snapshot_id` (`cs_` or `cs-`), `content_hash` (`sha256:`).
- `ExecutionRequestRef` — `request_id` (`xr_`), `kind` ∈ `KINDS`, `state` ∈ `STATES`.
- `UsageRef` — `session_id`, `result_uuid` (optional), `model_key`,
  `devloop_stage` (optional). Join keys only; no counters, no cost. This mirrors the
  ledger's own idempotency key, so a row is locatable and never copied.
- `ApprovalRef` — `approval_id` (`aar_`), `intent_hash`, `state`.
- `PolicyDecisionRef` — `action_digest`, `verdict`, `code`, `policy_version`,
  `rule_id`, `approval_ref`. Its `undecided` property is
  `self.code in UNDECIDED_CODES` — the exact expression `Decision.undecided`
  already uses at `policy_checkpoint.py:180-181`, against the same imported
  frozenset. There is no second list.
- `ArtifactRef` — `name` (bounded, no separators), `kind`, `content_hash`
  (`sha256:`). Immutable ref only.
- `Outcome` — `code` ∈ `OUTCOME_CODES` (`succeeded`, `failed`, `refused`,
  `abandoned`, `superseded`), `reason_code` (slug).
- `Gap` — `block` ∈ `BLOCK_NAMES`, `code` ∈ `GAP_CODES`
  (`not_produced`, `store_unavailable`, `not_applicable`, `redacted_out`,
  `undecided`), `required: bool`.
- `ExecutionEvidence` — the envelope: `api_version`, `kind`, `evidence_id`,
  `content_hash`, `created_at`, plus the blocks above and `gaps`.

#### `completeness` is derived, never stored

```python
COMPLETE = "COMPLETE"
INCOMPLETE = "INCOMPLETE"

@property
def completeness(self) -> str:
    return INCOMPLETE if any(g.required for g in self.gaps) else COMPLETE
```

It is a property on the dataclass, not a field, so it is not in `__init__`, not in
`from_dict`'s accepted keys, and not independently settable. `COMPLETE` therefore
holds *if and only if* there are no required gaps, by construction rather than by
a convention a caller could violate — the old finding, fixed structurally.

#### `_safe()` covers the whole envelope

`_safe(payload: Mapping) -> tuple[dict, tuple[Gap, ...]]` walks the *entire*
assembled dict recursively — every block, no exceptions — and for each leaf:

1. rejects non-scalars that are not part of the declared structure;
2. drops any string longer than the declared per-field cap;
3. drops any string where `contains_credential()` fires;
4. for each drop, appends `Gap(block=<block it was in>, code="redacted_out",
   required=<whether that block is required>)`.

`seal()` calls `_safe()` **before** computing canonical bytes, so `content_hash` and
`evidence_id` certify the redacted document — a sealed id can never attest to bytes
containing a credential. Dropping rather than masking follows
`tracing_sdk.py:132-138`; recording the drop as a gap is what keeps redaction from
being silent, and it feeds `completeness` automatically.

#### Sealing

```python
def _content_payload(...) -> dict[str, Any]:   # everything except content_hash, evidence_id, created_at
def seal(*, ..., created_at: str, requirements: Requirements = DEFAULT_REQUIREMENTS) -> ExecutionEvidence:
def recompute_content_hash(evidence: ExecutionEvidence) -> str:
```

`seal()` is the only constructor. It assembles, redacts, validates, hashes, mints
`evidence_id = "ev-" + content_hash[7:23]`, and calls `validate()` before returning —
never a partially-sealed envelope. `created_at` is caller-supplied and excluded
from the hash, so re-sealing the same inputs at a different time yields the same
identity (ADR 009 sec. 2). Optional blocks are hashed only when present, so a future
optional block does not re-identify already-sealed envelopes
(`context_snapshot.py:1174-1207`).

`Requirements` is a small frozen dataclass the caller passes to declare which blocks
this execution was supposed to produce. `seal()` raises `ExecutionEvidenceError`
when a required block is both absent and ungapped — so an omission is a hard error,
not a quietly `COMPLETE` envelope.

#### No paths, no I/O

The module imports `re`, `json` (transitively, via `canonical_json`) and
`dataclasses`. It does not import `pathlib`, `os`, `open`, `httpx` or `urllib`. No
function accepts, builds or returns a path, and `ArtifactRef.name` is validated
against a bounded pattern with no `/`, `\`, `..` or leading `~` — the old
"caller-controlled path construction" and "absolute pointer files" findings are
closed by the module having no filesystem surface at all.

#### Payload-free emission

```python
    def to_log_dict(self) -> dict[str, Any]:
        # {evidence_id, content_hash, completeness, outcome_code,
        #  snapshot_ref_count, usage_ref_count, ... , gap_count} — nothing else

def evidence_ref(evidence: ExecutionEvidence, kind: str) -> dict[str, str]:
    # {"evidence_id": ..., "kind": ...} — shaped for context_snapshot.EvidenceRef
```

`to_log_dict()` is the established name and shape for exactly this projection —
`ContextSnapshot.to_log_dict` (`context_snapshot.py:1082`) already reports
`"evidence_ref_count": len(self.evidence_refs)`, counting rather than listing. It
returns integer counts per block and closed-vocabulary codes only; there is no
field in it that can hold content. A runtime may print it or annotate a span with
it. Neither function writes anything. `evidence_ref()` produces exactly the two keys
`context_snapshot.EvidenceRef.from_dict` accepts, so the existing seam is used
unchanged; the same id is also usable as a `human_input` `"evidence:"` context ref.

### Conventions this module must follow

From the peer contract modules: `from __future__ import annotations`; frozen
dataclasses only (the repo has 166 `@dataclass(frozen=True)` against 24 bare, and
zero `enum.Enum` — closed vocabularies are `frozenset`s of `str` constants);
`tuple[...]` not `list[...]` for collections; `#:` attribute-doc comments on
constants that need justification; one `ExecutionEvidenceError(ValueError)` with the
standard fail-closed docstring; the `_reject_unknown_keys` / `_require_mapping` /
`_require_str` / `_require_int` / `_require_bool` / `_optional_str` /
`_require_sha256` helper block **copied and retyped to this module's error class** —
`context_snapshot.py:84-94` states that duplication of these tiny validators is
deliberate, so this module does not import them; an `__all__` list, alphabetical,
as in `capability.py:62-84`; the `api_version` / `kind` gate copied from
`context_snapshot.py:875-889`; ruff `line-length = 120`, `target-version = "py312"`.

The one thing that is deliberately *shared* rather than duplicated is the pair of
security- and identity-critical rules: `hash_bytes`/`canonical_json` (already shared
for exactly this reason) and the credential screen. Duplicating a tiny
`_require_int` is harmless because a divergence is a one-line fix in whichever
module is wrong; duplicating a credential regex is not, because the copy that
drifts is the one that silently stops catching a new token format.

### ADR 018

`docs/adr/018-execution-evidence-envelope-contract.md`. `018` is the next number
above the highest used (`017`); `015` and `016` are free but burned, and `011` is
already triple-claimed by three near-simultaneous proposals, so prose must
disambiguate ADRs by full path rather than by number.

Structure follows `009` / `011-execution-identity` / `017`: `# ADR 018 — <title>`
(em dash), then a blockquote front matter of `**Status:** proposed`, `**Date:**`,
`**Issue:** mctlhq/mctl-agents#520 (parent #199; supersedes the design of #483)`,
`**Supersedes:**`; then `## Context`, `## Decision` with numbered `### N.`
subsections (`1. Canonical shape — evidence.mctl.ai/v1alpha1, kind: ExecutionEvidence`
with the field/owner/meaning table; `2. Identity and immutability` stating the hash
rule verbatim; `3. Redaction`; `4. Completeness and gaps`; `5. Boundary rules —
normative and testable` as the `| Concern | Owner | What the envelope may record |
What it must never do |` table), then `## Alternatives`, `## Non-goals`,
`## Platform impact`, `## Implementation map` with the fenced file list and the
closing "which sections are normative and may not be reopened" paragraph.

Two statements are load-bearing and must appear: that persistence and retrieval are
Tier B and owned by mctl-api, and that #483's gitops-persistence design is
superseded and must not be continued.

## Alternatives

**1. Repair `orchestrator/evidence_store.py` and `_evidence/` from PR #483.**
Dropped. The issue forbids it, and independently it is wrong: it writes governance
evidence into a *public* repository, it creates a second copy of work-item,
execution, snapshot and usage state that must then be reconciled, and its 3650-day
retention is a data-protection commitment mctl-agents cannot make on mctl-api's
behalf. It also predates `we_`, `cs_`, `xr_` and the shipped usage ledger, so its
joins would have to be rewritten anyway — there is nothing left to salvage.

**2. Extend `ContextSnapshot` with the evidence blocks instead of a new module.**
Dropped. ADR 009 is explicit that "evidence has exactly one owner" and that
snapshots carry `evidence_refs: {evidence_id, kind}` only
(`docs/adr/009-context-snapshot-contract.md:231`). Beyond the contract violation, it
is mechanically unsafe: `_content_payload` hashes the snapshot's fields, so adding
blocks would re-identify every already-sealed `snapshot_id` — including the ones
`context_assembly`'s production `seal()` has already written into `.status.yaml`
files in gitops (`context_snapshot.py:1179-1186` names exactly this hazard).

**3. Define the envelope as a JSON Schema document validated by a generic
validator.** Dropped. The repo has no schema-validation dependency and every peer
contract (`context_snapshot.py`, `execution_identity.py`, `policy_checkpoint.py`,
`work_context/contract.py`) is expressed as frozen dataclasses with explicit
`from_dict` validation. A JSON Schema could express the field types but not the two
rules that matter here — `completeness` derived from gaps, and `_safe()` running
before the hash — so the interesting half of the contract would end up in Python
anyway, in two places.

**4. Specify and build the envelope in mctl-api first.** Dropped for Tier A. The
producer of the evidence is mctl-agents: it is the process that holds the `we_`,
the sealed snapshot, the `xr_`, the policy decisions and the outcome at the moment
they are true. Defining the contract where it is produced, with no persistence, is
what makes Tier B a straightforward mctl-api issue rather than a negotiation.

**5. Duplicate the credential regexes into the evidence module instead of
extracting `redaction.py`.** Dropped. Two copies of a credential screen drift, and
the copy that drifts is the one that stops catching a new token format. This is
precisely the "second, disagreeing convention" failure ADR 009 records for hashing;
the answer there was a single public alias, and the answer here is a single
stdlib-only module.

## Platform impact

**Migrations.** None. No schema, no database, no gitops file, no ArgoCD application,
no Helm value. Nothing is persisted, so there is nothing to migrate.

**Backward compatibility.** Fully additive. `orchestrator/execution_evidence.py` has
no importer on day one. `context_snapshot.EvidenceRef` is untouched, so no existing
`snapshot_id` or `content_hash` changes. The one edit to existing code —
`tracing_sdk.py` importing its regexes from `orchestrator/redaction.py` — is a pure
move; `tests/test_tracing.py`, `tests/test_tracing_agents.py` and
`tests/test_tracing_temporal.py` cover it and must pass unchanged.

**Resource impact.** Nil at rest. At seal time: one recursive walk plus one
`json.dumps` and one `sha256` over a document of bounded size (every field is
length-capped and every collection count-capped), so microseconds and no allocation
worth measuring. No network call, no file handle, no new dependency in
`pyproject.toml`.

**Risks and mitigations.**

- *The module becomes a covert payload store.* This is the exact risk ADR 009 lists
  for snapshots. Mitigated structurally: no block has a free-text or body field,
  every leaf is a slug/id/hash with a length cap, `_safe()` rejects undeclared keys
  and credential-shaped values before hashing, and a test asserts that no field
  accepts a string longer than its cap.
- *A second hashing or undecided convention creeps in.* Mitigated by importing
  `hash_bytes` / `canonical_json` from `context_snapshot` and `UNDECIDED_CODES` from
  `policy_checkpoint`, plus a test that fails if the evidence module defines its own
  `sha256`, its own `json.dumps` call, or a literal undecided-code list.
- *Prefix drift between the evidence module and the owning stores.* Mitigated by
  importing each prefix from its owner where possible, and by a test asserting
  equality with `work_context.snapshots.EXECUTION_ID_PREFIX`,
  `work_context.snapshots.SNAPSHOT_ID_PREFIX`,
  `work_context.execution_requests.REQUEST_ID_PREFIX` and
  `action_approvals.ID_PREFIX`.
- *An envelope is sealed `COMPLETE` while evidence is missing.* Mitigated by
  `completeness` being a derived property (not constructible), by `seal()` raising
  when a required block is absent and ungapped, and by `_safe()` emitting a
  `redacted_out` gap for every value it drops.
- *Tier B later disagrees with this schema.* Mitigated by the `v1alpha1`
  `api_version` and `SUPPORTED_API_VERSIONS` map, which is the repo's established
  way to evolve a contract, and by ADR 018 recording the boundary explicitly.
- *Someone continues #483 anyway.* Mitigated by ADR 018 naming it superseded and by
  the non-goals being restated in the module docstring, which is where the next
  implementer will actually look.
