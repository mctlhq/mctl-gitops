# Spike: evaluate an OpenSpec-compatible artifact contract for MCTL DevLoop proposals

## Context

Issue mctlhq/mctl-agents#655 asks for a bounded, reversible spike. The question is whether MCTL should
stop owning a custom planning format (`requirements.md` + `design.md` + `tasks.md`) and adopt an
OpenSpec-compatible artifact layer, while DevLoop keeps owning execution. Today the investigator
(`orchestrator/run_issue_investigator.py`, `TRIPLET = ("requirements.md", "design.md", "tasks.md")`)
writes the triplet plus `.status.yaml`. The implementer (`orchestrator/run_implementer.py`) reads
the triplet from `$PROPOSAL_DIR`. The shepherd (`orchestrator/run_shepherd.py::decide`) merges on
review and CI state. Approval and authorization are read from `.status.yaml`
(`orchestrator/proposal_state.py::human_approval_satisfied`, `execution_authorization`). Planning
intent and execution state already live side by side in one directory. They are different things,
but nothing in the format says so.

The compatibility target is pinned to OpenSpec **v1.14.2**, commit **`f80d860`**
(`f80d860fc510ba4f51180c8ddde35b91b32de657`, `@fission-ai/openspec` 1.14.2). This applies to every
OpenSpec fact the spike relies on. The spike must use only the facts pinned in the issue, plus
anything it verifies itself against that exact commit. A fact it needs that is neither pinned nor
verified forbids an `ADOPT_CONTRACT` claim. The spike produces evidence and exactly one
recommendation: `ADOPT_CONTRACT`, `ADAPTER_ONLY` or `NO_GO`. It must not change a production code
path, the deployed workers, or any existing proposal directory.

## User stories

- AS a platform maintainer I WANT a written, evidence-backed mapping from the MCTL proposal triplet to an OpenSpec v1.14.2-compatible change package SO THAT I can decide whether to adopt it, adapt to it, or drop it.
- AS a DevLoop operator I WANT `.status.yaml`, approval, authorization, Temporal state and execution identity to stay outside any spec artifact SO THAT format compatibility can never forge or weaken an approval.
- AS an implementer-agent owner I WANT proof that an OpenSpec-style change carries every piece of implementation-relevant information that `requirements.md` / `design.md` / `tasks.md` carry today SO THAT switching formats cannot silently drop scope.
- AS a shepherd owner I WANT spec verification defined as one more blocking-only input next to CI and P1/P2 review SO THAT it never becomes a second merge authority.
- AS a contributor filing a typo or dependency-bump issue I WANT a light change class SO THAT I do not pay for full spec ceremony, and no second lifecycle is created.

## Acceptance criteria (EARS)

Contract and mapping
- WHEN the spike completes THE SYSTEM SHALL provide an artifact mapping table with one row per current MCTL artifact or section. The table covers `requirements.md` Context / User stories / Acceptance criteria / Out of scope / Open questions, `design.md` Current state / Proposed solution / Alternatives / Platform impact, `tasks.md` tasks / Tests / Rollback, and the `.status.yaml` `source` block. Each row names its target in the candidate package (`proposal.md`, `specs/<capability>/spec.md`, `design.md`, `tasks.md`, `.openspec.yaml`) or marks it "stays MCTL execution state".
- WHEN `.openspec.yaml` is mapped THE SYSTEM SHALL list, field by field: the known keys used (`schema`, `created`, `goal`, `affected_areas`, and `initiative`/`skip_specs`/`retire_capabilities` where applicable); the `x-mctl-*` extension keys used for MCTL linkage (at least the source issue URL, service and slug); and the `.status.yaml` fields that must never appear in it (`status`, `approval`, `control`, `execution`, `attempt`, `pr`, `github`, `merged_at`, `merge_commit`, `context`, `request`).
- THE SYSTEM SHALL ship fixtures and tests for `.openspec.yaml` covering:
  - a valid file that passes;
  - an unknown top-level key that warns in normal mode and fails in strict mode;
  - an `x-` top-level key that passes strict mode;
  - an `x-` key inside `initiative` that is rejected;
  - a missing file, treated as "no metadata", not an error;
  - `skip_specs: true` while `specs/` has files, which is an error.
- IF a `.openspec.yaml` field would carry execution state (any key in the forbidden list above) THEN THE SYSTEM SHALL reject the artifact with a validation error naming that key.

Canonical spec and delta semantics
- WHEN the prototype applies a change delta to a canonical capability spec THE SYSTEM SHALL use the pinned archive order RENAMED -> REMOVED -> MODIFIED -> ADDED and pre-validate cross-section conflicts. Conflicts are a RENAMED FROM that is also REMOVED, and a RENAMED TO that collides with an ADDED.
- THE SYSTEM SHALL provide a row-by-row comparison table, each row with a fixture-backed test, against the pinned archive/sync rules:
  - RENAMED: source missing but target present is a no-op; both missing aborts.
  - REMOVED: target missing warns and is a no-op; a case/whitespace near-miss aborts.
  - MODIFIED: target missing aborts; identical after normalization is a no-op; dropping existing scenarios aborts.
  - ADDED: identical is a no-op; different content aborts; a near-miss aborts.
  - New capability: only ADDED is allowed; MODIFIED/RENAMED abort; REMOVED is skipped with a warning.
  - Duplicate requirement headers in the main spec are rejected before any delta is applied.
  - Idempotency is per requirement, not per change. Re-archiving fails because the target exists.
  - Sync treats an ADDED requirement whose name already exists as an implicit MODIFIED; archive aborts in that case.
  Each row records the MCTL choice (mirror archive, mirror sync, or MCTL-specific) and the reason.
- WHEN a delta is applied for a simulated merge THE SYSTEM SHALL show the canonical spec before the change, the delta, and the resulting canonical spec after archive. This is shown for at least one bounded DevLoop capability (the DevLoop approval gate), with at least one ADDED, one MODIFIED and one REMOVED requirement.
- IF any delta operation aborts THEN THE SYSTEM SHALL leave the canonical spec byte-identical and SHALL NOT move the change to archive.

Round-trip of an existing proposal
- WHEN an existing merged proposal (at least `mctl-agents/proposals/issue-596-test-agent-platform-add-an-inert-authori`) is converted THE SYSTEM SHALL produce an OpenSpec-compatible package. It SHALL also produce a loss report that lists every implementation-relevant item from `requirements.md`, `design.md`, `tasks.md` and the `source` linkage, with its location in the new package.
- WHEN the converted package is converted back THE SYSTEM SHALL either reproduce the original triplet's sections and items in a stable way (round-trip), or document a one-way migration with an explicit reason.
- THE SYSTEM SHALL record artifact size in bytes and an approximate token count for the current and candidate representations of each converted proposal, and state the token-estimation method.

Agent boundaries and Shepherd
- WHEN the Investigator -> artifact -> Implementer boundary is simulated THE SYSTEM SHALL record, for at least one issue, whether the candidate contract improves, preserves or worsens each of: requirement clarity, task completeness, context size, ambiguity, implementation success, and identification of the changed capability.
- THE SYSTEM SHALL define spec verification as a blocking-only signal. It is combined with CI required checks and P1/P2 review findings before the Shepherd decision. Its result vocabulary is limited to pass / fail / unknown, and it has no way to merge, approve or authorize.
- IF a proposed design lets spec verification (OpenSpec `verify` or an equivalent) replace Shepherd, CI, review policy, approval or MCTL authorization THEN THE SYSTEM SHALL reject that design explicitly in the decision record.

Invariants
- WHILE the spike is in progress THE SYSTEM SHALL keep `DevLoopWorkflow`, `run_issue_investigator.py`, `run_implementer.py`, `run_shepherd.py`, `proposal_state.py` and every live `agents-state/**/proposals/**` directory behaviorally unchanged.
- WHILE the prototype runs THE SYSTEM SHALL NOT require the OpenSpec CLI, Node.js or any `@fission-ai/openspec` package at runtime. Any optional check against the real CLI is dev-only and reported separately.
- THE SYSTEM SHALL keep a single canonical source of requirements in any recommended end state. Permanent dual-authoring of `requirements.md` and `specs/**` is not an acceptable outcome.
- THE SYSTEM SHALL cite OpenSpec `v1.14.2` / `f80d860` as the compatibility target in the decision record and in the prototype module docstring.

Change classes and decision
- WHEN change classes are evaluated THE SYSTEM SHALL define `trivial`, `normal` and `governed` as planning-artifact shapes inside the one existing DevLoop lifecycle. `trivial` uses `skip_specs: true` with no `specs/`. A class SHALL NOT change `control.requires_human_approval`, approval provenance, or authorization.
- WHEN a custom `mctl-devloop` workflow schema is evaluated THE SYSTEM SHALL score it against the same decision criteria as built-in `spec-driven` and adapter-only. The evaluation SHALL account for the pinned constraint that archive/validate read deltas only from `specs/**/spec.md`, and for the experimental status of schema commands at v1.14.2.
- WHEN the spike ends THE SYSTEM SHALL record exactly one recommendation (`ADOPT_CONTRACT`, `ADAPTER_ONLY` or `NO_GO`), the evidence for it, a migration/interop cost estimate for existing proposals, and follow-up issue drafts. If the recommendation is `ADOPT_CONTRACT`, the record SHALL also include a staged migration plan.
- IF a fact needed for compatibility (for example the exact markdown grammar of requirement and scenario headers) is neither in the pinned reference nor verified against `f80d860` THEN THE SYSTEM SHALL name that fact as unverified and SHALL NOT recommend `ADOPT_CONTRACT`.

## Out of scope

- Replacing `DevLoopWorkflow`, Temporal, MCTL approval/authorization, or the Shepherd.
- Changing the investigator prompt, the implementer prompt, `.status.yaml` writers, or the deployed workers (`mctl-agents-worker*`).
- Migrating or rewriting any existing proposal in `mctl-gitops` (conversion runs on read-only copies or fixtures only).
- A public `mctl spec ...` CLI or mctl-api endpoints. Only library functions and tests are built.
- A runtime dependency on the OpenSpec CLI, Node.js or its source code.
- A universal adapter for other SDD formats (Spec Kit, Kiro).
- Binding approval to a content digest of the planning artifacts. Today `.status.yaml` `approval` records only `approved_by`/`approved_at`. The spike notes this gap and drafts a follow-up, but does not fix it.

## Open questions

- The pinned reference does not state the markdown grammar of a spec file: requirement header text, scenario header text, the delta section headings (`## ADDED Requirements` etc.), whether SHALL/MUST is required, or the `proposal.md` section names. The spike assumes the commonly used `### Requirement:` / `#### Scenario:` form, marks it unverified, and may verify it against `f80d860` only if source access is available to the implementer. Until it is verified, `ADOPT_CONTRACT` is excluded.
- Whether the real OpenSpec CLI v1.14.2 may be run as an optional, dev-only cross-check (needs Node and network in CI). Proposed default: not run. The prototype's validator is tested against the pinned rules only.
- The issue says "posted" for the recommendation. The proposed default is a committed decision record (`docs/spikes/655-openspec-contract.md`) plus a summary in the PR body. Posting a comment on the issue is left to the reviewer.
- What the "implementation success" measurement means when no real implementer run is allowed. Proposed default: a simulated consumption check (every task and acceptance criterion is reachable from the converted package), with a real implementer run on one fixture recorded as optional.
- Which capability is first for canonical specs. Proposed default: the DevLoop approval gate, because its behavior is pinned in `proposal_state.py` and `dev_loop.py`.
