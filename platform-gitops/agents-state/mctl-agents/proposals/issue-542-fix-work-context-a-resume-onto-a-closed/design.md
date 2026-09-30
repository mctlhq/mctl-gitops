# Design: issue-542-fix-work-context-a-resume-onto-a-closed

## Current state

**The guard that causes the bug.** `orchestrator/run_issue_investigator.py` defines

```python
_OVERWRITABLE_STATUSES = {"proposed"}
```

and `_investigate` applies it immediately after resolving the slug:

```python
existing = _load_status(status_path)
existing_status = existing.get("status")
if existing and existing_status not in _OVERWRITABLE_STATUSES:
    reason = (f"proposal {service}/{slug} already at status "
              f"'{existing_status}' — refusing to overwrite in-flight work")
    print(f"warn: {reason}")
    return InvestigateResult(service, slug, proposal_dir, skipped_reason=reason)
```

This runs **before** the work-context block (`if work_item_id:` …), before
`_clone_repo`, and therefore before `_assemble_context`. The module docstring calls it
"step 4"; the clone is step 5 and assembly is step 2b inside the `try` at step 1/2.

**Where a snapshot would have been sealed.** `_assemble_context` is called from inside
the `try` block, after `_clone_repo` and after `_staging_dir`:

```python
context = _assemble_context(
    mode=_context_mode(), issue=issue, repo_dir=clone / "repo",
    proposal_dir=proposal_dir, service=service, slug=slug,
    work_context=work_context_ref, temporal_workflow_id=..., ...)
```

It delegates to `orchestrator/context_assembly.py::assemble_investigator_context`, which
needs `repo_dir` and `target_repo_sha` (`_target_repository_sha` runs `git rev-parse HEAD`
in the clone), and which persists the sealed snapshot to mctl-api via
`orchestrator/work_context/snapshots.py::persist` when the work context names a store
execution (`is_store_execution`, `we_` prefix). The three context modes are
`("off", "shadow", "on")`; `shadow` is documented in this file as "assembles/seals/logs/
correlates a snapshot but leaves the prompt untouched".

**Provenance.** `_work_context_ref` / `_prior_execution_ids` build the `WorkContextRef`
that is sealed into the snapshot: `work_item_id`, the store `execution_id`,
`execution_sequence`, `prior_execution_ids` (ledger entries below this execution's
sequence, plus a `resume_from_execution_id` the store has not recorded), and
`snapshots.resumed_from` links `resumed_from_snapshot_id`. This is exactly the data
#431's acceptance items 3, 4 and 7 want to see in C2 — and none of it is produced today
when the guard fires.

**How E2 ended `Succeeded`.** Two different actors can advance the execution:

- `_OwnExecution.finish` in `run_issue_investigator.py` — but only when *this run*
  attached its own engine run. On a dispatched resume the `we_` comes from the work-item
  layer, `resolve_identity` returns `attached=None`, `hold()` is never called, and
  `finish()` returns immediately (`if self.run is None: return`).
- `DevLoopWorkflow.run` in `orchestrator/temporal/workflows/dev_loop.py`:
  ```python
  advance_phase = "Succeeded" if investigate_result.succeeded else "Failed"
  ```
  keyed purely on the Argo workflow's phase. `main()` in the investigator returns without
  `sys.exit(1)` on a skip (`print(f"  skip ...")` then `return`), so the CWFT succeeds and
  E2 becomes `Succeeded`.

Note the latent inconsistency this exposes: for a **self-attached** run
`_OwnExecution.finish` computes `succeeded = result.error is None and
result.skipped_reason is None`, so the same skip would have ended the execution `Failed`.
Two paths, two answers, for one condition.

**Vocabulary that already exists and must not be reinvented.**

- `orchestrator/work_context/executions.py`: `PHASE_RUNNING`, `PHASE_SUCCEEDED`,
  `PHASE_FAILED` — mctl-api's closed set. There is no "did nothing" phase.
- `orchestrator/work_context/execution_requests.py`: `RESUME_REFUSED` plus the closed
  `RESUME_REFUSAL_REASONS`. These are minted *before* a `we_` exists, by the dispatcher
  (`orchestrator/temporal/dispatcher.py`, `f"{xr.RESUME_REFUSED}:{answer.reason}"`) or by
  `DevLoopWorkflow._validate_execution_request`. By the time the investigator runs, the
  request is already fulfilled — so this is structurally the wrong layer for a
  `proposal_terminal` refusal.
- `orchestrator/execution_evidence.py` (ADR 018):
  `OUTCOME_CODES = {"succeeded", "failed", "refused", "abandoned", "superseded"}` with a
  `reason_code` slug validated against `_SLUG_PATTERN` / `MAX_SLUG_LENGTH`. This is the
  platform's existing answer to "name the outcome of a governed execution".
- `orchestrator/work_context/snapshots.py`: `SNAPSHOT_SKIPPED = "snapshot-skipped"` — "nothing
  was sent", a transport verdict, not an execution outcome.
- `orchestrator/run_issue_directive_poller.py` already names this exact condition
  `"not-overwritable"` in its own outcome vocabulary, importing `_OVERWRITABLE_STATUSES`
  from the investigator. Two spellings for one condition is a smell; the implementation
  should pick one (this design proposes `proposal-terminal`) and note the other.
- `dev_loop.py` already has `PROPOSAL_TERMINAL_PATCH = "proposal-terminal-end"`, an
  **unrelated** merge-watch patch marker. The new work must not reuse that name; the
  collision is textual only.

**One read-surface caveat.** `orchestrator/work_context/client.py`'s `ROUTES` contains only
a singular, per-execution `execution_snapshot` route
(`/api/v1/work-items/{id}/executions/{execution_id}/snapshot`). There is no plural
`/snapshots` list route anywhere in this repo, so the `/snapshots` listing the issue quotes
is an mctl-api-side surface. Nothing in this design depends on a client-side listing.

**The precedent.** `dev_loop.py` already refuses the exact shape of silence this issue
reports: `DISPATCHED_NOT_RUN_FAILS_PATCH = "dispatched-not-run-fails"` /
`DISPATCHED_NOT_RUN_ERROR_TYPE = "DispatchedRequestNotRun"`, described in ADR 011 §8 as
"a COMPLETED run that did nothing would make every later intake label on the issue a
silent 'already handled'".

**The contract this must honour.** `docs/adr/011-work-item-resume-contract.md` §8:
"the dispatcher starts a new run after ANY closed run (`ALLOW_DUPLICATE`), because a
`resume` of a finished loop is exactly a new run of it and a request is an explicit ask
that mctl-api already re-decided". And §Context, quoting `dev_loop.py`: "It is a restart,
not a resume — the new run re-investigates and waits for a fresh approve signal."

## Proposed solution

Adopt the issue's **option (a)**, scoped to dispatched resumes, and carry option (c)'s
*explicit-outcome* half everywhere the run declines to rewrite.

The guard today answers one question with one branch. Split it into two independent
decisions:

1. **May this run rewrite the proposal?** `rewrite_allowed = (not existing) or
   existing_status in _OVERWRITABLE_STATUSES`. Unchanged rule, unchanged blast radius.
2. **Should this run assemble and seal a context snapshot?** Yes whenever the run is a
   dispatched resume and a snapshot would actually be sealed.

### 1. A context-only path in `_investigate`

Add a predicate beside the existing helpers:

```python
def _is_dispatched_resume(*, resume_from_execution_id, execution_id, execution_request_id):
    """This run serves a work-item `resume` the dispatcher fulfilled."""
    from orchestrator.work_context.snapshots import is_store_execution
    if resume_from_execution_id:
        return True
    return bool(execution_request_id) and is_store_execution(execution_id)
```

Imported lazily, inside the function body, matching this module's import discipline
(`tests/test_worker_isolation.py`).

Restructure the guard:

- `rewrite_allowed` **true** → everything is exactly as today.
- `rewrite_allowed` **false** and not a dispatched resume → today's skip, but the returned
  `InvestigateResult` now carries `outcome_code="refused"`,
  `outcome_reason="proposal-terminal"`.
- `rewrite_allowed` **false**, a dispatched resume, and `_context_mode() == "off"` → the
  same skip with the same typed outcome: with assembly off there is nothing to seal, so
  cloning would buy nothing.
- `rewrite_allowed` **false**, a dispatched resume, `_context_mode() != "off"` → fall
  through into the work-context block and then into the `try`, in **context-only** mode.

The guard must move *below* the `if work_item_id:` work-context block for the fall-through
case only, because `work_context_ref` is what makes the seal meaningful. Keep the
non-resume skip where it is (before any store contact) so the ordinary path is untouched.

### 2. What the context-only path does and does not do

Inside the `try`, gate the steps on `rewrite_allowed`:

| step | context-only |
| --- | --- |
| 1 `_clone_repo` | runs — `_target_repository_sha` needs a HEAD |
| 2 `_staging_dir` / `_dir_identity` | skipped |
| 2b `_assemble_context` | **runs**, with `mode="shadow"` forced |
| 2c `_service_skills_prompt_block` | skipped |
| 2d/3 `_build_prompt` + `_run_agent` | skipped — no model call, no cost |
| 4–7 verify / `write_status_yaml` / `_carry_forward` / publish swap | skipped |
| 8 issue comment | skipped |
| `finally` clone cleanup | runs unchanged |

Forcing `shadow` is the load-bearing detail. `_assemble_context`'s docstring states the
rule: in `on` mode a failure propagates because "a sealed snapshot must never describe a
prompt that was not actually built". On this path **no prompt is built at all**, so `on`
semantics would be a lie. `shadow` is precisely defined as seal-and-correlate without
touching the prompt, so the context-only path reuses it rather than inventing a fourth
mode.

The failure policy is inverted relative to plain `shadow`, though: here the snapshot *is*
the deliverable. So the context-only call sets a flag that makes an assembly failure
fatal — `outcome_code="failed"`, `outcome_reason="context-assembly-failed"`, non-zero
exit — rather than a warning. A resume that could not seal C2 must not be reported as a
success; that is the same "could not observe is never observed absent" rule the issue
cites.

### 3. The typed outcome

`InvestigateResult` gains three defaulted fields, so every existing construction and every
existing caller compiles unchanged:

```python
outcome_code: str = "succeeded"   # from execution_evidence.OUTCOME_CODES
outcome_reason: str = ""          # execution_evidence slug rules
context_only: bool = False
```

`orchestrator/execution_evidence.py` is imported lazily in one small validator so the
codes and the slug pattern are checked against the single existing source rather than
duplicated. The reason slug for this condition is `proposal-terminal`.

`main()` prints one machine-readable line before its human summary:

```
[outcome] code=succeeded reason=proposal-terminal context_only=true \
          snapshot_id=cs_... execution_id=we_... work_item_id=wi_...
```

and exits 0 for a context-only run, non-zero for `outcome_code="failed"`.

`_OwnExecution.finish` changes its predicate from
`result.error is None and result.skipped_reason is None` to
`result is not None and result.error is None and result.outcome_code == "succeeded"`.
This removes the self-attached/dispatched inconsistency noted above: a context-only run
ends `Succeeded` on both paths, a refused one is no longer silently success-shaped.

`_trace_published` is unchanged — it already returns early when `skipped_reason` is set,
and a context-only run publishes nothing.

### 4. `DevLoopWorkflow`

`advance_phase` stays as it is: the phase vocabulary is mctl-api's and the run did succeed
at what it was permitted to do. What changes is what the loop does *next*. After a
context-only investigate there is no new proposal revision, so the loop must end rather
than enter the approval wait. The loop learns this from the proposal status it already
reads through its existing `find_proposal_slug` / gitops activities; if that read is not
available at that point in `run`, the fallback is a typed exit code the CWFT surfaces on
`WorkflowResult`. The new branch returns

```python
DevLoopResult(investigate=investigate_result, implement=None,
              ended="investigate context-only: proposal-terminal")
```

behind `workflow.patched("context-only-resume")`, named and placed alongside
`DISPATCHED_NOT_RUN_FAILS_PATCH`, so an in-flight history recorded before this change
replays with its old command sequence. The name deliberately avoids the existing,
unrelated `PROPOSAL_TERMINAL_PATCH = "proposal-terminal-end"` marker.

Note the loop's own delivery accounting is untouched: `_land_delivery` computes
`"Succeeded" if decided else "Failed"` from `(self._approved or self._gates_passed) and not
self._abandoned`, and a context-only run reaches no approval gate, so the delivery-side
advance must be reached by the new end branch rather than left to fall through the
abandon path. The implementation must confirm the delivery lands `Succeeded` once and only
once — `OpenDelivery.pending_phase` already retries an unlanded advance every ten minutes,
so a double-advance shows up as a divergence, not as a silent duplicate.

### 5. Why this satisfies #431

The sealed C2 is produced by the same `_work_context_ref` → `assemble_investigator_context`
→ `snapshots.persist` path a normal run uses, so it carries `work_item_id` (W1), this
run's `execution_id` (E2), `prior_execution_ids` containing E1, and
`resumed_from_snapshot_id` pointing at C1 — acceptance items 3, 4 and 7, provable live on
the very item (`wi_5c479148`) the issue used. The new intent that came with the resume
request is visible in C2 because the collectors re-read the issue and its comments
(`gh_issue_view` already fetches `comments`, which `context_assembly.collect_issue_comments`
consumes).

## Alternatives

**Option (b) — treat the resume as a new cycle with a fresh proposal revision behind the
normal approval gate.** Dropped. It is the largest change of the three: proposal identity
is a directory name resolved by `resolve_slug` / `proposal_identity.select_proposal_slug`,
which has no concept of a revision; `existing_slugs` keys on the issue number and
`AmbiguousProposalError` fires on two live directories for one issue. The implementer and
shepherd both read `.status.yaml` as the single authority for a slug, and #438's
`rejected` rule is already the one carve-out. Adding revisions touches all of that, and it
re-opens work that merged — the exact thing `_OVERWRITABLE_STATUSES` exists to prevent. It
is a defensible future direction, not this fix.

**Option (c) — refuse the resume up front with `resume_refused:proposal_terminal`.**
Dropped as the primary behaviour, for two reasons. First, it contradicts ADR 011 §8's
stated reuse policy: the dispatcher deliberately uses `ALLOW_DUPLICATE` rather than
`ALLOW_DUPLICATE_FAILED_ONLY` precisely so a resume of a *completed* loop is allowed,
"because a `resume` of a finished loop is exactly a new run of it". Refusing every item
whose proposal reached `merged` would make the resume surface unusable for the normal
end-state. Second, the refusal is structurally misplaced: `RESUME_REFUSED` is minted by
`dispatcher._reject` and `DevLoopWorkflow._validate_execution_request` **before** a `we_`
exists, and neither reads `.status.yaml` — a gitops file the Temporal worker would have to
fetch through an extra activity just to make this decision. Its good half — "a run that
skips should end with an explicit outcome" — is adopted in full above.

**Seal C2 unconditionally, for every skipping run including intake-label
re-investigations.** Dropped. It would add a shallow `gh repo clone` and a full collector
pass to a path whose entire purpose is to cost nothing, on every poller tick that
re-encounters a merged proposal. Scoping to dispatched resumes keeps the default path
byte-identical, which is the same discipline `_context_mode`/`_resolver_mode` already
apply.

**Add a fourth `ISSUE_INVESTIGATOR_CONTEXT_MODE` value (e.g. `context-only`).** Dropped.
The mode is an operator-facing rollout switch read fresh per call; this is a per-run
condition derived from the proposal's status and the request's kind, not something an
operator sets. Reusing `shadow` semantics internally expresses the same thing without
enlarging a rollout vocabulary that `context_rollout.py` and the tests already pin.

## Platform impact

**Migrations.** None. No schema change, no new mctl-api field, no new phase or refusal
reason. `InvestigateResult`'s new fields are defaulted, so `tests/` constructions and
`orchestrator/run_issue_poller.py` are unaffected.

**Backward compatibility.**
- `ISSUE_INVESTIGATOR_CONTEXT_MODE=off` (the default): behaviour is byte-identical,
  including the skip message, except that the returned `InvestigateResult` now carries a
  typed outcome no current caller reads.
- Non-resume runs: unchanged on every mode.
- Self-attached runs: `_OwnExecution.finish`'s predicate changes meaning only for results
  that set `outcome_code` — today's `skipped_reason`-bearing results keep mapping to
  `PHASE_FAILED` because their outcome code will be `refused`, not `succeeded`. The
  `MCTL_ENGINE_FINAL_ATTEMPT=false` retry carve-out is untouched.
- `DevLoopWorkflow`: the new end branch is patch-gated, so replay of
  `tests/fixtures/histories/dev_loop_resumed.json` and `dev_loop_*.json` is unaffected.

**Resource impact.** One extra shallow `gh repo clone --depth=1` plus one collector pass
per dispatched resume onto a terminal proposal. No model call — this path never reaches
`_run_agent`, so it costs no subscription quota. Compared with today's ~80s no-op run, the
added wall-clock is the clone plus assembly, on the order of tens of seconds.

**Risks and mitigations.**
- *A context-only run mutates the merged proposal.* Mitigated structurally: the path never
  creates a staging directory, never calls `write_status_yaml`, and never reaches the
  publish swap — the only three writers into `proposal_dir`. Covered by a test that hashes
  the proposal directory before and after.
- *Assembly failure turns a previously-"successful" resume into a failure.* Intended, and
  the whole point of the issue's second complaint. Mitigated by the `off`-mode escape
  hatch: an operator can unset `ISSUE_INVESTIGATOR_CONTEXT_MODE` and get today's behaviour
  back with no redeploy, exactly as that variable's docstring promises.
- *The loop wedges on replay.* Mitigated by the `workflow.patched("context-only-resume")`
  gate and by running the existing replay fixtures in CI.
- *Two C2s for one E2 on an Argo retry.* Already handled: `snapshots.persist` /
  `answer_from_seal` classify a repeated seal of the same execution as
  `SNAPSHOT_REPLAYED` or `SNAPSHOT_DIVERGED` via `_retry_stable` / `differing_fields`, and
  the context-only path uses that same client.
- *`is_store_execution` misclassifies a correlation-only `--execution-id`.* The predicate
  requires the `we_` prefix, and `_resolve_work_context_ref` already refuses a `we_` that
  is not in the item's ledger — so a foreign id cannot open the context-only path.

## Correction 2026-09-30: the `work-item-intent` source

§5's claim that the resume intent reaches C2 through issue comments is
withdrawn. The intent is canonical WorkItem state in mctl-api, so this design
adds a first-class source for it.

- **Vocabulary.** `orchestrator/context_snapshot.py` `SOURCE_KINDS` gains
  `"work-item-intent"`. This is additive within `context.mctl.ai/v1alpha1`, the
  same way `human-input-response` was added for #333. `from_dict` still rejects
  unknown keys.
- **Client.** `orchestrator/work_context/client.py` `ROUTES` gains
  `"list_intents": "/api/v1/work-items/{id}/intents"` and
  `"work_item_intent": "/api/v1/work-items/{id}/intents/{intent_id}"`, each with
  an `answer_from_*` classifier that keeps "could not observe" (a transport
  error, 5xx, malformed body, or a truncated final page) apart from "observed
  absent" (a documented 404 or `200 []`). This follows the rules already
  applied to `execution_snapshot`.
- **Resume intent id.** The investigator reads its execution request
  (`ROUTES["execution_request"]`, which already exists) by
  `--execution-request-id` and takes `intent_id` from it. It never takes the id
  from argv or the issue.
- **Collector.** `context_assembly.collect_work_item_intents(assembly_input)`
  returns one `CandidateSource` per selected intent:
  - `kind="work-item-intent"` and `source_id="work-item-intent:<wi>:<id>"`;
  - content is the canonical JSON of `{"text":..., "params":...}`;
  - `uri` is the mctl-api route;
  - `retrieved_at` is the read time and `updated_at` is the intent's `created_at`;
  - trust is `reported`.

  The resume intent is marked pinned. `_PINNED_KINDS` is not widened to the
  whole kind, because older intents stay ranked and droppable. The kind joins
  `_CONTENT_ADDRESSED_KINDS`, since intents are immutable, with freshness
  `None`.
- **Selection.** Take the intents with `id` greater than the highest
  `work-item-intent` id among C1's sources (none, when C1 is absent or predates
  this kind, in which case all intents qualify), in ascending order, capped at 20.
  Always add the pinned resume intent, even if it is older (a re-resume).
  Selection is a pure function of `(C1 sources, intent list, resume intent id)`,
  so a retry of the same `we_` produces identical bytes and replays instead of
  diverging.
- **Switch.** `WORK_ITEM_INTENT_SOURCE` (`off`|`on`, default `off`) is read
  fresh on every call, like `_context_mode()`. When it is `off`, the collector
  is not called at all, and the run logs `[context] work-item-intent source=off`.
  This keeps the correction inert until mctl-api#430 is released and the value
  is set in mctl-gitops, so a missing route can never fail every WorkItem-backed
  run. An unrecognised value means `off`.
- **Where it runs.** It runs in every WorkItem-backed assembly, both the full
  path and the context-only path from §1–§2, before the idempotency guard is
  consulted. A cold, non-WorkItem run does not call it.
- **Failure.** If the referenced resume intent is unresolved, the run raises
  and ends as `failed` / `intent-unresolved` (§3), and E2 advances to `Failed`.
  If a non-referenced intent cannot be listed (the list read fails), the same
  outcome applies. Sealing a C2 that claims completeness it does not have is
  worse than failing.
- **Not authorization.** Nothing in `policy_checkpoint`, approval resolution or
  the ADR 011 provenance block reads `work-item-intent` sources. The resume
  provenance remains the only link to W1/E1/C1.
