# Design: issue-655-spike-devloop-evaluate-openspec-compatib

Compatibility target: OpenSpec **v1.14.2**, commit **`f80d860`** (`f80d860fc510ba4f51180c8ddde35b91b32de657`). Only the facts pinned in mctlhq/mctl-agents#655 are used, plus anything the spike verifies itself against that commit.

## Current state

How a proposal is produced and consumed today:

- **Investigator** writes the planning documents. In `orchestrator/run_issue_investigator.py`:
  - `TRIPLET = ("requirements.md", "design.md", "tasks.md")` names the planning documents, and `STATUS_FILENAME = ".status.yaml"` names the execution state.
  - `build_slug` / `resolve_slug` produce `issue-<N>-<kebab-title>`.
  - The agent writes into a staging directory (`_staging_dir`). The orchestrator writes `.status.yaml` (`write_status_yaml`, `status: proposed`, `source`, `control.requires_human_approval: true`, `execution`, optional `context`/`request`).
  - Before publish, `_landed_triplet_defects` checks that all four files are regular files. `_status_disagreements` refuses a published `.status.yaml` whose `status`, `source.*`, `control.requires_human_approval` or `execution.agent` differ from what the orchestrator wrote. This is the main guard against an agent forging approval.
  - The prompt template (`_build_prompt`, around lines 2171-2230) fixes the triplet's section headings. The headings are prompt conventions only. Nothing in code parses the documents' structure.
- **Implementer** reads the documents. `orchestrator/run_implementer.py` tells the sub-agent to "Read spec files from `$PROPOSAL_DIR` ... requirements.md, design.md, tasks.md" (around line 2083), and the review-fix variant does the same (around line 1969). Consumption is whole-file and natural-language. Nothing parses individual criteria or tasks.
- **State and approval.** `orchestrator/proposal_state.py` treats `.status.yaml` as a durable projection with merge-preserving writes (`update_status_file`). `human_approval_satisfied` refuses anonymous approvers (`_ANONYMOUS_APPROVERS`). `execution_authorization` distinguishes `human-approval` from `autonomy-policy`. The approval block records `approved_by` / `approved_at`. It does **not** record a digest of the triplet content.
- **Proposal selection.** `orchestrator/proposal_identity.py` (one live proposal per `issue-<N>-` prefix). `orchestrator/temporal/activities/gitops_state.py` lists proposals by `<service>/proposals/<slug>/.status.yaml` only and states that a proposal's `requirements.md` "is not state".
- **Context assembly.** `orchestrator/context_assembly.py` has `TRIPLET_FILENAMES` with the same three names and feeds prior proposals into context.
- **Shepherd.** `orchestrator/run_shepherd.py::decide(pr, codex_review, now, *, fix_only, ci)` is a pure function. It handles merged/closed first, then draft and wait, then fresh P1/P2 findings plus actionable required checks (`address-review`), then `ci-infra` / `ci-unknown`, then merge on the primary reviewer's verdict. The optional `ci` argument (#411) shows the established pattern for adding a new input: default `None` keeps the decision surface byte-identical.
- **DevLoop.** `orchestrator/temporal/workflows/dev_loop.py` owns the approval park (`wait_condition`), the atomic approve, and the `mctl-agents-approve` flip. Nothing in it reads planning content.
- **Representative proposals (read-only):**
  - `agents-state/mctl-agents/proposals/issue-596-test-agent-platform-add-an-inert-authori` (merged, PR #598): requirements 6,678 B, design 10,610 B, tasks 7,577 B, 24,865 B in total, 10 SHALL lines, standard headings.
  - `issue-516-...` (merged, 35,780 B).
  - `issue-519-...` (merged, 43,251 B).
- **OpenSpec.** No module or test in the repo mentions OpenSpec today. A case-insensitive grep over `*.py` and `*.md` found nothing.

Deployed state checked:
- `$MCTL_GITOPS_ROOT` = `/workdir/mctl-gitops/platform-gitops`. `services/` lists tenants `admins`, `karabu`, `labs`. Workers `mctl-agents-worker`, `mctl-agents-worker-exec` and `mctl-agents-worker-implement` exist under them. The spike changes none of their configuration or images, so their values were not inspected further.
- `agents-state/mctl-agents/proposals/` holds 93 entries. The three proposals above were read (headings, sizes, and `.status.yaml` for issue-596: `status: merged`, `approval.approved_by: mashkovd`, `source.url` = issue 596, `pr` = #598).
- mctl MCP tools were not called. The spike has no deployed-runtime component, so service status, logs and replicas are not relevant here.

## Proposed solution

The spike is a self-contained, test-only prototype plus a decision record. It is not imported by any runner, workflow or activity.

### 1. Prototype package `orchestrator/sdd/` (pure Python, PyYAML only)

- `orchestrator/sdd/__init__.py`. The docstring cites v1.14.2 / `f80d860` and states that the package is a spike, not imported by production code.
- `metadata.py` handles `.openspec.yaml`:
  - `load_change_metadata(dir, *, strict=False) -> ChangeMetadata | None`. A missing file returns `None`.
  - Known keys: `schema` (required), `created` (`YYYY-MM-DD`), `goal`, `affected_areas` (list of str), `initiative` (`{store, id}`, kebab-case, strict, no `x-` keys), `skip_specs`, `retire_capabilities`.
  - Top-level `x-` keys are passed through untouched.
  - An unknown key produces a warning, and an error when strict.
  - `FORBIDDEN_EXECUTION_KEYS` (the `.status.yaml` top-level keys, plus `x-mctl-status`, `x-mctl-approval` and similar) is always an error. This is the MCTL-specific rule that keeps execution state out.
  - `skip_specs: true` while `specs/` contains files is an error.
  - `dump_change_metadata` validates before writing and writes nothing on failure.
- `spec_model.py` parses and renders a capability spec: requirement blocks keyed by name, scenarios per requirement, and duplicate-header detection. It also parses delta files with ADDED / MODIFIED / REMOVED / RENAMED sections, using the assumed `### Requirement:` / `#### Scenario:` / `## <OP> Requirements` grammar. The grammar is isolated in one module with a `GRAMMAR_VERIFIED = False` constant, because the pinned reference does not cover it (see Open questions).
- `apply.py` provides `apply_change(canonical_specs: dict[str, str], deltas: dict[str, str], *, retire_capabilities: bool) -> ApplyResult`. It follows the pinned archive semantics row by row:
  - Order: RENAMED -> REMOVED -> MODIFIED -> ADDED.
  - Cross-section pre-validation.
  - Per-requirement no-ops, aborts and warnings as listed in requirements.md.
  - New-capability rules.
  - Duplicate-header rejection.
  - Name normalization for near-miss detection (casefold + whitespace collapse).
  The function is pure and returns either new specs or an abort with no partial output, which models the rollback-capable transaction. `archive_change(root, change)` claims `archive/YYYY-MM-DD-<change>`, fails if it exists, applies, then moves. It runs on a temporary directory in tests only.
- **MCTL delta choice.** The prototype mirrors `openspec archive` (deterministic, abort on ADDED-with-different-content). It does **not** adopt `/opsx:sync`'s implicit ADDED -> MODIFIED. Silent upgrades hide intent from the approver, and a deterministic gate fits DevLoop's fail-closed posture. The divergence is still encoded as a documented row with a test asserting MCTL aborts.
- `convert.py` handles both directions:
  - `triplet_to_change(proposal_dir, status) -> ChangePackage` and `change_to_triplet(pkg) -> Triplet`.
  - Mapping:

    | Current artifact / section | Candidate target |
    |---|---|
    | requirements.md Context, User stories, Out of scope, Open questions | `proposal.md` |
    | requirements.md EARS acceptance criteria | `specs/<capability>/spec.md` ADDED/MODIFIED requirements; each EARS line becomes a requirement statement plus one scenario (WHEN/THEN) |
    | design.md | `design.md` (verbatim) |
    | tasks.md, including Tests and Rollback | `tasks.md` (verbatim) |
    | `.status.yaml` `source` | `.openspec.yaml` `x-mctl-issue` (url), `x-mctl-repo`, `x-mctl-issue-number` |
    | service and slug | `affected_areas: [<service>]`, `x-mctl-slug` |
    | title | `goal` |
    | investigation date | `created` |
    | everything else in `.status.yaml` | stays MCTL execution state; never copied |

  - The capability name is chosen by the investigator, or by a `--capability` argument in conversion. Existing proposals have no capability concept, which is a measured migration cost.
  - `loss_report()` lists every heading, bullet, EARS line and checkbox in the source with its location in the target. Anything unmapped is reported, never dropped silently.
- `measure.py` reports bytes and approximate tokens (chars / 4, documented as an estimate with no tokenizer dependency) for both representations.
- `verify.py` provides `verify_change(pkg, canonical) -> SpecVerdict` with `outcome in {"pass", "fail", "unknown"}` and findings. The result type has no merge/approve fields.

### 2. Fixtures (`tests/fixtures/sdd/`)

- `metadata/`: valid, unknown-key, `x-` key, `x-` key inside initiative, missing, skip_specs-with-specs, forbidden-execution-key.
- `capabilities/devloop-approval/spec.md`: the canonical spec, derived from behavior in `proposal_state.human_approval_satisfied` and `dev_loop.py`'s approval park (anonymous approver refused, `requires_human_approval` default on, approve signal bound to one issue's workflow id).
- `changes/devloop-approval-content-digest/`: a hypothetical change with:
  - ADDED "Approval records proposal digest";
  - MODIFIED "Anonymous approver refused", adding a scenario;
  - REMOVED a deliberately obsolete fixture requirement;
  - the expected post-archive `spec.md`.
- `delta-rows/<row-id>/`: one minimal canonical + delta + expected outcome per comparison row.
- `roundtrip/issue-596/`: a read-only copy of the issue-596 triplet and a sanitized `.status.yaml` (`source` only), plus expected converted output.
- `schemas/mctl-devloop/schema.yaml` (candidate custom schema, `version: 1`):
  - artifacts `proposal` (`proposal.md`) -> `specs` (`specs/**/spec.md`) -> `design` -> `tasks`;
  - `apply: {requires: [tasks], tracks: tasks.md}`.

  It differs from `spec-driven` only in templates and instructions that encode MCTL headings. This is deliberate. The pinned `skip_specs` note says the `specs/` prefix is the contract custom schemas inherit, so a schema generating `requirements.md` would carry nothing archive can apply.

### 3. Decision record `docs/spikes/655-openspec-contract.md`

It contains:
- the mapping table;
- the loss report for issue-596 (and optionally 516/519);
- sizes;
- the delta comparison table, with each row giving the pinned rule, the MCTL choice and the test name;
- the `.openspec.yaml` field map;
- the canonical-spec before / delta / after demonstration;
- the Investigator/Implementer fit table (clarity, completeness, context size, ambiguity, implementation success, changed-capability identification);
- the Shepherd boundary;
- the change classes;
- the schema comparison (spec-driven vs `mctl-devloop` vs adapter-only);
- the coupling inventory;
- the migration cost;
- the effect on the state machine and APIs (expected: none for adapter-only; `TRIPLET` / `TRIPLET_FILENAMES` / prompts / `_landed_triplet_defects` for adoption);
- exactly one recommendation;
- follow-up issue drafts.

**Shepherd boundary (documented, plus an import-boundary test).** Spec verification would become a future optional argument `spec: SpecVerdict | None = None` to `decide`, following the `ci` precedent. `fail` joins `address-review` blockers. `unknown` maps to a wait, like `ci-unknown`. `pass` never short-circuits the reviewer or CI gates. With `None`, behavior is identical. The spike does not edit `run_shepherd.py`. It only adds a test asserting that `orchestrator/sdd` imports nothing from `run_shepherd`, `proposal_state` or `temporal`, and that `SpecVerdict` has no merge/approve affordance. The record explicitly rejects any design where `openspec verify` replaces Shepherd, CI, review policy, approval or authorization.

**Change classes.** Classes are planning shapes in one lifecycle:
- `trivial`: `skip_specs: true`, `proposal.md` + `tasks.md`.
- `normal`: one capability delta.
- `governed`: deltas plus a mandatory design.md and an explicit risk section.

The class is carried as `x-mctl-change-class`. It is advisory to agents and ignored by authorization. `control.requires_human_approval` is set by the orchestrator exactly as today.

**Expected outcome (hypothesis to be confirmed or overturned by the evidence): `ADAPTER_ONLY`.** The reasons:
- The spec grammar is not covered by the pinned reference.
- Schema commands are experimental at v1.14.2.
- Existing proposals have no capability decomposition, so canonical specs would have to be authored before deltas mean anything.
- Adoption touches the investigator's publish guards.

The record must flip to `ADOPT_CONTRACT` only if the grammar is verified against `f80d860`, the issue-596 loss report is empty, and the investigator simulation shows no worsened dimension. In that case it must include a staged plan:
1. Shadow-write a change package next to the triplet.
2. Implementer reads specs.
3. Investigator stops writing `requirements.md`.
4. Canonical-spec sync on merge.

## Alternatives

1. **Adopt built-in `spec-driven` directly, with the OpenSpec CLI in the worker image.** Dropped. It makes the Node CLI a runtime dependency (against invariant 6). It also ties publish validation to an external binary whose schema commands are experimental at v1.14.2.
2. **Keep EARS `requirements.md` and declare it as a custom-schema artifact.** Dropped. Per the pinned facts, archive/validate read deltas only from `specs/**/spec.md`, so such a schema carries nothing archive can apply. It would be compatible in name only.
3. **Dual-author `requirements.md` and `specs/**` permanently.** Dropped. It violates invariant 7 (one canonical source) and doubles investigator token cost.
4. **Do nothing (`NO_GO` without a prototype).** Dropped. The issue's acceptance criteria require fixture-backed evidence, and the mapping and delta work is cheap and fully reversible.

## Platform impact

- **Migrations.** None. No existing proposal is rewritten. The conversion runs on fixture copies.
- **Backward compatibility.** No production module imports `orchestrator/sdd`. `TRIPLET`, prompts, `.status.yaml` writers, `decide` and `DevLoopWorkflow` are untouched. This is enforced by an import-boundary test.
- **Resources.** Only test runtime is added (small pure-Python tests). No new dependency: PyYAML is already a direct dependency in `pyproject.toml`. No image change for `mctl-agents-worker*`.
- **Risks and mitigations:**
  - *Assumed spec grammar diverges from real OpenSpec.* Isolated in `spec_model.py` behind `GRAMMAR_VERIFIED = False`. Blocks an `ADOPT_CONTRACT` verdict.
  - *The spike is mistaken for a production path.* Package docstring, `docs/spikes/` placement, and the import-boundary test.
  - *Approval provenance is weakened by a new format.* Forbidden-execution-key validation. The approval-digest gap is recorded as a follow-up instead of being widened.
  - *Fixtures leak sensitive data.* Only the `source` block of `.status.yaml` is copied. No approver identities or trace ids are copied.

## Open questions

- The spec, delta and `proposal.md` markdown grammar is not in the pinned v1.14.2 reference and was not verified here. It must be verified against `f80d860` or recorded as unverified, which excludes `ADOPT_CONTRACT`.
- Whether to run the real OpenSpec CLI as a dev-only cross-check. Not observed; the default is not to run it.
- Deployed worker configuration was not inspected beyond confirming the services exist, because the spike does not touch it. No mctl MCP calls were made.
