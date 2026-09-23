# Tasks: issue-199-feat-governance-auditable-execution-evid

- [ ] 1. Write `docs/adr/015-execution-evidence-contract.md` — the schema,
      `evidence.mctl.ai/v1alpha1`, the `ev-` id derivation, the redaction and
      retention rules, the completeness gap vocabulary, the export bytes, and
      the two normative boundary rows mirroring ADR 009 sec. 5 and ADR 011
      sec. 6. — DoD: ADR merged in `proposed` status, numbered 015 (014 is the
      policy checkpoint), linking #195/#196/#197/#198/#60 and naming what it
      does not decide (trace backend, usage ledger, mctl-api store).

- [ ] 2. Add `orchestrator/execution_evidence.py` with the frozen dataclasses
      `ExecutionBlock`, `IdentityBlock`, `ModelUse`, `ActionRecord`,
      `ApprovalRecordRef`, `ArtifactRecord`, `Evaluation`, `Completeness`,
      `Gap`, `Outcome`, `Retention`, `ExecutionEvidence`, each with
      `to_dict`/`from_dict` and unknown-key rejection (depends on 1) — DoD:
      stdlib-only module, imports only `orchestrator.context_snapshot`'s
      `canonical_json`/`hash_bytes`, `mypy` and `ruff` clean, no import of
      `tracing`, `httpx` or the SDK.

- [ ] 3. Implement `seal()` and `recompute_content_hash()` in that module
      (depends on 2) — DoD: `content_hash` is `"sha256:" + hex` over canonical
      JSON of every field except `content_hash`, `evidence_id` and
      `created_at`; `evidence_id == "ev-" + content_hash[7:23]`; sealing the
      same inputs twice at different clock times yields the same id.

- [ ] 4. Implement the `_safe()` redaction guard and the `target_ref` /
      `target_digest` split (depends on 2) — DoD: strings over 256 chars and
      credential shapes (`ghp_`, `ghs_`, `github_pat_`, `sk-`, `hv*.`, JWT,
      PEM, `Bearer `, `user:pass@`) are dropped, never masked or truncated; a
      target outside the closed allowlist is stored only as a digest.

- [ ] 5. Implement `EvidenceRecorder` with an optional module-level sink and
      the offer methods `offer_decision`, `offer_artifact`, `offer_model_turn`,
      `offer_approval`, `finish` (depends on 3, 4) — DoD: every method is total
      and never raises; with no sink installed every offer is a no-op costing
      one attribute read.

- [ ] 6. Implement `check_completeness()` and the built-in `policy_compliance`
      / `evidence_completeness` evaluations (depends on 5) — DoD: the five gap
      codes of design.md are produced; `ungoverned_transport` is standing for
      any run whose builder grants `Bash`; `policy_compliance` is `PASS` only
      when every mutation links to a permitted decision and there are no gaps.

- [ ] 7. Wire the recorder into `orchestrator/policy_checkpoint.py:_emit`,
      next to the existing `tracing.record_policy_decision` call (depends on 5)
      — DoD: one added call guarded by the optional sink; `policy_checkpoint`
      stays stdlib-only and never-raises; `tests/test_policy_checkpoint.py` and
      `tests/test_github_mutations_policy.py` unchanged and green.

- [ ] 8. Wire artifact recording: extend
      `run_issue_investigator._trace_published` to also offer each proposal
      file with its `sha256:` content hash, byte count and gitops locator, and
      add the implementer/shepherd artifacts (branch, PR, merge commit) at
      their existing `gh`/`git` call sites (depends on 5) — DoD: an investigate
      run records four artifacts with hashes; an implement run records the
      branch and PR; a merge records the merge commit SHA.

- [ ] 9. Wire model usage: have `tracing.AgentRunObserver` offer
      `(provider, model, input_tokens, output_tokens)` per completed turn to
      the recorder, reading no field it does not already read (depends on 5) —
      DoD: `models` is keyed by `(provider, model)` with summed counters;
      `usage_record_ref` stays empty and is documented as ADR 012's slot; no
      new field is read from `AssistantMessage` or `ResultMessage`.

- [ ] 10. Wire identity and outcome: populate `ExecutionBlock`/`IdentityBlock`
      from `execution_identity.load_from_environment()`, and `Outcome` from the
      run's own result in `run_issue_investigator`, `run_implementer` and
      `run_shepherd` (depends on 5) — DoD: with a control-plane context the
      blocks are fully populated and `context_trust` is `control-plane`;
      without one the record still seals with `context_trust: unverified` and
      an `identity_unavailable` gap.

- [ ] 11. Add `orchestrator/evidence_store.py`: write the sealed document to
      `platform-gitops/agents-state/_evidence/<workflow_type>/<workflow_id>/<attempt>-<evidence_id>.json`
      plus the `by-trace/<trace_id>/<evidence_id>` pointer, and read it back by
      workflow id, trace id or evidence id (depends on 3) — DoD: paths are
      deterministic and collision-free; a re-seal of identical inputs
      overwrites nothing new; reads return newest attempt first.

- [ ] 12. Add the CLI `python -m orchestrator.evidence_store show
      --workflow-id | --trace-id | --evidence-id` printing canonical JSON
      (depends on 11) — DoD: the printed bytes re-hash to the document's
      `content_hash`; an unverifiable document is reported as untrusted rather
      than printed as evidence.

- [ ] 13. Emit one `EXECUTION_EVIDENCE <json>` summary line at run end
      following the `POLICY_DECISION` / `lifecycle/claim.py:_emit` convention
      (depends on 6) — DoD: the line carries ids, counts, completeness status
      and outcome only, no target and no digest of arguments; it is one line
      and greppable in an Argo log.

- [ ] 14. Wrap sealing, persistence and emission in the never-raises envelope
      and add the `evidence_ids` pointer list to `.status.yaml` via
      `proposal_state.update_status_file` (depends on 11, 13) — DoD: any
      injected failure logs once as `warn: evidence ...` and leaves the run's
      result and exit code unchanged; old `.status.yaml` files still load.

- [ ] 15. Document the contract in `docs/observability/execution-evidence.md`
      alongside `execution-traces.md`, including the retention/redaction rules
      and the Tier B mctl-api follow-up (depends on 1, 11) — DoD: page merged
      and cross-linked from `execution-traces.md`; the follow-up issue for the
      mctl-api evidence store is opened and referenced.

## Tests

- [ ] T1. `tests/test_execution_evidence.py::test_seal_is_deterministic` — the
      same inputs sealed at two different `created_at` values give the same
      `content_hash` and `evidence_id`; `recompute_content_hash` agrees.
- [ ] T2. `from_dict` rejects an undeclared key and an unsupported
      `api_version`, matching `execution_identity`'s behaviour.
- [ ] T3. Redaction: a record assembled from inputs carrying a `ghp_` token, a
      JWT, a 4 KB issue body and a long argv contains none of them; assert by
      recursive scan of the sealed dict, not by field name.
- [ ] T4. A mutation artifact with no matching `ActionRecord` yields
      `completeness.status == INCOMPLETE` with `mutation_without_decision`, and
      `policy_compliance == FAIL`.
- [ ] T5. A `REQUIRE_APPROVAL` action permitted with `code: approved` links to
      its `aar_` receipt, approver and `consumed_at`; an unresolvable receipt
      yields `approval_unresolved` and still seals.
- [ ] T6. Every undecided code (`evaluator_error`, `identity_unavailable`,
      `approval_lookup_error`) is recorded with `undecided=True` and does not
      set `outcome.status = REFUSED`.
- [ ] T7. A builder granting `Bash` always carries the standing
      `ungoverned_transport` gap, so `COMPLETE` is unreachable for it.
- [ ] T8. Failure isolation: a raising sink at each of the five offer points,
      and a store that cannot write, leave the investigate/implement result and
      exit code byte-identical to the unwired run.
- [ ] T9. `evidence_store` round trip: seal, write, retrieve by workflow id,
      trace id and evidence id; the exported bytes re-hash to `content_hash`.
- [ ] T10. Existing suites stay green with no edits:
      `tests/test_policy_checkpoint.py`, `tests/test_github_mutations_policy.py`,
      `tests/test_execution_identity.py`, `tests/test_context_snapshot.py`,
      `tests/test_tracing.py`, `tests/test_tracing_agents.py`,
      `tests/test_run_issue_investigator.py`.
- [ ] T11. `uv run ruff check orchestrator config tests` and `uv run mypy` pass.

## Rollback

The slice is additive and sink-gated, so rollback has three levels.

1. **Unwire.** Leave the sink uninstalled in the run entrypoints (tasks 7-10
   each add one guarded call). Every offer becomes a no-op, nothing is sealed
   or written, and the checkpoint, tracing, identity and proposal paths behave
   exactly as before. No config or gitops change is needed.
2. **Revert the PR.** `orchestrator/execution_evidence.py`,
   `orchestrator/evidence_store.py`, `docs/adr/015-*`,
   `docs/observability/execution-evidence.md` and
   `tests/test_execution_evidence.py` are new files; the edits to
   `policy_checkpoint.py`, `tracing.py`, `run_issue_investigator.py`,
   `run_implementer.py`, `run_shepherd.py` and `proposal_state.py` are each a
   small guarded addition. No dependency is added, so no `uv.lock` change has
   to be undone.
3. **Data.** Written evidence lives only under
   `platform-gitops/agents-state/_evidence/` and the optional `evidence_ids`
   key in `.status.yaml`. Deleting that directory removes every record; no
   other reader depends on it, and `proposal_state.load_status` ignores the
   extra key either way. Nothing mctl-api holds is touched, because Tier B is
   not in this slice.
