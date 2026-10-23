# Design: issue-210-feat-roadmap-spikedefinition-v1alpha1-co

## Current state

- `roadmap/schemas/epic-definition.schema.json` (`$id`
  `https://mctl.ai/schemas/roadmap/epic-definition-v1alpha1.json`) is the only
  authored-manifest schema. `kind` is `const: EpicDefinition`; `issueRef`
  (`repository` pattern `^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$`, `number >= 1`)
  and `localId` (DNS-label pattern, max 63) live in its local `$defs`.
- `roadmap/scripts/validate.py`:
  - `DEFAULT_SCHEMA` = the epic schema, `DEFAULT_EPICS` = `roadmap/epics`.
  - `_load_schema` (runs `check_schema`), `_load_manifest` (`yaml.safe_load`,
    root must be a mapping), `schema_errors(document, schema)` builds a bare
    `Draft202012Validator(schema)` and renders `$.a.b[0]: message` via `_json_path`.
  - `issue_key` / `canonical_repository` are the shared case-insensitive issue
    identity; `issue_label` renders authored spelling.
  - `semantic_errors` (epic graph invariants), `validate_document` (schema first,
    semantics only if schema-clean), `corpus_errors(documents)` (unique epic
    `metadata.name`, globally unique issue bindings via `_document_bindings`).
  - `main`: one `--schema` for every file, exit 0 all pass, 1 any `FAIL`, 2 for
    schema-load error or no manifests.
- `validate` is imported as a library by `reconcile.py` (`validate_corpus` uses
  `_manifest_paths`, `_load_schema(DEFAULT_SCHEMA)`, `validate_document`,
  `corpus_errors`), `plan.py`, `apply.py`, `ready.py`, `health.py`, `publish.py`
  (`DEFAULT_SCHEMA`, `_load_schema`, `schema_errors`), `completion.py`, and
  `github_graph.py` (`_json_path`, `issue_key`). Every epic schema validation goes
  through `validate.schema_errors`; other `Draft202012Validator(...)` sites
  (`github_graph.py`, `publish.py`, `ready.py`, tests) validate other,
  self-contained schemas.
- `roadmap/tests/test_validate.py` loads the epic schema JSON and calls
  `validate.validate_document`; it asserts `main` returns 0 / 1 / 2.
  `roadmap/tests/mutations.py` holds pure deep-copy mutators of
  `GitHubGraphSnapshot` fixtures (`drop_parent_edge`, `set_state`, ...) plus
  manifest helpers (`unbind`).
- `.github/workflows/roadmap-validate.yml` runs
  `python3 roadmap/scripts/validate.py roadmap/epics`, offline fixture replays,
  and `unittest discover -s roadmap/tests -p 'test_*.py'`. Its `paths` filter is
  `roadmap/**`, so `roadmap/spikes/**` already triggers it.
- `roadmap/README.md` "Validation" describes three layers (schema, per-manifest
  semantics, corpus).
- `roadmap/requirements.txt` pins `jsonschema==4.25.1`, which resolves `$ref`
  through the `referencing` library: a cross-file `$ref` only resolves if the
  validator is constructed with a `registry=` that contains the target.
- Existing epic bindings of spikes: `enterprise-mcp.yaml` `compatibility-spike`,
  `edge-ai-android.yaml` `feasibility-spike` (`mctl-agents#652`),
  `agent-governance-decision-assurance.yaml` `decision-assurance-spike`. None of
  the five pilot issues (`mctl-agents#746`, `#747`, `#757`, `#655`,
  `.github#209`) is bound anywhere in `roadmap/epics/` (grep on `number:`).
- `roadmap/spikes/` and `docs/spikes/655-*` do not exist in this repository;
  `docs/spikes/` holds only `agent-governance-decision-assurance.md`.

Deployed state checked:

- No deployed service is involved: the change is confined to schemas, an offline
  CLI, manifests, tests and a CI workflow in `mctlhq/.github`. No mctl MCP tool and
  no `$MCTL_GITOPS_ROOT` service path is relevant, so none was read.
- `gh issue view` (GET) on the pilot issues: `mctl-agents#746`, `#747`, `#757` and
  `.github#209` are OPEN, authored by `mashkovd`; `mctl-agents#655` is CLOSED
  (`COMPLETED`, 2026-10-16T17:57:08Z) with a 2026-10-17 owner comment "the
  evidence-based decision stays ADAPTER_ONLY".
- `gh api repos/mctlhq/mctl-agents/contents/docs/spikes` lists
  `655-openspec-contract.md`, `659-openspec-grammar.md`,
  `661-canonical-capabilities.md`; the 655 report names `ADAPTER_ONLY` (chosen) and
  `ADOPT_CONTRACT` (rejected) as the verdict vocabulary.
- Not observed: the outcome vocabularies and dates for #747, #757 and
  `.github#209` (issue bodies not fully read here), and whether anything outside
  this repo loads `epic-definition.schema.json` (see Open questions in
  requirements.md).

## Proposed solution

### 1. Shared schema: `roadmap/schemas/common.schema.json`

New file, `$id` `https://mctl.ai/schemas/roadmap/common-v1alpha1.json`, holding
`$defs.issueRef`, `$defs.localId` and `$defs.name` (the `metadata.name` pattern,
identical to `localId`). The epic schema keeps its `$defs.issueRef` / `$defs.localId`
names as thin wrappers (`{"$ref": "common-v1alpha1.json#/$defs/issueRef"}`), so every
internal `#/$defs/...` reference in the epic schema is unchanged and its error
messages stay identical (the wrapper produces the same leaf errors at the same
instance path).

`validate.py` gains a module-level `SCHEMA_REGISTRY`
(`referencing.Registry().with_resource(...)` built from every
`roadmap/schemas/*.schema.json` by `$id`, Draft 2020-12), and `schema_errors`
constructs `Draft202012Validator(schema, registry=SCHEMA_REGISTRY)`. Because all
epic-schema validation in `plan.py`, `apply.py`, `reconcile.py`, `ready.py`,
`health.py` and `publish.py` already goes through `validate.schema_errors`, this is
the single place that needs to know about cross-file references. `_load_schema` is
unchanged (`check_schema` does not resolve references). A `--schema` override that
`$ref`s the common `$id` keeps working; one that does not is unaffected.

### 2. Spike schema: `roadmap/schemas/spike-definition.schema.json`

`$id` `https://mctl.ai/schemas/roadmap/spike-definition-v1alpha1.json`,
`additionalProperties: false` at every level:

- `apiVersion: const roadmap.mctl.ai/v1alpha1`, `kind: const SpikeDefinition`.
- `metadata`: `name` (common `name`), `owner` (an `owner/repo` repository, same
  pattern as `issueRef.repository`, because `evidence.report` is a path in the
  owner repository), optional `labels` (unique strings).
- `spec` required: `title`, `question`, `lifecycle`
  (`proposed | parked | active | decided | archived`), `github.issue` (common
  `issueRef`), `outcomes`.
- `spec.outcomes`: array, `minItems: 2`, `uniqueItems`, items
  `^[A-Z][A-Z0-9_]*$`.
- Optional: `epic` {`name` (common `name`), `workItem` (common `localId`)}, both
  required when present; `activation` {`trigger` (non-empty string, required),
  `reviewBy` (date)}; `timebox` {`decisionBy` (date, required)}; `evidence`
  {`report`: relative path string, `^(?!/)(?!.*(^|/)\.\.(/|$)).+$`};
  `execution` {`devloop`: boolean}; `decision` {`verdict` (outcome pattern),
  `decidedAt` (date), `decidedBy` (GitHub login pattern), optional `followUps`
  (array of common `issueRef`, `uniqueItems`)}, with `verdict`, `decidedAt`,
  `decidedBy` required.
- `$defs.date`: `type: string`, `pattern ^\d{4}-\d{2}-\d{2}$`, `format: date`
  (format is advisory in jsonschema; the semantic layer parses it).
- Lifecycle conditionals are expressed in the schema with `allOf` / `if` / `then`
  so any schema-only consumer gets them too:
  `lifecycle == parked -> required activation`;
  `lifecycle == active -> required timebox`;
  `lifecycle == decided -> required decision`;
  `lifecycle != decided -> not required decision`.
  `activation.trigger` and `timebox.decisionBy` are themselves required inside
  their objects, so "parked without trigger" fails either as missing `activation`
  at `$.spec` or missing `trigger` at `$.spec.activation`.

Observed state (issue state, `.status.yaml`, comments, PRs) has no field, so
`additionalProperties: false` is what rejects it.

### 3. YAML dates

`yaml.safe_load` turns an unquoted `2026-12-01` into a `datetime.date`, which JSON
Schema would reject as "not of type string", while the issue's own example is
unquoted. `_load_manifest` normalises: a `datetime.date` (not `datetime`) value is
replaced by its `isoformat()` string, recursively. A `datetime.datetime` is left
alone and so fails the `date` pattern. Epic manifests contain no dates, so their
loaded value is unchanged; digests in `reconcile.py` hash raw bytes and are
unaffected. Pilot manifests quote their dates anyway, for portability to other
YAML loaders.

### 4. `validate.py` kind dispatch and spike semantics

- Constants: `SPIKE_SCHEMA = ROOT/"schemas"/"spike-definition.schema.json"`,
  `DEFAULT_SPIKES = ROOT/"spikes"`, `KINDS = ("EpicDefinition", "SpikeDefinition")`.
  `DEFAULT_SCHEMA` keeps meaning the epic schema (eight importers depend on it).
- `kind_error(document) -> str | None`: `$.kind: unsupported kind 'X'; expected one
  of EpicDefinition, SpikeDefinition` (also for a missing or non-string kind).
- `spike_semantic_errors(document) -> list[str]` (on a schema-valid document):
  - verdict not in outcomes ->
    `$.spec.decision.verdict: 'X' is not one of spec.outcomes [A, B]`;
  - calendar validity of every date (`date.fromisoformat`), e.g. `2026-02-30` ->
    `$.spec.timebox.decisionBy: '2026-02-30' is not a calendar date`;
  - `followUps` canonical duplicates (via `issue_key`, mirroring the epic
    `externalDependsOn` dedupe) and self-reference to `spec.github.issue`.
  Lifecycle/decision coupling is enforced by the schema conditionals; the semantic
  layer does not duplicate it.
- `validate_spike_document(document, schema)`: schema first, semantics only if
  schema-clean, same as `validate_document`.
- `validate_manifest(document, schemas: dict[str, dict]) -> list[str]`: kind
  dispatch to `validate_document` (epic, unchanged) or `validate_spike_document`.
  `validate_document` keeps its signature and epic-only meaning, so
  `reconcile.validate_corpus` and the existing tests are untouched.
- `corpus_errors(documents)`: partitions by `kind`. The epic part is exactly
  today's code over epic documents only (names and bindings), so an epics-only
  corpus yields byte-identical messages. A new `_spike_corpus_errors(epics, spikes)`
  adds:
  - duplicate spike `metadata.name` across spike manifests (spike names are their
    own namespace; an epic and a spike may share a name);
  - duplicate spike issue binding across spike manifests:
    `GitHub issue R#N is bound by more than one SpikeDefinition: <path>, <path>`;
  - spike issue equal to an epic root issue:
    `$.spec.github.issue: R#N is the root issue of EpicDefinition <name> (<path>)`;
  - spike issue bound as an epic work item `E/W` while `spec.epic` is absent or
    names a different pair:
    `$.spec.epic: R#N is bound by EpicDefinition E work item W (<path>); declare spec.epic {name: E, workItem: W}`;
  - declared `spec.epic` that does not resolve: unknown epic name, unknown work
    item, work item unbound, or work item bound to a different issue, each with
    its own `$.spec.epic...` message. If the named epic manifest exists but failed
    its own validation, the message says so instead of "unknown epic", so an epic
    error is not misreported as a spike error.
  Spike issue bindings are deliberately not added to the epic global binding map:
  a spike bound inside an epic is the intended ownership edge, not a collision.
- `main`: default paths `[DEFAULT_EPICS, DEFAULT_SPIKES]`; `--schema` keeps
  overriding the EpicDefinition schema (backward compatible), new `--spike-schema`
  overrides the SpikeDefinition schema; both are loaded up front (exit 2 on load
  failure as today). Each file is loaded, kind-dispatched, and valid documents of
  both kinds go into `corpus_errors`. Output format (`PASS`/`FAIL` + `  - msg`) and
  exit codes (0 / 1 / 2) are unchanged. "no EpicDefinition manifests found" becomes
  "no roadmap manifests found".
- Module docstring updated to describe both kinds.

### 5. Pilot manifests: `roadmap/spikes/`

| file | issue | lifecycle | notes |
| --- | --- | --- | --- |
| `portable-runtime.yaml` | `mctlhq/mctl-agents#746` | active | outcomes `NO_RUNTIME`, `THIN_ADAPTER`, `PORTABLE_RUNTIME_RUST`, `PORTABLE_RUNTIME_OTHER`; `timebox.decisionBy`; `execution.devloop: true` |
| `agent-scale-coordination.yaml` | `mctlhq/mctl-agents#747` | parked | `activation.trigger` "next GitHub article in the agent-scale Git infrastructure series", `reviewBy` |
| `duet-sessions.yaml` | `mctlhq/mctl-agents#757` | proposed | outcomes from the issue body |
| `security-finding-lifecycle.yaml` | `mctlhq/.github#209` | active | `metadata.owner: mctlhq/.github`, `timebox.decisionBy` |
| `openspec-contract.yaml` | `mctlhq/mctl-agents#655` | decided | outcomes `ADAPTER_ONLY`, `ADOPT_CONTRACT`; `decision {verdict: ADAPTER_ONLY, decidedAt: "2026-10-17", decidedBy: mashkovd}`; `evidence.report: docs/spikes/655-openspec-contract.md`; `execution.devloop: true` |

No pilot declares `spec.epic`, because none of these issues is a work item of any
epic today; declaring one would require the cross-kind rule to fail. Values the
issue does not give (other outcome lists, dates) are taken from each issue body
and flagged in the PR for the owner.

### 6. Tests

New `roadmap/tests/test_validate_spike.py` (keeps `test_validate.py` focused on
epics), with a minimal valid `_base()` spike and one test per rule, asserting the
exact message/path; plus corpus tests that write temporary epic + spike manifests
and assert `corpus_errors` / `main` results, and a test that every file in
`roadmap/spikes/` validates together with `roadmap/epics/`. Pure manifest mutators
(`set_lifecycle`, `drop_path`, `set_verdict`, `bind_spike_epic`, ...) go in a new,
clearly separated section of `roadmap/tests/mutations.py`, so the "converged corpus
green, one mutation one red, restore green" discipline applies to the validator
too. Snapshot mutators for the slice 2 diff types are not added.

A regression test asserts that `corpus_errors` over the current `roadmap/epics/`
corpus returns `{}`, and that a crafted epics-only corpus produces exactly the old
message strings. Existing `test_validate.py` tests stay green with no edits.

### 7. README and CI

- `roadmap/README.md`: Layout gains `spikes/`, `schemas/common.schema.json`,
  `schemas/spike-definition.schema.json`; Validation command becomes
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes`; a new
  "SpikeDefinition v1alpha1" section documents fields, lifecycle meanings
  (`archived` vs `decided`), the rules, the cross-kind invariants, the date
  normalisation, and states that the drift family is slice 2.
- `.github/workflows/roadmap-validate.yml`: the validate step becomes
  `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` (step name
  "Validate roadmap manifests"). All reconcile/health/ready/plan/apply steps keep
  `--corpus roadmap/epics`.

## Alternatives

1. **Spike schema `$ref`s the epic schema's `$defs` directly**
   (`epic-definition-v1alpha1.json#/$defs/issueRef`), leaving the epic schema byte
   identical. Lowest risk to epic consumers, but makes the spike contract depend
   on the epic contract's internals; the next kind would repeat the problem.
   Dropped in favour of a neutral `common.schema.json`. It remains the fallback if
   an external consumer of the standalone epic schema is found (Open questions).
2. **Copy `issueRef` / `localId` into the spike schema.** No registry needed, but
   two definitions of issue identity can drift apart, exactly what `issue_key` was
   introduced to prevent. Dropped.
3. **Make `validate_document` itself dispatch on `kind`.** Fewer new functions, but
   `reconcile.validate_corpus` passes the epic schema explicitly and depends on
   epic-only semantics; silently accepting spike documents there would let a spike
   leak into reconcile/publish. Dropped; a separate `validate_manifest` is explicit.
4. **All lifecycle rules in the semantic layer only.** Simpler messages, but a
   schema-only consumer (a future mctl-api read model) would accept a parked spike
   without a trigger. Dropped; only what JSON Schema cannot express (verdict
   membership, calendar dates, canonical-identity dedupe, cross-kind) is semantic.

## Platform impact

- Migrations: none. No existing manifest changes; the epic schema changes only
  structurally (wrappers around shared `$defs`), so every current epic still
  validates with the same messages.
- Backward compatibility: `DEFAULT_SCHEMA`, `validate_document`, `semantic_errors`,
  `schema_errors` signature, `corpus_errors` signature and its epics-only output,
  CLI output format and exit codes are preserved. `validate.py` with no arguments
  now also validates `roadmap/spikes` (intentional).
- Reconcile, health, ready, plan, apply and publish are not touched and still run
  over `roadmap/epics`; spikes do not enter the RoadmapPublication in this slice.
- Risk: the `referencing` registry. If a schema is loaded by a path other than
  `validate.schema_errors` and contains the cross-file `$ref`, it fails with an
  unresolvable reference. Mitigation: grep shows all epic-schema validation goes
  through `schema_errors`; the full existing suite (`test_reconcile`, `test_plan`,
  `test_apply`, `test_publish`, `test_ready`, `test_health`) exercises those
  paths and must stay green; the CI fixture-replay steps run every script.
- Risk: an external consumer reading `epic-definition.schema.json` standalone.
  Mitigation: recorded as an open question; Alternative 1 is a one-file revert.
- Resource impact: negligible (five small YAML files, one extra schema load).
- No GitHub access in validation; the CI job keeps `permissions: {}`.
