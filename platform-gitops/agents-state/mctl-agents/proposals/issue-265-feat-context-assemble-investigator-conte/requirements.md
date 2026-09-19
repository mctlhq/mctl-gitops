# Assemble the investigator ContextSnapshot with deterministic source selection

## Context

ADR 009 (`docs/adr/009-context-snapshot-contract.md`) and
`orchestrator/context_snapshot.py` landed the `ContextSnapshot` contract as a
deliberately inert schema: a frozen-dataclass document, a canonical-JSON
`sha256:` hash rule, `seal()`, `validate()` and `to_log_dict()`, with **no
retrieval, no ranking and no I/O**. The module's own docstring records that it
"is not yet imported by production code, only by tests and fixture generation",
and the ADR's follow-up table names the missing half explicitly: row (a), "A
producer wired into `run_issue_investigator.py` that calls `seal()` with real
fetched/hashed sources — needs an issue". This proposal is that issue
(mctlhq/mctl-agents#265).

Today the investigator's context surface is assembled implicitly and recorded
nowhere. `gh_issue_view` (`orchestrator/run_issue_investigator.py:868`) fetches
exactly `number,title,body,state,url` — no comments, no labels. `_clone_repo`
(`:900`) makes a `--depth=1` checkout the agent then free-roams with
Glob/Grep/Read, and `_target_repository_sha` (`:117`) pins its HEAD only when
`ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative` — which is not the production
default (`_resolver_mode`, `:109`, defaults to `legacy`). `_build_prompt`
(`:1127`) interpolates the issue into the prompt with no record of what else
the model saw. Nothing measures staleness, duplication, byte volume or
assembly cost, so there is no baseline against which any future ranking or
retrieval work could be judged. This proposal adds the deterministic assembly
pipeline — collect, normalize, freshness-filter, deduplicate, truncate, budget,
seal — behind a feature gate whose default is today's behaviour byte-for-byte.

## User stories

- AS a platform reviewer reading a bad proposal I WANT the sealed
  `ContextSnapshot` for that investigation SO THAT I can tell whether the agent
  reasoned badly or was simply never shown the relevant evidence.
- AS a platform operator I WANT context assembly gated by an env var with
  `off` as the default SO THAT I can enable, shadow-run and roll back the
  pilot without redeploying or touching the existing investigator path.
- AS an agent-platform engineer I WANT source counts, drop reasons, selected
  byte totals and assembly latency emitted per run SO THAT later ranking or
  retrieval work has a measured baseline rather than an anecdote.
- AS a security reviewer I WANT provenance, hashes and counts in telemetry and
  never the retrieved payloads SO THAT enabling observability does not create a
  second copy of untrusted issue text or log tails.
- AS a future implementer of #195 traces / #199 evidence I WANT the snapshot id
  and content hash correlated to the execution and carried into the proposal's
  `.status.yaml` SO THAT there is a join key to build against before either
  store exists.

## Acceptance criteria (EARS)

### Feature gate and compatibility

- WHEN `ISSUE_INVESTIGATOR_CONTEXT_MODE` is unset THE SYSTEM SHALL default to
  `off` and SHALL execute the existing investigator path unchanged — no
  collector runs, no snapshot is sealed, and the string returned by
  `_build_prompt` is byte-identical to the current implementation's.
- WHEN `ISSUE_INVESTIGATOR_CONTEXT_MODE` is set to a value outside
  `{off, shadow, on}` THE SYSTEM SHALL raise `SystemExit` naming the allowed
  values, mirroring `_resolver_mode`'s behaviour at
  `orchestrator/run_issue_investigator.py:109-115`.
- WHILE the mode is `shadow` THE SYSTEM SHALL collect, filter, seal, log and
  correlate a snapshot AND SHALL leave the prompt byte-identical to `off`.
- WHILE the mode is `on` THE SYSTEM SHALL additionally render the included
  sources that are not already present in the prompt into an appended context
  section, leaving the existing `<issue_title>`/`<issue_body>` blocks and every
  other instruction in `_build_prompt` unmodified.
- WHEN the investigator runs in any mode THE SYSTEM SHALL print one line
  naming the effective context mode, in the style of the existing
  `print(f"[resolver] issue-investigator resolver_mode={mode!r}")` at
  `orchestrator/run_issue_investigator.py:1310`.
- IF any collector, filter or seal step raises in `shadow` mode THEN THE SYSTEM
  SHALL log the failure, skip context assembly, and continue the investigation
  on the unmodified prompt.
- IF any step raises in `on` mode THEN THE SYSTEM SHALL fail the run rather
  than silently investigating on a different prompt than the snapshot claims.

### Sources and provenance

- WHEN assembly runs THE SYSTEM SHALL produce candidates from at least three
  heterogeneous `SOURCE_KINDS` values, and the pilot SHALL cover
  `github-issue`, `github-issue-comment`, `target-repo`, `proposal-dir` and
  `inline-template`.
- WHEN a candidate is produced THE SYSTEM SHALL record every field
  `ContextSource` requires — `source_id`, `kind`, `locator`, `selector`,
  `content_hash`, `byte_count`, `retrieved_at`, `freshness`, `trust`,
  `selection` — with `kind` drawn from `context_snapshot.SOURCE_KINDS` and
  `trust.tier` from `context_snapshot.TRUST_TIERS`.
- WHEN the `github-issue` source is built THE SYSTEM SHALL assign
  `trust.tier="untrusted"` with `rationale_code="github-issue-body-third-party-text"`,
  and SHALL assign the same tier to every `github-issue-comment` source.
- WHEN the `target-repo` source is built THE SYSTEM SHALL set its locator to
  `git+https://github.com/<owner>/<repo>@<sha>` using `_target_repository_sha`,
  `selector={"mode": "agent-directed"}`, `byte_count=0` and
  `trust.tier="authoritative"`, per ADR 009 sec. 8.
- WHEN the investigator runs in `shadow` or `on` mode THE SYSTEM SHALL resolve
  `_target_repository_sha` regardless of `ISSUE_INVESTIGATOR_RESOLVER_MODE`.
- WHILE building any source THE SYSTEM SHALL compute `content_hash` using the
  hash rule already defined in `orchestrator/context_snapshot.py` and SHALL NOT
  introduce a second hash convention.
- WHEN a `ContextSource` is constructed THE SYSTEM SHALL keep its `locator`
  within `MAX_LOCATOR_LENGTH` and its `selector` canonical JSON within
  `MAX_SELECTOR_JSON_LENGTH`.

### Freshness, deduplication, truncation, budget

- WHEN a candidate's source kind is pinned by content address (`target-repo`
  pinned by SHA, `inline-template` hashed in-process) THE SYSTEM SHALL classify
  `freshness.staleness="fresh"` with `max_age_seconds=null`.
- WHEN a candidate declares `max_age_seconds` THE SYSTEM SHALL classify it
  `fresh` while its age is at most half that value, `aging` while its age is at
  most that value, and `stale` beyond it.
- IF a candidate classifies as `stale` THEN THE SYSTEM SHALL retain it in
  `sources` with `selection.included=false` and
  `selection.reason_code="stale"`, never silently discard it.
- IF two candidates share a `content_hash` THEN THE SYSTEM SHALL include only
  the lower-ranked one and SHALL mark the other
  `included=false, reason_code="duplicate-content"`.
- IF a candidate's normalized bytes exceed `max_bytes_per_source` THEN THE
  SYSTEM SHALL truncate the bytes, hash the post-truncation bytes, record
  `byte_count` post-truncation, record the retained range in the source's
  `selector`, and set `budget.truncated=true`.
- WHEN the budget is applied THE SYSTEM SHALL walk candidates in ascending rank
  and, from the first candidate that does not fit within `max_sources` or
  `max_bytes`, SHALL mark that candidate and every lower-ranked candidate
  `included=false, reason_code="budget-exhausted"` and set
  `budget.truncated=true`.
- WHILE the candidate list exceeds the configured candidate ceiling THE SYSTEM
  SHALL drop the excess deterministically, SHALL count the drop in metrics, and
  SHALL NOT report the run as having considered them.
- WHEN assembly runs twice over identical collected inputs, identical
  configuration and an identical injected clock THE SYSTEM SHALL produce
  identical `snapshot_id` and `content_hash`.
- WHEN assembly runs twice over identical inputs at two different `created_at`
  values THE SYSTEM SHALL still produce identical `snapshot_id` and
  `content_hash`, because `created_at` is excluded from the hash by
  `context_snapshot.seal`.

### Correlation, metrics, telemetry safety

- WHEN a snapshot is sealed THE SYSTEM SHALL populate `ExecutionCorrelation`
  from the resolved `ExecutionPlan` while `ISSUE_INVESTIGATOR_RESOLVER_MODE`
  is `declarative`, and from documented legacy-mode pins otherwise, never
  leaving a required field empty and never fabricating a registry release.
- WHEN a snapshot is sealed THE SYSTEM SHALL write a `context` block carrying
  `snapshot_id`, `content_hash`, `strategy` name and version into the
  proposal's `.status.yaml` via `write_status_yaml`
  (`orchestrator/run_issue_investigator.py:979`), additively, without altering
  the `status`, `source` or `control` blocks `_status_disagreements` (`:539`)
  checks.
- WHEN a snapshot is sealed THE SYSTEM SHALL emit exactly one structured
  metrics line carrying: candidate count per source kind before filtering;
  included count per source kind after filtering; `used_sources`; `used_bytes`;
  stale, duplicate, truncated and budget-excluded counts; assembly wall-clock
  latency in milliseconds; the number of collector invocations; the strategy
  name and version; and the `snapshot_id` and `content_hash`.
- WHILE emitting metrics or logs THE SYSTEM SHALL emit no retrieved payload
  bytes, no `locator` and no `selector`, restricting the snapshot portion of
  the line to `ContextSnapshot.to_log_dict()`'s fields
  (`orchestrator/context_snapshot.py:807`).
- WHEN rendering included sources into the prompt in `on` mode THE SYSTEM SHALL
  pass every untrusted payload through `_neutralize_prompt_tags`
  (`orchestrator/run_issue_investigator.py:1098`) and SHALL wrap each in a
  delimiter block declaring it untrusted data.
- WHILE any code path in the new module executes THE SYSTEM SHALL NOT consult
  a snapshot field to decide whether an action is permitted, preserving ADR 009
  sec. 5's "context relevance is never authorization" rule.
- WHILE the new assembly module is imported THE SYSTEM SHALL NOT import
  `claude_agent_sdk` or `orchestrator.run_implementer`, keeping
  `tests/test_worker_isolation.py` green.

## Out of scope

- Vector databases, embeddings, semantic retrieval, and any ML reranker.
  `strategy.ranker_name`/`ranker_version` stay `null`.
- Cross-surface or cross-run working memory; each investigation seals its own
  root snapshot.
- Changing runtime authorization semantics, `ExecutionProfile` eligibility
  (#242), or policy checkpoints (#197).
- `loki-logs` and `incident` collectors. Both kinds are reachable today only
  through mctl MCP tools the *model* calls; the Python wrapper holds no Loki or
  incident client, and adding one is a new credentialed network dependency. The
  `Collector` seam this proposal defines makes them additive later. The pilot
  ships five other kinds, satisfying the "at least three heterogeneous source
  types" criterion without that dependency.
- Persisting sealed snapshots into mctl-api beside `ExecutionRecord`
  (ADR 009 follow-up (b)). This proposal correlates through `.status.yaml` and
  structured logs only.
- A real redaction helper (ADR 009 follow-up (c)). `Redaction()` keeps its
  no-op default; nothing here claims redaction occurred.
- Per-file enumeration of the agent's Glob/Grep/Read inside the clone
  (ADR 009 follow-up (e)); the single `agent-directed` `target-repo` source
  stands, as ADR 009 sec. 8 rules.
- Step-level child snapshots (`StepRef`). The investigator is a single model
  execution; only a root snapshot is sealed.
- Token counting or model-context-window accounting — deferred by ADR 009
  sec. 6 with written rationale.
- Wiring assembly into the implementer, shepherd, incident-responder,
  service-agent or mentor.

## Open questions

- **Legacy-mode execution correlation.** `ExecutionCorrelation` requires
  `definition_version`, `definition_content_hash`, `profile_version`,
  `profile_content_hash` and `release_revision`, all of which exist only on a
  resolved `ExecutionPlan` — and `declarative` mode needs a mctl-gitops catalog
  checkout (`agents/_manifests/issue-investigator/agent.yaml`'s
  `executionProfileRef` comment), so production still runs `legacy`. Gating the
  pilot on `declarative` would make it undeployable. Proceeding with documented
  legacy pins: `definition_version="legacy"` with `definition_content_hash`
  over the bytes of `agents/_manifests/issue-investigator/agent.yaml`;
  `profile_version="legacy"` with `profile_content_hash` over the canonical
  JSON of the legacy option constants that actually determine the execution
  shape (`INVESTIGATOR_MODEL`, the `allowed_tools` list and
  `ISSUE_INVESTIGATOR_BUDGET_USD` in `orchestrator/options.py:387-419`); and
  `release_revision=0` meaning "no registry release resolved". **A reviewer
  should confirm this is acceptable**, since ADR 009's risk table names "a
  second, disagreeing hash convention creeps in" — mitigated here by reusing
  `context_snapshot`'s single canonical-JSON rule and nothing else.
- **Default budget numbers.** `tests/fixtures/context/investigator-snapshot.json`
  uses `max_sources=5 / max_bytes=60000 / max_bytes_per_source=50000`, which is
  illustrative and too tight once issue comments participate. Proceeding with
  `max_sources=12 / max_bytes=120000 / max_bytes_per_source=50000`, all
  overridable by env and all recorded inside the hashed `budget` block.
- **Comment ceiling.** A long issue thread could dominate the candidate list.
  Proceeding with a deterministic ceiling of the 20 most recent comments,
  counted in metrics as a pre-budget drop rather than hidden.
- **Whether `shadow` or `on` becomes the eventual production default.** Out of
  scope for this proposal; `off` ships as the default and the rollout decision
  is a later operational change.
