---
name: roadmap-intake
description: 'Normalize a raw product/platform idea into a roadmap proposal type and scope before any mutation. Use when the user asks to add something to the roadmap, create an epic, run a PoC/spike, or formalize an implementation proposal. Produces a structured RoadmapIntent with kind, goal, constraints, expected outcome, and recommended next step. Never creates or updates GitHub issues.'
---

# roadmap-intake

Turn a raw idea into a normalized roadmap intent before research or publishing.

## Output contract

Return a `RoadmapIntent` with:

- `kind`: one of `POC`, `SPIKE`, `EPIC`, `IMPLEMENTATION`;
- `summary`: one-sentence normalized intent;
- `goal`: what must be proven, enabled, or delivered;
- `constraints`: explicit boundaries from the user or platform architecture;
- `success_signal`: what would justify proceeding;
- `next_step`: normally `roadmap-research-match`.

## Classification rules

Use `POC` when the primary question is whether an integration or architecture works end-to-end in the real environment.

Use `SPIKE` when the main output is knowledge, measurements, compatibility results, or an ADR rather than a production path.

Use `EPIC` when the proposal spans multiple repositories/phases and represents a durable platform/product capability.

Use `IMPLEMENTATION` when the architecture and ownership are already settled and the task is a bounded executable change.

Prefer the smallest honest type. Do not upgrade a PoC into an Epic only because it may have future follow-up work.

## Safety and mutation boundary

This skill is read/transform only. It MUST NOT create, update, label, close, or otherwise mutate roadmap/issues.

If the user's request also says to publish immediately, still produce the normalized intent first. Publishing belongs to a separate governed operation.
