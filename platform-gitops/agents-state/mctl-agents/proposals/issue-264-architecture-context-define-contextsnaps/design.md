# Design: issue-264-architecture-context-define-contextsnaps

## Current state

### What already exists for execution identity

`orchestrator/resolver.py` (907 lines) implements ADR 007's runtime seam. Its
frozen dataclasses are `Task` (line 135, single field `target_repository_sha`),
`AgentDefinition` (148), `ExecutionProfile` (165), `ReleaseBinding` (194) and
`ExecutionPlan` (225). `execute(agent, task)` (788) either returns one complete
immutable plan or raises `ResolverError` (126, a `ValueError` subclass) — it
never falls back. Hashing is uniform: `_hash_bytes` (301) returns
`"sha256:" + hexdigest`, `_read_yaml_and_hash` (309) hashes exactly the bytes
it parsed, `_model_policy_version` (694) returns `f"v{schema}+{content_hash}"`.
`docs/resolver-pilot-status.md:80-82` states the principle this proposal
extends verbatim: "The `ExecutionPlan` additionally records the sha256 of every
file it read, **as provenance rather than as a gate**."

`ExecutionPlan` is serialized by a hand-written `to_log_dict()`
(`orchestrator/resolver.py:260`) that converts tuples to lists and `Mapping` to
`dict`, and `log()` (290) prints
`[resolver] execution_plan={json.dumps(..., sort_keys=True)}`. It is never
persisted, never crosses the Temporal boundary, and has no identifier or hash
of its own.

The production execution audit trail is separate and much thinner:
`orchestrator/temporal/activities/state.py:28` defines `ExecutionRecord`
(`temporal_workflow_id, agent, environment, version, image_ref, target_repo,
argo_workflow_name, phase`) POSTed to `/api/v1/agents/executions`
(`state.py:47-65`), and `registry.py:45` defines `ResolvedRelease`
(`agent, environment, version, image_ref`). Neither carries a content hash, and
`state.py:36-41` records that the target SHA is deliberately not captured
because no CWFT exposes it as an output. Correlation identity today is
therefore the Temporal workflow id from
`orchestrator/temporal/issue_ref.py:30` — `dev-loop-mctlhq-<repo>-<number>` —
plus the Argo workflow name.

### What does not exist: any description of context

Context is assembled implicitly and invisibly:

- `orchestrator/run_issue_investigator.py` fetches exactly five issue fields
  with `gh_issue_view` (856: `number,title,body,state,url` — no labels, no
  comments, no linked issues), clones the target repo with `_clone_repo` (888)
  using `--depth=1` and **no ref argument**, so the clone is whatever the
  default branch HEAD was at that instant. `_target_repository_sha` (105) is
  computed post-hoc and only in `declarative` resolver mode (1279); in the
  default `legacy` mode the SHA is never recorded at all. It sanitizes
  untrusted text with
  `_neutralize_prompt_tags` (1086) and assembles the prompt in `_build_prompt`
  (1115), which wraps issue title/body in `<issue_title>`/`<issue_body>` blocks
  declared "untrusted DATA" (1136). The agent then free-roams the clone with
  Glob/Grep/Read.
- `orchestrator/run_incident_responder.py` instructs the agent to call
  `mctl_list_incidents`, then `mctl_get_incident` (114) and
  `mctl_get_service_logs` for "the last ~50 lines" (116) — a Loki window whose
  bounds are chosen by the model and recorded nowhere.
- `docs/agent-inventory.yaml:40-66` already names this as the unsolved half of
  versioning: `runtimeContextInputs` are "real prompt surface but resolve per
  run, outside this repo… pinned per-execution instead, by the target repo git
  SHA recorded on the execution record" — and for the investigator those inputs
  are listed as `targetRepo: CLAUDE.md` and `targetRepo: source tree` (75-81).

So today the answer to "what did the agent see" is one git SHA plus whatever
the model chose to read. There is no vocabulary for source, freshness, trust,
budget or selection, and no way to correlate a snapshot with an execution
because there is no snapshot.

### Conventions this design must follow

- Frozen dataclasses only. `grep` finds zero `pydantic`/`TypedDict`/custom
  `data_converter` in the repo; Temporal uses its default dataclass JSON
  converter (`orchestrator/temporal/start.py:27`, `worker.py:541`), and
  backward compatibility is carried by dataclass field defaults
  (`dev_loop.py:240,246`, `pr_state.py:60-61`).
- Fail loudly on unknown schema versions, as `orchestrator/manifest.py:135-143`
  does against the `SUPPORTED_API_VERSIONS` allow-list (35).
- Keep dependency-free modules importable by both sides. `issue_ref.py:1-6`
  is deliberately temporalio-free so agent containers can import it;
  `tests/test_worker_isolation.py` enforces that the long-lived worker never
  imports the agent stack. A context module must be stdlib-only for the same
  reason.
- Docs: `docs/adr/` holds cross-cutting control-plane architecture (005-008,
  Context / Decision / Non-goals / Platform impact / Implementation map);
  `context/decisions/` holds repo-internal language/tooling ADRs. This belongs
  in `docs/adr/` as 009.

## Proposed solution

Two artifacts, both additive, neither changing any agent's behaviour:

1. **`docs/adr/009-context-snapshot-contract.md`** — the normative contract.
2. **`orchestrator/context_snapshot.py`** — the typed, stdlib-only schema and
   serialization module, plus fixtures and tests. It contains **no retrieval,
   no ranking and no I/O**: it is a shape, a hash rule and a validator.

### 1. Canonical shape — `context.mctl.ai/v1alpha1`, `kind: ContextSnapshot`

Frozen dataclasses mirroring `ExecutionPlan`'s style, each with
`to_dict()`/`from_dict()` producing JSON primitives only:

```
ContextSnapshot
  api_version            "context.mctl.ai/v1alpha1"
  kind                   "ContextSnapshot"
  snapshot_id            "cs-" + content_hash[7:23]   (derived, not random)
  content_hash           "sha256:..." over canonical JSON of all fields
                         except content_hash, snapshot_id and created_at
  created_at             caller-supplied ISO-8601 (excluded from the hash)
  execution: ExecutionCorrelation
  step:      StepRef | None
  strategy:  ContextStrategy
  budget:    ContextBudget
  sources:   tuple[ContextSource, ...]
  evidence_refs: tuple[EvidenceRef, ...]
  retention: RetentionPolicy

ExecutionCorrelation
  agent, environment                  # "production" (dev_loop.py:69) or "shadow"
  temporal_workflow_id                # dev-loop-mctlhq-<repo>-<number>
  temporal_run_id | None
  argo_workflow_name | None
  target_repository_sha
  definition_version, definition_content_hash
  profile_version,    profile_content_hash
  release_revision

StepRef        parent_snapshot_id, step, sequence
ContextStrategy name, version, ranker_name | None, ranker_version | None
ContextBudget  max_sources, max_bytes, max_bytes_per_source,
               used_sources, used_bytes, truncated
EvidenceRef    evidence_id, kind
RetentionPolicy class ("telemetry"|"execution-record"|"gitops"),
                expires_after_days
```

`ContextSource` is the provenance descriptor — the heart of the contract:

```
source_id       stable within the snapshot ("s1", "issue", ...)
kind            github-issue | github-issue-comment | github-pr |
                target-repo | gitops-file | proposal-dir |
                loki-logs | incident | inline-template
locator         non-secret, structured address:
                https://github.com/mctlhq/mctl-agents/issues/264
                git+https://github.com/mctlhq/mctl-agents@<sha>
                loki://team-admins/mctl-api
                mctl-incident://6ab54770
selector        what slice was taken: {"mode": "agent-directed"} |
                {"lines": 50, "since": "1h"} | {"path": "CLAUDE.md"}
content_hash    "sha256:..." of the bytes ACTUALLY placed in context
byte_count      int
retrieved_at    ISO-8601
freshness       observed_at, max_age_seconds | None,
                staleness: fresh|aging|stale|unknown
trust           tier: authoritative|corroborated|reported|untrusted,
                rationale_code
selection       rank:int, score: float|None, strategy_step, reason_code,
                included: bool
redaction       applied: bool, rules: tuple[str,...], dropped_bytes: int
```

**Never a payload field.** The schema has no place to put one; `from_dict`
rejects unknown keys so a future caller cannot smuggle one in.

### 2. Identity, immutability and hashing

`content_hash` uses the existing `"sha256:"`-prefixed convention
(`resolver.py:301`) over `json.dumps(payload, sort_keys=True,
separators=(",", ":"))` of every field except `content_hash`, `snapshot_id`
and `created_at`. Excluding the timestamp is what makes the hash a statement
about *content*, so re-assembling identical inputs yields an identical id —
the property `tests/test_resolver.py`-style determinism tests can assert
without freezing the clock. `seal()` is the only constructor that fills
`content_hash`/`snapshot_id`; there is no mutator. The ADR fixes one small
inconsistency inherited from the resolver: `skill_hashes` at
`resolver.py:894` emits bare hex without the `sha256:` prefix every other hash
in that file carries — `ContextSnapshot` mandates the prefixed form everywhere
and says so, rather than silently forking a second convention.

### 3. Per-execution and per-step: both, via parent reference

A root snapshot has `step: None`. A step snapshot carries
`StepRef(parent_snapshot_id, step, sequence)` and must repeat the *identical*
`execution` block; `validate()` enforces that. This answers the issue's
question without choosing a side: DevLoop's investigate/implement/review-fix
phases (`dev_loop.py:534-539, 596-683, 991`) each get their own snapshot
chained to the execution root, while a single-step agent emits exactly one.

### 4. Correlation with execution identity

The `execution` block is deliberately a superset of what exists today:
`temporal_workflow_id` matches `workflow_id_for` (`issue_ref.py:30`) and the
value `_record` already sends (`dev_loop.py:327-336`); `argo_workflow_name`
matches `ExecutionRecord.argo_workflow_name`; the four version/hash pins and
`target_repository_sha` are copied straight off `ExecutionPlan`
(`resolver.py:237-256`). That makes the join key "the fields both sides already
have", not a new correlation id. It also closes, for context, the gap
`state.py:36-41` documents: the target SHA is recorded on the snapshot even
though no CWFT exposes it as a workflow output, because the investigator
already computes it locally (`run_issue_investigator.py:105`).

### 5. Boundary rules — normative and testable

| Concern | Owner | What ContextSnapshot does |
|---|---|---|
| Capability eligibility (#242) | `ExecutionProfile.tools` / `permissions` (`resolver.py:174-181`) | May record which capability produced a source (`kind`, `locator`). Never widens eligibility. |
| Authorization (#197) | Policy checkpoints + provider-side enforcement | Nothing. No allow/deny field exists; no policy path may import this module. |
| Evidence (#199) | Evidence store | `evidence_refs: {evidence_id, kind}` only. No payload, no duplication. |
| Traces (#195) | Trace/telemetry | Exports `snapshot_id`, `content_hash`, strategy/ranker versions, counts and byte totals as attributes. Never locators containing free text, never payloads. |

Two tests make "relevance is not authorization" executable rather than
aspirational: a field-name assertion (no `allow`/`deny`/`permit`/`grant`/
`authorized` token anywhere in the serialized schema, including nested
dataclasses) and an import-direction assertion in the style of
`tests/test_worker_isolation.py` (a subprocess import of the snapshot module
pulls in stdlib only; no policy module imports it).

### 6. Budget, freshness, trust vocabularies

- **Budget is assembly-side and model-independent**: sources and bytes, not
  tokens. Rationale recorded in the ADR: token counts depend on a tokenizer
  and model that `config/model-policy.yaml` may change under a snapshot, which
  would make a historical budget uninterpretable, and the repo has no
  tokenizer dependency. A token-denominated budget is explicitly deferred; the
  schema can add `max_tokens` later as an optional field without an
  `apiVersion` bump, exactly as `DevLoopResult` grew fields by default.
- **Freshness** is `fresh | aging | stale | unknown`, defaulting to `unknown`
  when no `max_age_seconds` is declared. A Loki tail is `fresh` with
  `max_age_seconds: 3600`; a repo clone is `fresh` at its SHA; a six-week-old
  incident record is `aging` or `stale`.
- **Trust** is descriptive of origin only: `authoritative` (GitOps catalog,
  registry, repo content at a pinned SHA), `corroborated` (platform telemetry
  such as Loki or an incident record), `reported` (human-authored platform
  state, e.g. a maintainer comment), `untrusted` (arbitrary third-party text —
  a GitHub issue body). The last tier is not new policy: it is the existing
  behaviour of `_neutralize_prompt_tags` (`run_issue_investigator.py:1086`) and
  the untrusted-DATA prompt wrapper (1136), finally given a name in the data
  model. The ADR states in one sentence that raising a tier grants nothing.

### 7. Retention and redaction

Three retention classes, each mapped to an existing store:
`telemetry` (traces/metrics, shortest, hashes and counts only),
`execution-record` (mctl-api, outlives Temporal/Argo retention, the durable
statement — consistent with ADR 007's source-of-truth table,
`docs/adr/007-...:215-224`), `gitops` (only when a snapshot is committed
alongside a proposal; longest-lived and therefore most restricted).
Redaction is applied **before** hashing, so `content_hash` describes the bytes
the model actually saw and the snapshot never needs the raw payload to be
verifiable. `redaction.rules` records rule ids (not matched text) and
`dropped_bytes` records volume.

### 8. Worked investigator example

`tests/fixtures/context/investigator-snapshot.json`: one sealed snapshot for
`issue-investigator` on `dev-loop-mctlhq-mctl-agents-264`, with four sources —
the GitHub issue (`untrusted`, `fresh`), the target repo at
`target_repository_sha` with `selector.mode: agent-directed`
(`authoritative`), a Loki window `loki://team-admins/mctl-api` with
`{"lines": 50, "since": "1h"}` (`corroborated`, `fresh`), and an incident
record `mctl-incident://6ab54770` (`corroborated`, `aging`) — plus one
`included: false` candidate with `reason_code: budget-exhausted`, one
`evidence_ref`, and a filled budget block. It is asserted by a round-trip test
and a hash-stability test, so the example is executable documentation rather
than prose. Checked-in fixture data is rare here — `tests/fixtures/histories/`
is the only precedent and `tests/test_resolver.py` builds its documents from
Python dict helpers instead — so the ADR states why a checked-in golden is
right for this one case: the fixture *is* the worked example the issue asks
for, and a golden hash is the only way a round-trip test can detect a silent
canonicalization change.

A further gap this example makes visible, and does not fix: nothing in the
repo redacts anything today. `grep` for a redact/sanitize/mask/scrub helper
returns no production hit; `_neutralize_prompt_tags` strips delimiter tags
only, and `_audit_pre_tool_use` (`orchestrator/options.py:123-141`) prints
whole Bash commands verbatim. The `redaction` block is therefore a contract
for a redactor that does not exist yet, which the ADR must say plainly rather
than imply a capability.

## Alternatives

1. **Extend `ExecutionPlan` with context fields instead of a new type.**
   Rejected: `ExecutionPlan` is resolved *before* submission from committed
   files and is pinned by publish-time hashes; context is gathered *during*
   execution from mutable external systems. Merging them would put a
   runtime-varying, per-step, possibly-large structure inside the one object
   ADR 007 defines as "created once and never follows later promotions"
   (`docs/adr/007-...:222`), and would force a plan re-materialization per
   step. The snapshot instead *quotes* the plan's pins in its `execution`
   block, preserving one-way reference.
2. **Store retrieved payloads in the snapshot (or in traces) so a run is fully
   replayable.** Rejected: the issue forbids it, and the repo's own hardening
   agrees — issue bodies are untrusted text, Loki tails routinely contain
   tokens and PII, and `state.py`/`registry.py` payloads already go to mctl-api
   over the network. Hash + locator + selector + byte count gives auditability
   and correlation at a fraction of the blast radius. The cost is honest:
   verification requires re-fetching the source, and a mutated source is
   detectable (hash mismatch) but not recoverable.
3. **Hash pre-redaction bytes so the "true" source is identified.** Rejected:
   it would make `content_hash` unverifiable by anyone holding only the
   snapshot (the raw bytes are, by design, never stored), and it decouples the
   hash from what the model actually saw — the thing a reader of a bad proposal
   needs to reconstruct. `redaction.applied`/`rules`/`dropped_bytes` preserve
   the fact that removal occurred.
4. **Model context selection as a policy input ("only surface what the profile
   permits, and treat surfacing as permission").** Rejected explicitly and
   named in the ADR as the anti-goal: it would make a ranker a privilege
   escalation surface and put an LLM-influenced score on the authorization
   path. Eligibility stays in `ExecutionProfile`/#242; enforcement stays with
   #197 and the providers, exactly as ADR 007 already rules for `tools`
   (`docs/adr/007-...:106-110`).

## Platform impact

- **Migrations:** none. No mctl-api table, no GitOps schema, no manifest field
  changes. `agents/_manifests/*/agent.yaml`, `orchestrator/resolver.py` and
  every workflow are untouched. The new module is imported by tests only until
  a follow-up wires a producer.
- **Backward compatibility:** additive by construction. Optional fields are
  added with dataclass defaults, the convention `dev_loop.py:240,246` and
  `pr_state.py:60-61` already rely on for Temporal payload evolution.
  `apiVersion` bumps only for a breaking change; `strategy.version` and
  `ranker.version` absorb configuration changes without one. Unknown
  `apiVersion` fails loudly (`manifest.py:135-143` precedent).
- **Resource impact:** negligible. A sealed snapshot is a few kilobytes of
  primitives; one sha256 over that JSON per seal. Because payloads are
  excluded, snapshot size is bounded by source *count*, not source size.
  Stdlib-only imports keep the 256Mi Temporal worker (ADR 008 context,
  `docs/adr/008-...`) unaffected.
- **Risks and mitigations:**
  - *The contract is written and then ignored by the retrieval follow-up.*
    Mitigated as ADR 007 mitigated it: the ADR names which decisions are
    normative and may not be reopened, and the schema module plus fixtures are
    the executable form of those decisions.
  - *Snapshots become a covert evidence or payload store.* Mitigated by
    `from_dict` rejecting unknown keys, a max-length bound on `locator` and
    `selector` values, and a test asserting no field accepts free-form content
    beyond those bounds.
  - *Relevance drifts into authorization.* Mitigated by the field-name and
    import-direction tests above, plus an explicit non-negotiable sentence in
    the ADR.
  - *Hash instability makes ids meaningless.* Mitigated by excluding
    `created_at` from the hash, canonical `sort_keys` JSON, and a golden
    fixture whose hash is asserted byte-for-byte.
  - *Two prompt-hash algorithms already disagree in this repo*
    (`tools/publish_agent_release.py` length-prefixes its blobs;
    `resolver._hash_prompt_source`, `resolver.py:722-753`, does not).
    Mitigated by this contract defining exactly one canonical-JSON hash rule
    for snapshots and stating that it does not attempt to reconcile the
    existing two.
- **Security:** the snapshot is a strictly non-authoritative, payload-free
  description. Provider-side authorization (GitHub, mctl MCP, Kubernetes,
  Loki) remains the only enforcement, unchanged by this proposal.
