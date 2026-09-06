---
name: roadmap-compose
description: 'Compose a canonical mctl RoadmapDraft from a normalized intent, the original user request, and roadmap research/match evidence. Produces a deterministic NEW/EXTEND/DUPLICATE draft for the fixed roadmap repository. Never publishes or mutates roadmap state.'
---

# roadmap-compose

Compose a reviewable roadmap draft from `RoadmapIntent`, `RoadmapMatchResult`, and the original user request text supplied verbatim by the orchestrator.

## Inputs

Consume all three inputs:

1. `RoadmapIntent` from `roadmap-intake`;
2. `RoadmapMatchResult` from `roadmap-research-match`;
3. the original user request text verbatim.

`RoadmapIntent.source_request` MUST equal the separately supplied original request. If they differ, fail rather than composing from inconsistent provenance.

Preserve explicit requirements carried in `RoadmapIntent.details` and in the original request. Do not reconstruct omitted requirements from guesswork.

## Preconditions and decision transitions

For `EXTEND`, compose an addendum/comment against the existing roadmap item identified by `primary_match`.

If research matched an existing parent but the user's explicit requirement is to create a separate child PoC/spike or otherwise a separate roadmap item, the resulting draft MUST use `decision: "NEW"`, `target_issue: null`, and list the matched parent in `related`. Do not emit an `EXTEND` draft for a separate item.

For `DUPLICATE`, produce a non-publishable draft that points to the matching item and explains why publication must stop.

## Shared issue-reference format

Every issue reference in the draft MUST use the canonical string `owner/repo#number`, for example `mctlhq/.github#18`.

`target_issue` when non-null, every element of `related`, and every element of `dependencies` use this exact string shape. Do not emit numeric-only issue identifiers or issue objects in these fields.

## Output contract

Return exactly one `RoadmapDraft` JSON object. This `EXTEND` example intentionally shows a non-null `target_issue`:

```json
{
  "kind": "EPIC",
  "decision": "EXTEND",
  "target_repo": "mctlhq/.github",
  "target_issue": "mctlhq/.github#18",
  "title": "Addendum: governed roadmap authoring capability",
  "body": "## Proposed extension\n...",
  "related": [
    "mctlhq/.github#18"
  ],
  "dependencies": [
    "mctlhq/mctl-agents#242"
  ],
  "source_research": "The existing roadmap item owns the same durable capability and should be extended rather than duplicated.",
  "warnings": []
}
```

Field requirements:

- `kind`: one of `POC`, `SPIKE`, `EPIC`, `IMPLEMENTATION`;
- `decision`: one of `NEW`, `EXTEND`, `DUPLICATE`;
- `target_repo`: MUST be exactly the constant string `mctlhq/.github`;
- `target_issue`: canonical `owner/repo#number` string required for `EXTEND` and `DUPLICATE`; MUST be `null` for `NEW`;
- `title`: proposed issue title for `NEW`; for `EXTEND`/`DUPLICATE`, use the existing roadmap item title or a concise addendum title. If the user supplied `details.exact_title`, preserve it for a `NEW` draft unless doing so would contradict the required roadmap title convention;
- `body`: exact publishable issue body for `NEW`, exact comment body for `EXTEND`, and a concise non-publishable duplicate explanation for `DUPLICATE`;
- `related`: array of canonical issue-reference strings;
- `dependencies`: array of canonical issue-reference strings;
- `source_research`: concise summary of the match evidence used to compose the draft;
- `warnings`: array of known limitations/uncertainties; use `[]` when none are known.

Do not add fields outside this contract.

Emit a single JSON object matching the contract above. Nothing else.

## Canonical body structure

For `NEW`, the body should use this baseline structure when applicable:

```markdown
## Context
## Goal
## Architectural boundary / principles
## Phases
## Deliverables
## Acceptance criteria
## Non-goals
## Related work
```

Populate these sections from the original request and `RoadmapIntent.details` when provided. Do not add empty sections just to satisfy the template, and do not silently discard explicit phases, deliverables, acceptance criteria, non-goals, context, or exact-title requirements from the user.

For `EXTEND`, the `body` is the exact comment/addendum text to be posted to the existing issue. Do not rewrite the existing roadmap issue body in the MVP.

For `DUPLICATE`, the draft is explicitly non-publishable. `body` should explain the match and direct the caller to the existing item; the privileged publish operation must reject this decision.

## Type-specific guidance

### POC

Focus on the hypothesis to prove, smallest integration path, controlled test phases, negative tests, measurements, and an explicit go/no-go decision. Distinguish PoC limitations from target production architecture.

### SPIKE

Focus on questions, experimental matrix, measurements, compatibility constraints, ADR output, and decision criteria. Avoid pretending the spike itself ships production behavior.

### EPIC

Describe durable capability boundaries, repository ownership, sequencing, governance/security constraints, acceptance criteria for the initiative, and expected child-issue decomposition.

### IMPLEMENTATION

Keep scope bounded and executable. State concrete behavior, affected ownership, tests, compatibility requirements, and definition of done. Avoid roadmap-level future architecture unless directly required.

## Quality rules

- Preserve explicit user constraints and detailed requirements from the original request.
- Cite/mention existing roadmap/issues discovered by research using canonical issue-reference strings rather than restating their scope as new work.
- Separate capability visibility from authorization where relevant.
- Make security boundaries enforceable outside prompts/skills.
- Do not claim a PoC closes a known bypass if it intentionally leaves that bypass in place.
- Prefer explicit negative tests for risky integrations.
- Avoid creating child issues in this skill.

## Mutation boundary

This skill only produces a draft. The resulting content may be shown to the user for approval, but publication MUST happen through a separate privileged operation that binds approval to the exact draft/version/hash.

Execution environment provides read-only tools; this text is not the enforcement.
