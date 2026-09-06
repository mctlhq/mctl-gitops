---
name: roadmap-compose
description: 'Compose a canonical mctl roadmap draft from a normalized intent plus roadmap research/match evidence. Use after roadmap-intake and roadmap-research-match. Produces a deterministic RoadmapDraft with title, context, goal, phases, acceptance criteria, dependencies, non-goals, and related work. Never publishes or mutates roadmap state.'
---

# roadmap-compose

Compose a reviewable roadmap draft from `RoadmapIntent` and `RoadmapMatchResult`.

## Preconditions

For `EXTEND`, compose an addendum/comment against the existing roadmap item rather than a parallel item unless the user explicitly requires a separate child PoC/spike.

For `DUPLICATE`, produce a non-publishable draft that points to the matching item and explains why publication must stop.

## Output contract

Return exactly one `RoadmapDraft` JSON object with this shape:

```json
{
  "kind": "POC",
  "decision": "NEW",
  "target_repo": "mctlhq/.github",
  "target_issue": null,
  "title": "roadmap(example): bounded proof of concept",
  "body": "## Context\n...\n\n## Goal\n...",
  "related": [
    "mctlhq/.github#18"
  ],
  "dependencies": [
    "mctlhq/mctl-agents#242"
  ],
  "source_research": "No existing roadmap item owns the same durable outcome; related control-plane work is listed above.",
  "warnings": []
}
```

Field requirements:

- `kind`: one of `POC`, `SPIKE`, `EPIC`, `IMPLEMENTATION`;
- `decision`: one of `NEW`, `EXTEND`, `DUPLICATE`;
- `target_repo`: normally `mctlhq/.github` for platform roadmap items;
- `target_issue`: required for `EXTEND` and `DUPLICATE`, otherwise `null`;
- `title`: proposed issue title for `NEW`; for `EXTEND`/`DUPLICATE`, use the existing roadmap item title or a concise addendum title;
- `body`: exact publishable issue body for `NEW`, exact comment body for `EXTEND`, and a concise non-publishable duplicate explanation for `DUPLICATE`;
- `related`: array of issue references;
- `dependencies`: array of issue references;
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

Do not add empty sections just to satisfy the template.

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

- Preserve explicit user constraints.
- Cite/mention existing roadmap/issues discovered by research rather than restating their scope as new work.
- Separate capability visibility from authorization where relevant.
- Make security boundaries enforceable outside prompts/skills.
- Do not claim a PoC closes a known bypass if it intentionally leaves that bypass in place.
- Prefer explicit negative tests for risky integrations.
- Avoid creating child issues in this skill.

## Mutation boundary

This skill only produces a draft. The resulting content may be shown to the user for approval, but publication MUST happen through a separate privileged operation that binds approval to the exact draft/version/hash.
