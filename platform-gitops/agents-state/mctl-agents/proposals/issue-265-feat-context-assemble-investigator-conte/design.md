# Design: issue-265-feat-context-assemble-investigator-conte

## Current state

### The contract exists; nothing produces one

`orchestrator/context_snapshot.py` (977 lines) is the complete, frozen
`ContextSnapshot` contract from mctlhq/mctl-agents#264 / ADR 009
(`docs/adr/009-context-snapshot-contract.md`):

- Closed vocabularies: `SOURCE_KINDS` (`:50`), `TRUST_TIERS` (`:49`),
  `FRESHNESS_VALUES` (`:48`), `RETENTION_CLASSES` (`:61`), plus
  `MAX_LOCATOR_LENGTH`/`MAX_SELECTOR_JSON_LENGTH` (`:66-67`).
- Frozen dataclasses `Freshness` (`:141`), `Trust` (`:172`), `Selection`
  (`:193`), `Redaction` (`:242`), `ContextSource` (`:278`),
  `ExecutionCorrelation` (`:407`), `StepRef` (`:480`), `ContextStrategy`
  (`:504`), `ContextBudget` (`:537`), `EvidenceRef` (`:583`),
  `RetentionPolicy` (`:604`), `ContextSnapshot` (`:638`).
- `seal()` (`:885`) — the only constructor. It computes
  `content_hash = "sha256:" + sha256(canonical JSON of every field except
  content_hash/snapshot_id/created_at)` via `_hash_bytes` (`:79`) and
  `_canonical_json` (`:83`), derives `snapshot_id = "cs-" + content_hash[7:23]`
  (`:916`), and calls `validate()` (`:734`).
- `validate()` already enforces the budget semantics this proposal must
  satisfy: overrun checks excused only by `truncated=true` (`:758-775`), and
  unconditional reconciliation of `used_sources`/`used_bytes` against the
  actual included sources (`:783-794`).
- `to_log_dict()` (`:807`) is the telemetry-export shape — ids, hashes,
  strategy, counts, byte totals; never `locator` or `selector`.

The module's docstring states it "is not yet imported by production code, only
by tests and fixture generation". A grep for `snapshot` in
`orchestrator/run_issue_investigator.py` returns zero hits. ADR 009's follow-up
table, row (a), names the gap: "A producer wired into
`run_issue_investigator.py` that calls `seal()` with real fetched/hashed
sources — needs an issue."

`tests/fixtures/context/investigator-snapshot.json` is a hand-authored golden
fixture that already describes the intended shape for this agent:
`strategy.name = "deterministic-fixed-order"`, `version = "1.0.0"`,
`retention.class = "execution-record"` with `expires_after_days: 180`, four
included sources across `github-issue`/`target-repo`/`loki-logs`/`incident`,
and a fifth marked `included: false, reason_code: "budget-exhausted"` with
`budget.truncated: true`. Its `content_hash` is asserted byte-for-byte in
`tests/test_context_snapshot.py`.

### The investigator's actual context surface

`orchestrator/run_issue_investigator.py` (2129 lines). `investigate()` (`:1457`)
is the entrypoint declared in `docs/agent-inventory.yaml:76`. The ordering that
matters here:

1. `gh_issue_view(issue_url)` (`:868`) — `gh issue view --json
   number,title,body,state,url` only. No comments, no labels, no linked PRs.
2. Slug/idempotency guard against `_OVERWRITABLE_STATUSES` (`:146`) using
   `_load_status` (`:889`).
3. `_clone_repo(full_repo, slug)` (`:900`) — `gh repo clone ... --depth=1` into
   an mkdtemp wrapper (`investigate():1522`).
4. `_staging_dir(proposal_dir)` (`:268`) — mkdtemp under
   `agents-state/<service>/`, deliberately not under `proposals/`.
5. `prompt = _build_prompt(issue, service, slug)` (`:1127`, called at `:1537`)
   — one f-string interpolating only `issue.ref.full_repo/number/url`,
   `issue.state`, `_neutralize_prompt_tags(issue.title)` and
   `_neutralize_prompt_tags(issue.body)` (`_neutralize_prompt_tags` at `:1098`),
   plus `service`/`slug` in the requested headers. Nothing else.
6. `anyio.run(_run_agent, clone / "repo", prompt, staging.resolve())` (`:1538`).
   `_run_agent` (`:1285`) defers its SDK imports (module note `:68-73`), reads
   `_resolver_mode()` (`:108`), prints
   `[resolver] issue-investigator resolver_mode=...` (`:1309`), and in
   `declarative` mode calls `resolver.execute(...)` with
   `_target_repository_sha(repo_dir)` (`:117`) and `plan.log()` (`:1315`).
   In the default `legacy` mode the SHA is never resolved.
7. `write_status_yaml(staging, issue)` (`:979`, called at `:1643`) — writes
   `status`/`updated_at`/`updated_by`/`source`/`control` atomically via
   mkstemp + `yaml.safe_dump` + `fsync` + `fchmod` + `os.replace`.
8. Publish-by-swap, then `post_proposal_comment` (`:1054`).
   `_status_disagreements` (`:539`) re-checks exactly five fields after
   publish: `status`, `source.repo`, `source.issue`, `source.url`,
   `control.requires_human_approval`.

Everything else the model sees, it fetches itself with Glob/Grep/Read/Bash/
WebSearch/`mcp__mctl__*` — the allow-list in
`orchestrator/options.py:412` — and none of it is recorded.

### Conventions this design must respect

- **Env flags are string enums with an explicit allow-list.** `_resolver_mode`
  (`:108`) reads fresh per call, lowercases, and raises `SystemExit` naming the
  allowed values. There is no boolean env helper anywhere in the repo.
- **Telemetry is `print`.** The only structured JSON emission on this path is
  `ExecutionPlan.log()` → `print(f"[resolver] execution_plan={json.dumps(...)}")`
  at `orchestrator/resolver.py:290`.
- **Import isolation is enforced.** `tests/test_worker_isolation.py` forbids
  `claude_agent_sdk` and `orchestrator.run_implementer` in the worker's import
  closure; `tests/test_context_snapshot.py:268` asserts `context_snapshot`
  itself stays SDK-free. `run_issue_poller.py:68` imports pure helpers from
  `run_issue_investigator`, which is why its SDK imports are function-local.
- **`orchestrator/validate_manifest.py:275`** asserts by regex that a driver's
  declared env vars are read with `os.getenv("<NAME>"`.

## Proposed solution

### New module: `orchestrator/context_assembly.py`

Stdlib-only, no `claude_agent_sdk` import, mirroring `context_snapshot.py`'s
discipline so both isolation tests stay green. It owns the whole pipeline the
issue draws — collectors → normalize + provenance → freshness → dedup/truncate
→ budget → `seal()` — and nothing else. It never decides permissions.

```
CandidateSource      (mutable, in-process only; holds raw bytes)
  source_id, kind, locator, selector, raw: bytes, observed_at,
  max_age_seconds, trust_tier, trust_rationale, reason_code, strategy_step

Collector = Callable[[AssemblyInput], list[CandidateSource]]

AssemblyInput        issue, issue_comments, repo_dir, target_repo_sha,
                     full_repo, proposal_dir, prompt_template, now, config
AssemblyConfig       max_sources, max_bytes, max_bytes_per_source,
                     max_candidates, max_comments, freshness table
AssemblyResult       snapshot: ContextSnapshot
                     rendered: dict[str, str]     # payloads, prompt-only
                     metrics: AssemblyMetrics
```

The single most important structural decision: **payloads and provenance
travel on different objects.** `AssemblyResult.snapshot` is payload-free by
construction (`ContextSource` has no payload field and `from_dict` rejects
unknown keys). `AssemblyResult.rendered` holds the text and is consumed only by
`_build_prompt`. No function in this module writes `rendered` to a log. That is
how "raw retrieved payloads must not be blindly copied into traces" becomes a
property of the type graph rather than a rule someone has to remember.

**Collectors**, run in a fixed declared order (that order *is* the
`deterministic-fixed-order` strategy):

| # | Collector | `kind` | Source of bytes | `trust.tier` |
|---|---|---|---|---|
| 1 | `collect_inline_template` | `inline-template` | the un-interpolated `_build_prompt` scaffold | `authoritative` |
| 2 | `collect_github_issue` | `github-issue` | the five fields `gh_issue_view` already fetches | `untrusted` |
| 3 | `collect_issue_comments` | `github-issue-comment` | `comments` added to the *same* `gh issue view --json` call — zero extra API calls; one source per comment, ordered by comment id ascending, newest `max_comments` retained | `untrusted` |
| 4 | `collect_target_repo` | `target-repo` | none — `byte_count=0`, `selector={"mode":"agent-directed"}`, locator `git+https://github.com/<repo>@<sha>` | `authoritative` |
| 5 | `collect_prior_proposal` | `proposal-dir` | the existing `requirements.md`/`design.md`/`tasks.md` when re-investigating a `proposed` proposal | `corroborated` |

Five kinds, three of them heterogeneous in origin (GitHub API, local git
checkout, local gitops worktree, in-process template), which clears the "at
least three heterogeneous source types" criterion without adding a credentialed
network dependency. `loki-logs` and `incident` are deliberately absent: they
are reachable only through `mcp__mctl__*` tools the *model* calls, and the
Python wrapper has no Loki or incident client. The `Collector` alias is the
seam that makes adding them a pure append to `_COLLECTOR_ORDER`.

**Rank** is assigned once, 1-based, over the concatenated candidate list in
collector order, before any filtering, and never renumbered. A rank is
therefore a stable statement of position in the candidate list, and every later
stage only flips `included` and sets a `reason_code`.

**Normalize + provenance.** Each candidate's bytes are UTF-8 encoded and hashed
with `context_snapshot`'s own rule. To guarantee ADR 009's "a second,
disagreeing hash convention creeps in" risk does not materialize,
`context_snapshot.py` gains two thin public aliases — `hash_bytes` and
`canonical_json` — over the existing `_hash_bytes`/`_canonical_json`, with no
behaviour change, and `context_assembly` imports only those.

**Freshness.** A per-kind table supplies `max_age_seconds`: `3600` for
`github-issue` and `github-issue-comment`, `86400` for `proposal-dir`, `None`
for the two content-addressed kinds. `classify(observed_at, max_age, now)`
returns `fresh` when age ≤ max/2, `aging` when age ≤ max, `stale` beyond. The
content-addressed kinds return `fresh` explicitly with a rationale, which is
what the golden fixture's `target-repo` entry already does; the `unknown`
fail-safe remains the default for anything the table does not classify. A
`stale` candidate is kept in `sources` with `included=false,
reason_code="stale"` — visible and countable, never silently dropped.

**Deduplicate.** Group by `content_hash`; the lowest rank wins, the rest get
`included=false, reason_code="duplicate-content"`.

**Truncate.** A candidate over `max_bytes_per_source` has its bytes cut to the
limit *before* hashing, so `content_hash` describes what the model actually
saw — the same hash-after-modification rule ADR 009 sec. 7 fixes for redaction.
`byte_count` is post-truncation, the retained range goes into the source's
`selector` as `{"byte_range": [0, N]}` (a slice descriptor, which is exactly
what `selector` is for), and `budget.truncated=true`.

**Budget.** Walk in ascending rank; include while `used_sources < max_sources`
and `used_bytes + byte_count <= max_bytes`. From the first candidate that does
not fit, that candidate and every lower-ranked one are marked
`included=false, reason_code="budget-exhausted"` and `truncated=true` is set.
Stopping at the first miss rather than opportunistically fitting a smaller
later source keeps the rule one sentence long and trivially reproducible.

A `max_candidates` ceiling bounds the `sources` array itself (a 500-comment
issue must not produce a 500-entry snapshot). Excess candidates are dropped
deterministically from the tail of the collector order and counted in metrics
as `candidates_dropped_pre_budget` — an explicitly reported cap, not a silent
truncation.

**Seal.** `ContextStrategy(name="deterministic-fixed-order", version="1.0.0",
ranker_name=None, ranker_version=None)`,
`RetentionPolicy(class_="execution-record", expires_after_days=180)`, no
`StepRef` (the investigator is one model execution), `evidence_refs=()` until
#199 exists. `created_at` is injected, and `seal()` excludes it from the hash,
so the same inputs seal to the same `snapshot_id` at any wall-clock time.

### Execution correlation

`build_execution_correlation()` has two branches:

- **`declarative`**: copy `definition_version`, `definition_content_hash`,
  `profile_version`, `profile_content_hash`, `release_revision` and
  `target_repository_sha` straight off `resolver.ExecutionPlan`
  (`orchestrator/resolver.py:226-258`), exactly as ADR 009 sec. 4 prescribes.
- **`legacy`** (today's production default, because `declarative` needs a
  mctl-gitops catalog checkout): `definition_version="legacy"` with
  `definition_content_hash` over the bytes of
  `agents/_manifests/issue-investigator/agent.yaml`; `profile_version="legacy"`
  with `profile_content_hash` over the canonical JSON of the constants that
  actually determine the legacy execution shape — `INVESTIGATOR_MODEL`, the
  `allowed_tools` list and `ISSUE_INVESTIGATOR_BUDGET_USD` from
  `orchestrator/options.py:387-419`; `release_revision=0` for "no registry
  release resolved". Both hashes use the one canonical rule above.

`temporal_workflow_id` comes from `orchestrator.temporal.issue_ref.workflow_id_for`,
already used at `run_issue_investigator.py:1069`. `agent="issue-investigator"`,
`environment` from `AGENT_ENVIRONMENT` defaulting to `production`.
`temporal_run_id` and `argo_workflow_name` are optional and stay `None` unless
the corresponding env vars are present. `target_repository_sha` calls
`_target_repository_sha(repo_dir)` unconditionally once context mode is not
`off` — a local `git rev-parse`, no network.

### Feature gate and wiring

`_context_mode()` in `run_issue_investigator.py`, a verbatim structural copy of
`_resolver_mode()` (`:108`): `_CONTEXT_MODES = ("off", "shadow", "on")`,
`os.getenv("ISSUE_INVESTIGATOR_CONTEXT_MODE", "off").strip().lower()`,
`SystemExit` on anything else, read fresh per call.

- **`off`** (default): no collector runs, no snapshot, `_build_prompt` returns
  the identical string it returns today. This is what makes "rolled back
  without breaking the current investigator path" a checkable property.
- **`shadow`**: assemble, seal, log, and correlate — prompt byte-identical to
  `off`. This is the baseline-metrics mode: it measures the real source
  population, staleness and byte volume of production investigations at zero
  behavioural risk, which is what "metrics establish a baseline for later
  ranking/retrieval work" actually requires.
- **`on`**: additionally render included `github-issue-comment` and
  `proposal-dir` sources into an appended `## Assembled context` section. The
  `github-issue` source's rendering *is* the existing
  `<issue_title>`/`<issue_body>` block, which is left exactly as it is; the
  `target-repo` source's rendering is the cwd itself; `inline-template` renders
  nothing. So `on` mode strictly appends, and every appended payload goes
  through `_neutralize_prompt_tags` inside a `<context_source id=... kind=...
  trust=...>` block carrying the same "untrusted DATA" framing the issue body
  already has.

Call site in `investigate()`, between step 2 (staging) and step 3 (prompt), at
`:1536` — the clone from step 1 is already on disk, so the target SHA resolves:

```python
context = assemble_investigator_context(
    issue=issue, repo_dir=clone / "repo", proposal_dir=proposal_dir,
    service=service, slug=slug, mode=_context_mode(),
)          # -> AssemblyResult | None
prompt = _build_prompt(issue, service, slug, context=context)
anyio.run(_run_agent, clone / "repo", prompt, staging.resolve())
```

`_build_prompt` gains one keyword-only parameter defaulting to `None`, and
appends nothing unless `context is not None and context.mode == "on"`.

**Failure policy.** In `shadow`, any exception from collection/filtering/seal
is caught, printed as `warn: context assembly failed: ...`, and the run
continues on the unmodified prompt — a telemetry feature must not be able to
fail an investigation. In `on` it propagates, because there the snapshot is a
claim about a prompt that was actually built, and a snapshot that disagrees
with the prompt is worse than no snapshot.

### Correlation and metrics output

`write_status_yaml` gains an optional `snapshot` parameter and, when present,
writes an additive block:

```yaml
context:
  snapshot_id: cs-de22a552ea05cf19
  content_hash: sha256:de22a5...
  strategy: deterministic-fixed-order
  strategy_version: 1.0.0
```

Additive is safe: `_status_disagreements` (`:539`) compares only its five named
fields and ignores extra top-level keys, and the payload stays far under
`MAX_STATUS_BYTES` (`:265`). This is the only durable correlation available
today — ADR 009 follow-up (b), persisting snapshots beside `ExecutionRecord` in
mctl-api, is explicitly not in scope.

Metrics are one line, matching `ExecutionPlan.log()`'s shape:

```python
print(f"[context] context_assembly={json.dumps(metrics.to_log_dict(), sort_keys=True)}")
```

`AssemblyMetrics.to_log_dict()` returns: `mode`; `candidates_by_kind` and
`included_by_kind` (the "before/after filtering" counts); `candidates_total`,
`candidates_dropped_pre_budget`; `dropped_stale`, `dropped_duplicate`,
`excluded_budget`, `truncated_sources`; `used_sources`, `used_bytes`;
`assembly_latency_ms`; `collector_calls`; `strategy_name`, `strategy_version`;
and the whole of `snapshot.to_log_dict()` merged under a `snapshot` key. No
`locator`, no `selector`, no payload byte ever appears — enforced by a test,
not by convention.

## Alternatives

1. **Gate the pilot on `ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative` and take
   `ExecutionCorrelation` straight off `ExecutionPlan`.** Cleanest correlation
   story, and rejected because it makes the pilot undeployable: the
   v1alpha2 manifest's `executionProfileRef` now resolves against the real
   mctl-gitops catalog (see the comment block in
   `agents/_manifests/issue-investigator/agent.yaml`), production still runs
   `legacy`, and #265 would sit dark behind another repository's rollout. The
   documented legacy pins cost one open question and buy a shippable pilot.

2. **Put assembly inside `_run_agent` and hand `seal()` the real tool calls the
   model makes, via SDK hooks.** This is the faithful per-file enumeration ADR
   009 sec. 8 describes and explicitly defers to follow-up (e). Rejected for
   this issue: it requires a `PreToolUse`/`PostToolUse` hook that records every
   Read/Grep, which makes the snapshot a *post-hoc* record of what the model
   chose rather than a *pre-execution* statement of what it was given — the
   opposite of the issue's "assembling a bounded, immutable `ContextSnapshot`
   **before** model execution". It also lands the assembler inside the one
   function that must import `claude_agent_sdk`, breaking the stdlib-only
   property that keeps the module importable by the 256Mi Temporal worker.

3. **Extend `context_snapshot.py` with the collectors instead of adding a
   module.** Rejected because that module's contract is "no retrieval, no
   ranking, no I/O" (`context_snapshot.py:11-14`), it is imported by
   `tests/test_context_snapshot.py`'s isolation test, and mixing a network- and
   filesystem-touching pipeline into the schema would make the schema
   untestable without mocks — precisely the separation ADR 009 built.

4. **One boolean `ISSUE_INVESTIGATOR_CONTEXT_ENABLED` instead of a three-value
   mode.** Rejected twice over: the repo has no boolean env helper and
   `_resolver_mode` establishes the string-enum convention, and a boolean
   collapses `shadow` into `on`. `shadow` is the mode that actually delivers
   the "metrics establish a baseline" acceptance criterion — it measures
   production investigations without changing a single prompt byte.

## Platform impact

- **Migrations:** none. No mctl-api table, no GitOps schema change, no
  `ClusterWorkflowTemplate` change, no chart change. `.status.yaml` gains an
  optional top-level `context` block; every existing reader
  (`orchestrator/proposal_state.py`, the implementer, the approve operation,
  the reconcile sweep) reads named keys and ignores unknown ones.
- **Backward compatibility:** the default (`off`) path is the current code
  path with two extra function-call sites that immediately return `None`. The
  new `_build_prompt` parameter is keyword-only with a `None` default, so
  `agents/_manifests/issue-investigator/agent.yaml`'s
  `prompt.sources: [inline: orchestrator/run_issue_investigator.py:_build_prompt]`
  still names the right symbol and `orchestrator/validate_manifest.py` keeps
  resolving it. `run_issue_poller.py`'s import of this module's pure helpers is
  unaffected because `context_assembly` is stdlib-only.
- **Resource impact:** one extra `git rev-parse` per run, one extra JSON field
  on an existing `gh issue view` call, a handful of local file reads bounded by
  `max_bytes_per_source`, and one sha256 per candidate. Sub-second, well inside
  the existing `ISSUE_INVESTIGATOR_BUDGET_USD` and drain timeouts. In `on` mode
  the prompt grows by at most `max_bytes` (120 KB default), which is a real
  model-cost increase and the reason `on` is not the default.
- **Risks and mitigations:**
  - *A second hash convention creeps in* — the exact risk ADR 009 names.
    Mitigated by exporting `hash_bytes`/`canonical_json` from
    `context_snapshot.py` and forbidding any other hashing in the new module,
    asserted by a test that the assembler's source hashes match
    `context_snapshot`'s rule over the same bytes.
  - *Payload leakage into telemetry.* Mitigated structurally (payloads live on
    `AssemblyResult.rendered`, never on `ContextSnapshot`) and by a test that
    feeds a distinctive marker string through a collector and asserts it
    appears in no emitted log line.
  - *Prompt-injection surface widens* — issue comments are third-party text
    that today never reaches the model. Mitigated by routing every rendered
    payload through the existing `_neutralize_prompt_tags` and the existing
    untrusted-data framing, and by `on` being opt-in. `trust.tier="untrusted"`
    on those sources records the fact; per ADR 009 sec. 5 it grants nothing.
  - *Assembly failure breaks investigations.* Mitigated by the shadow-mode
    catch-and-continue policy and by `off` being the default.
  - *Non-determinism sneaks in via wall-clock or dict ordering.* Mitigated by
    injecting `now`, excluding `created_at` from the hash by contract, sorting
    comments by id, and a test that seals the same inputs twice at two clock
    values and asserts one `snapshot_id`.
  - *Relevance drifts into authorization.* Mitigated by keeping the module free
    of any allow/deny vocabulary and by an import-direction test, matching the
    check ADR 009 sec. 5 already imposes on the schema module.
- **Security:** no new credential, no new network endpoint, no new outbound
  call. The added `comments` field rides the existing authenticated `gh`
  invocation. The snapshot remains strictly non-authoritative; provider-side
  authorization is unchanged.
