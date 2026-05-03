# Document command/args Values in base-service rollout.yaml

## Context

On 2026-05-02, commit `1e3f42f` in `mctlhq/mctl-gitops` added `command` and `args`
value support to the base-service Helm chart's `rollout.yaml` template, closing a
parity gap with `deployment.yaml` (which already supported these fields).

Before this fix, an operator who set `command` or `args` in a service's `values.yaml`
and used the Argo Rollout deployment strategy (canary or blue-green) would get a
silent no-op: the values were present in `values.yaml` but the rollout template simply
did not wire them into the container spec. The container started with the default image
entrypoint. No error, no warning — the misconfiguration was invisible.

`docs.mctl.ai` currently has no page explaining the available Helm values for
base-service (neither for deployment nor rollout mode). This gap means users cannot
discover or verify the `command`/`args` capability from the documentation.

## User Stories

- AS a **platform operator** deploying a service with a custom entrypoint (e.g. a
  multi-binary image or a wrapper script), I WANT to know which Helm values control
  the container command and arguments SO THAT I can confidently configure them without
  reading the chart templates directly.
- AS a **tenant developer** migrating a service from Deployment to Rollout strategy,
  I WANT confirmation that `command` and `args` work identically in both modes SO THAT
  I do not unknowingly regress container startup behaviour during the migration.
- AS an **on-call engineer** debugging a service that silently starts with the wrong
  entrypoint, I WANT a reference page listing supported values SO THAT I can quickly
  identify whether the configuration is correct.

## Acceptance Criteria (EARS)

- WHEN a reader opens `docs/guides/gitops-workflows.md`, THE SYSTEM SHALL include a
  section (or clearly labelled callout) that names `command` and `args` as supported
  Helm values in the base-service chart.
- WHEN the documentation mentions `command` / `args`, THE SYSTEM SHALL explicitly state
  that both `deployment.yaml` and `rollout.yaml` templates honour these values (parity
  note).
- IF a reader wants to override the container entrypoint, THEN THE SYSTEM SHALL provide
  a minimal YAML example showing `command` and `args` in a service `values.yaml`.
- WHILE the content is part of an existing page (update, not new page), THE SYSTEM
  SHALL preserve the existing structure and only add a concise subsection or callout.

## Out of Scope

- A full Helm values reference (all chart fields) — that is a larger effort and belongs
  in `docs/reference/` as a separate proposal.
- Documentation of Argo Rollout strategies (canary/blue-green weighting, pause steps,
  analysis templates) — out of scope for this targeted fix.
- Migration guide for operators who were accidentally relying on the broken behaviour
  (custom `command`/`args` ignored in rollout mode) — edge case; not warranted.
