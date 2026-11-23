# Design: agent-fixer-guardrails

version-status: unverified, see commit SHA

## Source commits
- mctl-agent:8f91420 — fix(fixer): patch only the YAML path a fix names
- mctl-agent:42cce34 — fix(fixer): refuse no-op diagnoses and Unicode line breaks
- mctl-agent:ca6beca — fix(fixer): refuse diagnosis values that would not stay one scalar

## Current state of documentation
- Existing page: `docs/platform/components.md` (mctl-agent block). Per the inbox it likely does not describe fixer constraints. The docs-tree snapshot (2026-04-27) is stale and the page was not re-read: `<TODO: confirm current contents before applying>`.
- Optional: `docs/reference/troubleshooting.md` for "why no PR" cross-link, if it exists.

## Proposed solution
UPDATE `docs/platform/components.md`: add a "Fixer guardrails" subsection under mctl-agent covering single-scalar edits, refusal cases, and the behaviour that refusals produce no PR. Optionally add a one-line pointer in troubleshooting. No code-level detail beyond the commit messages.

## Alternatives
- New standalone page `docs/platform/agent-fixer.md`: dropped, impact and effort are small, and a subsection suffices.
- Troubleshooting-only entry: dropped, since the guarantees are also useful to PR reviewers.

## Impact
- No sidebar / nav change.
- No mermaid diagram needed.
- Versioning: applies once mctl-agent 2.9.2 or later is confirmed in prod.
