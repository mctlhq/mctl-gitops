# Design: issue-796-spike-devloop-evaluate-rea-as-investigat

## Current state

How the investigator reaches tools and records evidence today:

- `orchestrator/run_issue_investigator.py` builds the prompt (`_build_prompt`) and
  options. `orchestrator/options.py` `build_issue_investigator_options` grants
  `Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, Bash` plus
  `_mctl_tool_globs()`. Its only MCP server is `mctl_mcp_config(always_load=True)`.
  No third-party MCP server is wired in, and REA appears nowhere in the repo.
- ADR 017 capability discovery (#242) lives in `orchestrator/capability_gateway.py`
  and is selected by `_capability_mode()` (`ISSUE_INVESTIGATOR_CAPABILITY_MODE`).
  It replaces eager `mcp__mctl__*` schemas with three gateway tools over a sealed
  `CapabilitySet`. It covers only the mctl provider; there is no third-party
  provider in it today. `tools/capability_bench.py` (`schema-bytes`, `compare`)
  and `docs/benchmarks/capability-discovery.md` are the established way to
  measure first-turn schema bytes and token usage.
- Evidence primitives:
  - `orchestrator/context_snapshot.py` (ADR 009): `ContextSource` has `kind` from
    the closed `SOURCE_KINDS`, `locator`, `selector`, `content_hash`,
    `byte_count`, `Freshness.observed_at` and `Trust.tier` from
    `authoritative|corroborated|reported|untrusted`, which "grants nothing". It
    has no payload field. `EvidenceRef` is `{evidence_id, kind}`. Its
    `RetentionPolicy` is bounded.
  - `orchestrator/execution_evidence.py` (ADR 018 Amendment 2): `ArtifactRef`
    (name, kind, content_hash), `ToolCallRef` (kind, name, action_digest, status,
    never arguments or results), `Provenance.authority` with
    `observed > derived > asserted`, and `Gap` with `observation_failed`, so
    "could not observe" is never silent.
  - `SOURCE_KINDS` has no member for a local binary-analysis result, and
    `SUBJECT_KINDS` (`pull_request, issue, branch, release, work_item`) has no
    member for a binary target. These are the two candidate gaps the spike must
    confirm or refute.
- Model selection: `config/model-policy.yaml` defines only Claude profiles
  (`cheap` is `claude-haiku-5-5`, `balanced` is `claude-sonnet-5-5`). The
  investigator's real model comes from the `ISSUE_INVESTIGATOR_MODEL` override.
  No non-Claude provider is configured anywhere in `orchestrator/`, `config/` or
  `tools/`.
- Spike conventions: reports live in `docs/spikes/<n>-<slug>.md` with artefacts
  in `docs/spikes/<n>/`. Examples are 707 (bench script, `results.json`) and 746
  (measurements, decision tokens, "verdict stays with the owner"). Report-guard
  tests such as `tests/test_spike_707_report.py` check the `STATUS: DRAFT`
  marker, the token set and that no gate changed. Harnesses such as
  `tools/semantic_decision_spike.py` and `tools/capability_bench.py` keep I/O in
  thin wrappers around pure, unit-tested functions, and refuse live mode without
  an explicit flag. `orchestrator/spike_issue.py` makes the implementer emit
  `Refs` for spike titles.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml:883`:
  `ISSUE_INVESTIGATOR_MODEL=claude-opus-5-5`. This is the active Claude path to
  probe; it must be re-read at run time.
- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/issue-investigator-default/profile.yaml`:
  `spec.version: "1.5.1"`, `tools` lists `mcp__mctl__*` and no REA entry, and
  `modelPolicyRef.legacyEnvOverride: ISSUE_INVESTIGATOR_MODEL`.
- `$MCTL_GITOPS_ROOT/services/` and `tenants/`: grep for `hetzner|rea.tools|morluto`.
  The only "Hetzner" hits are storage comments ("billed Hetzner volume") in
  `tenants/admins/values.yaml` and `tenants/labs/values.yaml`, plus unrelated
  mentions in `services/labs/mctl-telegram*`. No #791 open-model endpoint was
  observed. This is "could not observe", not "absent". See Open questions in
  requirements.md.
- No mctl MCP calls were needed. The spike touches no deployed service.

## Proposed solution

This is a research-only change set. The report carries the decision; nothing in
the runtime path changes. All artefacts live under the spike's own paths.

1. **Corpus** (`docs/spikes/796/fixtures/`):
   - `native-codec/`: a small C program built by a pinned `Makefile` (`-O2`, then
     stripped). Its hidden behaviour is a custom record checksum and field
     ordering inside a serializer, e.g. a rotate-xor checksum seeded from a
     constant table.
   - `packaged-app/`: an Android APK built with a pinned Gradle wrapper, or a JVM
     jar if the toolchain is unavailable (Open question). Its hidden behaviour is
     an obfuscated-by-structure feature-flag resolution order.
   - Optional `js-bundle/`: a minified Node bundle, included only if REA exposes a
     distinct JS path in the pinned version.
   - Each fixture has `oracle.yaml` listing facts as `{id, statement, kind:
     observed|inferable}`, a `build.sh` that rebuilds deterministically and prints
     the artefact's sha256, and a `task.md` holding the identical investigation
     question used in every arm. No fixture contains licence, auth, DRM or
     anti-tamper logic. Built binaries are not committed, only their recorded
     digests.

2. **Harness** (`tools/rea_spike.py`, stdlib plus PyYAML, never imported by
   `orchestrator/`). It follows the `tools/semantic_decision_spike.py` pattern:
   - `run --arm baseline|rea-mcp|rea-cli --fixture X --model M [--allow-live]`
     drives one investigation with `claude_agent_sdk` for Claude. REA arms
     register REA's MCP server, or run a fixed allowlist of REA CLI operations
     through Bash. Each run writes one JSONL record: versions, stage results,
     tool calls, usage, wall clock, final answer hash, and a bounded summary
     capped at 4 KiB per REA result. The command refuses to run without
     `--allow-live`.
   - `probe-stages` runs the five compatibility stages as separate sessions with
     fixed prompt text from `docs/spikes/796/stages/`. Each stage is attempted
     once. On a refusal or error it records and stops. There is no retry and no
     rephrasing (invariant 4).
   - `classify(record) -> class` is a pure function mapping the observed
     signals to the six classes in requirements.md:
     - no tool registered: `CLIENT_TOOL_ADMISSION`;
     - schema rejected or context overflow: `MCP_SCHEMA_OR_CONTEXT_FAILURE`;
     - REA non-zero exit or error result: `REA_TOOL_FAILURE`;
     - HTTP/transport error: `PROVIDER_RUNTIME_FAILURE`;
     - an assistant turn that declines with no tool error:
       `MODEL_POLICY_REFUSAL`;
     - anything else: `UNKNOWN`.
     Refusal text is stored verbatim only when the operator passes
     `--store-text`. Otherwise the record keeps a normalized reason plus sha256.
   - `score(record, oracle)` is pure. An operator-filled `grading.yaml` marks each
     final claim as `oracle:<id>`, `unsupported`, or `unknown-acknowledged`, and
     records whether it cites a REA result. The tool computes the metrics table.
     Grading is human, so the report states the grader and that n=1 per arm.
   - `schema-bytes --server rea` reuses `capability_bench`'s counting rule
     (serialized `tools/list` bytes and count) against REA's MCP server.
   - `report RECORDS.jsonl` renders the issue's metrics table and the
     cross-model matrix. Unrun cells render as `not-run (<reason>)`, and
     unobserved values as `unobserved`.
   - Cross-model: `--model` accepts an OpenAI-compatible endpoint only if
     `REA_SPIKE_ALT_BASE_URL` points at an existing #791 path. Without it the
     rows are `not-run`, and no provider code is added.

3. **Evidence-contract evaluation**, recorded in the report. Map one real REA
   result per fixture onto existing primitives:
   - target identity: `ContextSource.content_hash` plus `locator`
     (`fixture://<name>@<sha256>`);
   - operation: `ToolCallRef.name`/`status`;
   - observed versus inferred: `Provenance.authority` `observed` versus `derived`;
   - limitation or unknown: `Gap(observation_failed)` or an explicit
     summary field;
   - trust: `Trust.tier=reported`, meaning context, not authority.
   The report then decides one of two outcomes. Either existing primitives
   suffice, or the smallest extension is needed, expected to be one
   `SOURCE_KINDS` member such as `local-analysis` and nothing else. It is only a
   recommendation for a follow-up issue.

4. **Integration-shape comparison**, from the same runs:
   - direct MCP (arm `rea-mcp`): schema bytes, setup, how missing-REA behaves;
   - thin CLI adapter (arm `rea-cli`): an allowlisted operation set with
     normalized JSON output, which cuts schema cost to one Bash call pattern;
   - none: manual attach.
   Discovery-mode hiding is assessed on paper against ADR 017. Today it serves
   only the mctl provider, so the report states what it would take rather than
   building it.

5. **Report** `docs/spikes/796-rea-investigation-evidence.md`. It covers the
   environment and versions, the duplicate map (#242, #597, #746, #791), the
   corpus and oracle, the metrics table, the stage-by-stage Claude result, the
   cross-model matrix, schema footprint, the MCP-versus-CLI comparison, the
   evidence-contract decision, the setup/data/safety note, the decision (one
   token) and follow-ups. It ships `STATUS: DRAFT` until an operator run's
   records are committed under `docs/spikes/796/results/`.

6. **Guard test** `tests/test_spike_796_report.py`, modelled on
   `test_spike_707_report.py`. It checks four things. The report has either
   `STATUS: DRAFT` or exactly one token from the set. No file under
   `orchestrator/`, `config/` or `agents/_manifests/` changed. Committed results
   hold no file over the byte ceiling and no binary magic (ELF, `PK\x03\x04`,
   `dex\n`). Every oracle file parses. A second file, `tests/test_rea_spike.py`,
   unit-tests `classify`, `score` and `report` against recorded records.

Why this shape: it reuses the spike conventions already used for 707, 746 and
556 and the measurement rule from `capability_bench`. It keeps REA entirely
outside the investigator's runtime path, which honours "no production rollout"
and "no REA fork". It also separates the work the implementer can do (corpus,
harness, tests) from what only a credentialed operator can run.

## Alternatives

- **Wire REA into `build_issue_investigator_options` behind an env flag and run
  the real CWFT.** Dropped. It edits the production options builder and profile
  allow-list, which the spike forbids. It would also need REA and its
  dependencies in the worker image.
- **Extend `CapabilityGateway` to front REA's MCP tools now, to measure lazy
  discovery directly.** Dropped as #242 scope duplication and premature. The
  spike measures the schema footprint and judges hideability on paper. A
  follow-up is filed only if the result is `ADOPT_OPTIONAL_REA_CAPABILITY`.
- **Add a `rea` evidence type or a new `InvestigationEvidence` contract up
  front.** Dropped. The issue requires first checking whether ADR 009/018
  primitives already express it, and a contract without data would be
  speculative.

## Platform impact

- No migrations. No runtime, CWFT, profile, image or model-policy change, so
  backward compatibility is unaffected.
- Resource and cost: operator-run only. Expect about 3 fixtures x 3 arms on
  Claude, plus 5 probe stages, at roughly $1-3 each against subscription quota.
  Open-model runs use #791's existing endpoints if they exist. CI gains only
  pure unit tests and the report guard, with no network, REA or model calls.
- Risks and mitigations:
  - Data leaving the host: only source-owned fixtures are analysed, and binaries
    are never committed, only digests.
  - Accidental jailbreak behaviour: a single attempt per stage, with no
    rephrase path in code; the test asserts the probe has no retry loop.
  - Upstream churn: REA is pinned by commit SHA, and the report is dated.
  - Grading subjectivity: the oracle is defined before runs, the grader is
    named, and n=1 is stated.
  - "Unknown stays unknown": failures become `Gap`-style `unobserved` cells, never
    evidence that a behaviour is absent.
