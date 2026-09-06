---
name: roadmap-compose
description: 'Compose a canonical mctl roadmap draft from a normalized intent plus roadmap research/match evidence. Use after roadmap-intake and roadmap-research-match. Produces a deterministic RoadmapDraft with title, context, goal, phases, acceptance criteria, dependencies, non-goals, and related work. Never publishes or mutates roadmap state.'
---

# roadmap-compose

Compose a reviewable roadmap draft from `RoadmapIntent` and `RoadmapMatchResult`.

## Preconditions

Do not compose a new item when the match decision is `DUPLICATE`; instead return the matching item and explain why publishing should stop.

For `EXTEND`, compose an update/addendum against the existing roadmap item rather than a parallel item unless the user explicitly requires a separate child PoC/spike.

## Canonical output

Return a `RoadmapDraft` containing:

- `kind`: `POC`, `SPIKE`, `EPIC`, or `IMPLEMENTATION`;
- `decision`: `NEW` or `EXTEND`;
- `target_repo`: normally `mctlhq/.github` for platform roadmap items;
- `target_issue`: required for `EXTEND`;
- `title`;
- `body`;
- `related` issue references;
- `dependencies`;
- `source_research` summary;
- `warnings` / known limitations.

The body should use this baseline structure when applicable:

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
