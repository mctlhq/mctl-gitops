# Spike #796: REA as an investigation evidence provider, and model-policy compatibility

## Context

Issue mctlhq/mctl-agents#796 asks for a time-boxed experiment on REA (Reverse
Engineer Anything, https://github.com/morluto/rea). REA is an open-source MCP and
CLI toolkit for local, evidence-backed inspection of binaries, packaged
applications and runtime behaviour. The question is whether REA makes the DevLoop
issue-investigator's findings more accurate, and its evidence easier to
attribute, on legitimate tasks: interoperability, compatibility and understanding
how an implementation works. It also asks whether current Claude models and
clients finish such workflows or refuse partway. There are reports of refusals.
Treat them as a hypothesis to reproduce. They are not an established policy.

The spike runs only on fixtures that MCTL owns. It changes nothing in
production. It must not duplicate #242/#597 (capability discovery and context
efficiency), #791 (model and provider benchmark) or #746 (portable runtime). It
ends with a report that carries exactly one decision token:
`ADOPT_OPTIONAL_REA_CAPABILITY`, `ADOPT_REA_CLI_ADAPTER_ONLY`, `RESEARCH_ONLY` or
`REJECT`. The issue owner records the verdict. Every commit and PR uses `Refs`,
never `Closes`. `orchestrator/spike_issue.py` already enforces this for the
implementer, because the title matches `SPIKE_TITLE_RE`.

## User stories

- AS the #796 owner I WANT a reproducible, scored comparison of investigations with and without REA on a source-owned fixture corpus SO THAT the adopt/reject decision rests on measured accuracy and evidence quality, not anecdote.
- AS a platform operator I WANT each refusal or failure in a Claude REA workflow pinned to its earliest stage and classified SO THAT I can tell model policy apart from client, schema, tool or runtime faults.
- AS the owner of the investigator's evidence contracts I WANT a decision on whether `ContextSource`/`EvidenceRef` (ADR 009) and `ExecutionEvidence` (ADR 018) can already express REA findings SO THAT no new contract is added unless the experiment proves a gap.
- AS a security reviewer I WANT the spike to inspect only authorized, source-owned targets, without bypassing any protection or refusal, SO THAT the experiment stays inside MCTL's safety and data boundaries.

## Acceptance criteria (EARS)

- WHEN the spike report is published THE SYSTEM SHALL record the exact REA upstream snapshot used: repository URL, commit SHA, package or release version, install method and test date.
- WHEN the corpus is built THE SYSTEM SHALL contain at least two fixtures built from source by the spike itself: one native binary and one packaged application, the second an Android APK if the toolchain is available or otherwise a JVM jar. Each fixture SHALL have a machine-readable oracle listing the true implementation facts. Each fixture SHALL hide one behaviour behind implementation details.
- WHILE any fixture is built or analysed THE SYSTEM SHALL use no third-party, customer or private payload. No fixture SHALL contain or exercise DRM, licence checks, authentication, anti-cheat or access-control logic.
- WHEN a fixture is investigated THE SYSTEM SHALL run the same task text twice, once as a baseline without REA and once with REA. Each run SHALL record oracle facts recovered, unsupported claims, evidence-grounded claims, turns and tool calls, input and output tokens, wall-clock latency, and whether the implementation plan is actionable. Any value that cannot be observed SHALL be recorded as `unobserved`.
- WHEN a REA-assisted run completes THE SYSTEM SHALL record the interface used (MCP or CLI), the REA operations invoked, any evidence IDs REA returned, and whether each final claim cites a concrete REA result or appears as unsupported prose.
- WHEN the Claude compatibility probe runs THE SYSTEM SHALL test the investigator's active Claude path at run time and record the exact model ID, client/SDK version and date. The path was observed as `claude-opus-5-5` via `ISSUE_INVESTIGATOR_MODEL` in `cwft-mctl-agents-investigate.yaml`, but the probe SHALL re-read it at run time. The probe SHALL run the five stages separately: tool discovery, static inspection, multi-step tracing, evidence synthesis, and compatible implementation in the fixture project.
- IF a stage refuses or fails THEN THE SYSTEM SHALL record the earliest failing stage and exactly one class from `MODEL_POLICY_REFUSAL`, `CLIENT_TOOL_ADMISSION`, `MCP_SCHEMA_OR_CONTEXT_FAILURE`, `REA_TOOL_FAILURE`, `PROVIDER_RUNTIME_FAILURE`, `UNKNOWN`. It SHALL store either the verbatim text, where licence and policy allow, or a normalized reason plus a sha256 of the text.
- IF a model refuses on safety grounds THEN THE SYSTEM SHALL NOT retry with a rephrased, decomposed or otherwise altered prompt to get around the refusal. It SHALL record the refusal and stop that stage.
- WHERE a #791 provider path for the owner-selected open models (Kimi K2.7 Code, DeepSeek V4 Flash, GLM 5.2, Qwen 3.6) is available at run time THE SYSTEM SHALL run the same REA-assisted workflow on each available model and record the matrix the issue specifies.
- IF a #791 model path is not available at run time THEN THE SYSTEM SHALL mark that matrix row `not-run` with a reason. It SHALL NOT build a new provider integration for this spike.
- WHEN REA's MCP server is registered THE SYSTEM SHALL record the `tools/list` count and serialized schema byte size, measured the way `tools/capability_bench.py schema-bytes` measures the mctl provider. It SHALL also record whether ADR 017 discovery mode could keep these schemas out of the first-turn context.
- WHEN REA is absent or misconfigured THE SYSTEM SHALL record how each integration shape fails (direct MCP, thin CLI adapter, none) and whether the investigator degrades cleanly.
- WHILE evidence is persisted THE SYSTEM SHALL keep only target digests, operation names, bounded summaries and references. Full binaries, decompiled output and raw REA output over a fixed byte ceiling SHALL NOT be committed.
- WHEN the report is finalized THE SYSTEM SHALL contain exactly one decision token and a decision on the evidence contract: reuse existing primitives, or name the smallest extension. It SHALL also contain a direct-MCP versus CLI-adapter comparison, a setup/data/safety note, a current-state map against #242, #597, #746 and #791, and follow-up issues limited to gaps the experiment proved.
- WHILE the report is not backed by a recorded live measurement run THE SYSTEM SHALL carry a `STATUS: DRAFT` marker and no final decision token.
- WHILE the spike is in progress THE SYSTEM SHALL leave unchanged `orchestrator/`, `config/model-policy.yaml`, every `agents/_manifests/*/agent.yaml`, the mctl-gitops execution profiles and the investigate CWFT.

## Out of scope

- Any production rollout: adding REA to `issue-investigator-default`'s `spec.tools`, to `build_issue_investigator_options` (`orchestrator/options.py`) or to the worker image.
- Reverse engineering third-party software, and bypassing any protection or model safety system.
- Forking or patching REA. Upstream defects are reported upstream.
- Generic model benchmarking (#791), generic MCP context benchmarking (#597), capability-gateway changes (#242) and portable-runtime work (#746).
- Adding a new `SOURCE_KINDS` member, evidence block or contract. The spike may only recommend one.

## Open questions

- #791's provider/runtime path is not in this repository. No non-Claude provider is configured in `orchestrator/` or `config/model-policy.yaml`. In mctl-gitops, "Hetzner" appears only as the cluster's storage provider. Whether any open-model path is usable at run time is therefore unknown. Proceeding: matrix rows are `not-run` unless the operator supplies an existing endpoint.
- Whether an Android SDK/JDK build toolchain is acceptable in the spike's CI or operator environment. Proceeding: build an APK if available, otherwise fall back to a JVM jar, and state which was used.
- The issue allows sending fixture bytes or decompiled output to a model provider only "unless the normal MCTL data policy explicitly permits it". No written data policy was found in this repo. Proceeding: only source-owned fixtures are sent, which is the issue's own corpus definition. The owner should confirm.
- The live runs need REA installed locally, plus Claude credentials and budget. The implementer sandbox cannot provide these. Proceeding: the implementer delivers the corpus, the harness and a draft report. Measurements come from an operator run, the same split `docs/benchmarks/capability-discovery.md` used.
