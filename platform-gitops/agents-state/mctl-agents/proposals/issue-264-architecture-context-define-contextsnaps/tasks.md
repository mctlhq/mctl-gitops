# Tasks: issue-264-architecture-context-define-contextsnaps

- [ ] 1. Write `docs/adr/009-context-snapshot-contract.md` following the
      house shape of `docs/adr/007-agent-definition-execution-profile-contract.md`
      (H1 `# ADR 009 — ContextSnapshot contract and execution correlation`,
      blockquote metadata `> **Status:** / **Date:** / **Supersedes:**`,
      then Context / Decision with numbered subsections / Alternatives /
      Non-goals / Platform impact / Implementation map) — DoD: the file exists,
      its Context cites the real gap (`docs/agent-inventory.yaml:40-66`
      `runtimeContextInputs`, `orchestrator/run_issue_investigator.py:856,888`,
      `orchestrator/run_incident_responder.py:114-116`,
      `orchestrator/temporal/activities/state.py:36-41`), and every existing
      symbol it names resolves in the clone or is explicitly marked "new".
- [ ] 2. In the ADR, specify the canonical `ContextSnapshot` shape under
      `apiVersion: context.mctl.ai/v1alpha1`, `kind: ContextSnapshot`, with the
      field table for `ContextSnapshot`, `ExecutionCorrelation`, `StepRef`,
      `ContextStrategy`, `ContextBudget`, `ContextSource`, `EvidenceRef` and
      `RetentionPolicy` exactly as in design.md (depends on 1) — DoD: a reader
      can write a conforming document from the ADR alone; every field has an
      owner and a one-line meaning; no field can hold a source payload.
- [ ] 3. In the ADR, define identity and immutability: `content_hash` =
      `"sha256:" + sha256(canonical JSON of all fields except content_hash,
      snapshot_id, created_at)`, `snapshot_id = "cs-" + content_hash[7:23]`,
      seal-once/no-mutation, and the rule that every hash in the schema carries
      the `sha256:` prefix (naming, as a known inconsistency it does not
      inherit, the bare-hex `skill_hashes` at `orchestrator/resolver.py:894`)
      (depends on 2) — DoD: two independent implementers reading only the ADR
      would produce the same hash for the same document.
- [ ] 4. In the ADR, define lifecycle and granularity: assembled -> sealed ->
      referenced -> expired; per-execution root snapshots and per-step children
      via `StepRef{parent_snapshot_id, step, sequence}` with an identical
      `execution` block; mapped onto DevLoop's investigate/implement/
      review-fix steps (`orchestrator/temporal/workflows/dev_loop.py:534-539,
      596-683, 991`) (depends on 2) — DoD: the ADR answers the issue's
      "per execution, per step, or both" question in one unambiguous sentence
      plus the parent/version reference rule.
- [ ] 5. In the ADR, write the boundary section as a normative table:
      `ExecutionProfile`/#242 owns capability eligibility, #197 owns
      authorization, #199 owns evidence, #195 owns traces — and state the
      non-negotiable sentence that context relevance is never an authorization
      mechanism, echoing ADR 007's `tools`-is-not-authorization rule
      (`docs/adr/007-...:106-110`) (depends on 2) — DoD: the table names, for
      each neighbour, what the snapshot may record and what it must never do;
      each row maps to a test in task 10.
- [ ] 6. In the ADR, define the vocabularies and their defaults: budget in
      sources/bytes with `truncated`, explicitly NOT the model context window
      and with token budgets deferred plus written rationale; freshness
      `fresh|aging|stale|unknown` defaulting to `unknown`; trust
      `authoritative|corroborated|reported|untrusted` as origin-descriptive
      only, with the GitHub issue body as the worked `untrusted` case
      (`orchestrator/run_issue_investigator.py:1086,1136`) (depends on 2) —
      DoD: each vocabulary is closed, each term has a one-line definition and a
      real example drawn from this repo's agents.
- [ ] 7. In the ADR, write the sensitive-data / telemetry / retention rules:
      hash-after-redaction, no payloads anywhere, `retention.class` of
      `telemetry | execution-record | gitops` mapped onto ADR 007's
      source-of-truth table (`docs/adr/007-...:215-224`), the bounded-length
      rule for `locator`/`selector`, and the explicit statement that no
      redaction helper exists in the repo today so `redaction` is a contract
      for future code, not a claim about current behaviour (depends on 2) —
      DoD: a reviewer can point at the rule that forbids a Loki line, an issue
      body or a token from ever reaching a snapshot, a trace or the gitops repo.
- [ ] 8. Implement `orchestrator/context_snapshot.py`: the frozen dataclasses
      from task 2, `ContextSnapshotError(ValueError)`, `seal()`,
      `to_dict()`/`from_dict()` (JSON primitives only, unknown keys rejected),
      `validate()` and a `to_log_dict()`-style export for traces — stdlib only,
      no third-party imports, in the style of `orchestrator/resolver.py:226-291`
      and `orchestrator/temporal/issue_ref.py` (deliberately dependency-free so
      both the worker and the agent container can import it) (depends on 2, 3)
      — DoD: `uv run ruff check orchestrator` and `uv run mypy` pass; the module
      contains no I/O, no retrieval, no ranking and no network call.
- [ ] 9. Add `tests/fixtures/context/investigator-snapshot.json`: one sealed
      investigator snapshot on `dev-loop-mctlhq-mctl-agents-264` with a
      GitHub-issue source (`untrusted`/`fresh`), a `target-repo` source pinned
      by `target_repository_sha` with `selector.mode: agent-directed`
      (`authoritative`), a `loki-logs` source `{"lines": 50, "since": "1h"}`
      mirroring `orchestrator/run_incident_responder.py:116` (`corroborated`),
      an `incident` source (`corroborated`/`aging`), one `included: false`
      candidate with `reason_code: budget-exhausted`, one `evidence_ref`, and a
      filled `budget` block (depends on 8) — DoD: the fixture loads through
      `from_dict`, re-seals to the `content_hash` recorded in the file, and
      contains no free-text payload field.
- [ ] 10. Add `tests/test_context_snapshot.py` covering T1-T8 below, with the
      `# T<n> —` section-banner convention of `tests/test_resolver.py:217-246`
      and the T-list cross-referenced from this file (depends on 8, 9) —
      DoD: `uv run pytest tests/test_context_snapshot.py -q` is green and every
      acceptance criterion in requirements.md maps to at least one T-number.
- [ ] 11. Cross-link the new ADR: a pointer from
      `docs/adr/007-agent-definition-execution-profile-contract.md` (its
      non-goals list at line 341 already names #195/#197/#199 — add #196/#264
      context alongside), and a header note in `docs/agent-inventory.yaml`
      beside the `runtimeContextInputs` explanation (lines 40-66) saying where
      the per-run context contract now lives (depends on 1) — DoD: one-line
      pointers at both ends, no content duplicated, and
      `uv run pytest tests/test_agent_inventory.py -q` still green.
- [ ] 12. Record the follow-ups the ADR deliberately does not do, as a
      sequencing subsection: (a) a producer that emits a snapshot from
      `run_issue_investigator.py`, (b) persisting snapshots next to
      `ExecutionRecord` in mctl-api, (c) a redaction helper, (d) emitting
      snapshot attributes into #195 traces, (e) per-file enumeration of
      agent-directed reads (depends on 1, 5) — DoD: each follow-up names its
      owning issue or states "needs an issue", and none of them is a
      prerequisite for merging this proposal.

## Tests

- [ ] T1. Round-trip: `from_dict(to_dict(snapshot)) == snapshot` for the
      investigator fixture and for a minimal snapshot with no sources.
- [ ] T2. Hash determinism: sealing the same inputs twice with different
      `created_at` values yields the same `content_hash` and `snapshot_id`;
      changing any non-timestamp field changes both.
- [ ] T3. Golden stability: the checked-in fixture's recorded `content_hash`
      equals a freshly computed one, so a canonicalization change cannot pass
      silently.
- [ ] T4. Fail-loud versioning: an unknown `api_version` or `kind` raises
      `ContextSnapshotError`, and an unknown key in any nested object is
      rejected rather than ignored — mirroring
      `orchestrator/manifest.py:135-143` and closing the silent-discard hole
      `spec.runtimeContext` has today.
- [ ] T5. No-authorization invariant: the recursive field-name set of the
      serialized schema contains no `allow`/`deny`/`permit`/`grant`/
      `authorized` token; and a subprocess import of
      `orchestrator.context_snapshot` loads stdlib only (style of
      `tests/test_worker_isolation.py`).
- [ ] T6. Boundary invariants: `evidence_refs` entries accept only
      `{evidence_id, kind}`; the trace-export helper emits ids, hashes,
      versions and counts but never a `selector`, `locator` or any string
      sourced from a retrieved payload.
- [ ] T7. Vocabulary closure: `freshness.staleness`, `trust.tier`,
      `source.kind` and `retention.class` reject any value outside their
      documented sets, and an omitted `max_age_seconds` yields `unknown`
      rather than `fresh`.
- [ ] T8. Step chaining: a child snapshot whose `execution` block differs from
      its parent's is rejected; `sequence` must be strictly increasing within
      one parent; a root snapshot with a `parent_snapshot_id` is rejected.
- [ ] T9. Budget semantics: `used_sources`/`used_bytes` exceeding their maxima
      without `truncated: true` is rejected; the schema exposes no token or
      context-window field (guards against the deferred decision quietly
      reappearing).

## Rollback

Everything in this proposal is additive and inert. `docs/adr/009-*.md`,
`orchestrator/context_snapshot.py`, `tests/fixtures/context/` and
`tests/test_context_snapshot.py` are new files that no production code path
imports: no agent, workflow, activity, manifest or options builder changes, and
`orchestrator/resolver.py` is untouched, so `ISSUE_INVESTIGATOR_RESOLVER_MODE`
behaviour in both `legacy` and `declarative` mode is unchanged.

Partial rollback: delete `orchestrator/context_snapshot.py`, the fixture and
the test file, keeping the ADR as a documented decision. Full rollback: revert
the single PR, which also removes the two cross-link lines added in task 11 —
after which `uv run pytest`, `uv run ruff check orchestrator config tests tools`
and `uv run mypy` return to exactly their pre-PR state. There is no data, no
migration and no deployed artifact to undo.
