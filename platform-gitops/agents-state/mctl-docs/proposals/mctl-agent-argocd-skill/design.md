# Design: mctl-agent-argocd-skill

## Source commits
- `mctl-agent:74ee766` — feat(skill): argocd_sync_failed — diagnose stuck-degraded ArgoCD apps

## Current state of documentation
- **Existing page:** `docs/platform/components.md`
- The page covers platform components including mctl-agent. Based on the docs-tree
  snapshot, mctl-agent is listed as a component but the specific built-in skills it
  runs are not enumerated in detail (or only the rollback skill is mentioned).
- The new `argocd_sync_failed` skill is absent from any current page.
- No new page is needed — a targeted update to the mctl-agent section of
  `docs/platform/components.md` is sufficient.

## Proposed solution

**Target file:** `docs/platform/components.md`

Locate the mctl-agent section and add a subsection (or extend an existing skills
table) with the following content:

### New subsection: Built-in diagnostic skills

Add or extend a table listing active built-in skills. At minimum add:

| Skill | Trigger | Action |
|---|---|---|
| `argocd_sync_failed` | ArgoCD app in `OutOfSync+Degraded` or `Degraded` state; or `ArgoCDApplicationDegraded` / `ArgoCDApplicationSyncFailed` AlertManager alert | Diagnoses failure pattern; posts recovery commands to Telegram. No autonomous fix. |
| *(existing skills if any)* | ... | ... |

Below the table, add a prose paragraph explaining the human-approval model:

> `argocd_sync_failed` recognises two known failure patterns: **CRD storedVersion
> conflicts** (status contains "must remain in spec.versions") and **managedFields
> poisoning** (status contains "request to convert CR from an invalid group/version").
> For each, the skill returns the exact `kubectl` recovery commands in the Telegram
> diagnosis message. The skill never applies changes autonomously — the operator must
> review and execute the commands.

Add a cross-reference to `docs/reference/troubleshooting.md` if that page covers
CRD recovery steps, or add a note that a runbook is planned.

## Alternatives

1. **New standalone page `docs/platform/mctl-agent.md`** — rejected: the component
   already has a section in `docs/platform/components.md`. A standalone page would
   require a sidebar update and is disproportionate for adding one skill entry.

2. **Add to `docs/reference/troubleshooting.md`** — rejected: the troubleshooting
   page is for user-facing problems; documenting the agent's skill set belongs with
   the component description, not the troubleshooting guide.

## Impact
- **VitePress sidebar / nav config:** no change — `components.md` is already in the
  nav.
- **Diagrams (mermaid):** not required for this change; a simple table + prose is
  sufficient. A sequence diagram for the alert → diagnosis → Telegram flow could be
  added optionally.
- **Documentation versioning:** applies to mctl-agent 1.10.1 (in production 2026-05-07).
  No version marker needed.
