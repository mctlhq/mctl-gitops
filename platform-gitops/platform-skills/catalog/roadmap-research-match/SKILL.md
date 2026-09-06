---
name: roadmap-research-match
description: 'Research existing mctl roadmap items and related implementation issues before a new roadmap mutation. Use after roadmap-intake. Determines whether the proposal is NEW, EXTEND, or DUPLICATE; finds related epics/issues, likely ownership, dependencies, and conflicts. Never mutates GitHub.'
---

# roadmap-research-match

Research the existing roadmap and implementation graph before composing a new item.

## Inputs

Consume a normalized `RoadmapIntent` from `roadmap-intake`.

## Required research

Search, at minimum:

1. `mctlhq/.github` roadmap issues for semantic overlap;
2. implementation issues in likely owner repositories;
3. enabling platform issues that constrain sequencing or ownership;
4. recent/active issues first unless the user explicitly asks for historical context.

Use exact entity/technology terms plus semantic variants. Do not infer `NEW` merely because titles differ.

## Decision contract

Return a `RoadmapMatchResult`:

- `decision`: `NEW`, `EXTEND`, or `DUPLICATE`;
- `primary_match`: best existing roadmap item if any;
- `related`: relevant roadmap and implementation issues;
- `dependencies`: prerequisite/enabling work;
- `ownership`: likely repository boundaries;
- `rationale`: concise evidence for the decision;
- `research_queries`: enough detail to make the match reproducible.

### NEW

Use when no existing roadmap item already owns the same durable outcome.

### EXTEND

Use when an existing roadmap item owns the same capability but should be broadened with a new phase, PoC, boundary, or acceptance criterion.

### DUPLICATE

Use when creating a new item would describe substantially the same outcome and scope as an existing roadmap item.

## Safety and mutation boundary

This skill is strictly read-only. Never create/update issues, comments, labels, milestones, or project fields.

If evidence is ambiguous, prefer `EXTEND` with an explicit uncertainty note over silently creating a near-duplicate.
