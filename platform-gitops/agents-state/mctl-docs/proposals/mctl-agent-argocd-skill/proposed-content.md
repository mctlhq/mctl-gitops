# Proposed content: mctl-agent-argocd-skill

> **Apply to:** `mctl-docs/docs/platform/components.md` (UPDATE)
> **Source:** mctl-agent@74ee766

---

Locate the mctl-agent section in `docs/platform/components.md` and add the following
subsection after the existing description of the component.

### BEFORE (current state — no skill enumeration)

```markdown
## mctl-agent

The self-healing agent monitors AlertManager and automatically raises PRs to
fix detected issues (image tag drift, rollback, etc.).
```

*(The exact existing text may differ — match on the `## mctl-agent` heading and
insert after the existing description paragraph.)*

### AFTER (add built-in skills subsection)

```markdown
## mctl-agent

The self-healing agent monitors AlertManager and automatically raises PRs to
fix detected issues (image tag drift, rollback, etc.).

### Built-in diagnostic skills

mctl-agent ships with a set of built-in skills that activate automatically when
matching conditions are detected. Skills either produce a GitOps PR (autonomous fix)
or post a diagnosis to Telegram for human approval (no autonomous change).

| Skill | Trigger | Behaviour |
|---|---|---|
| `argocd_sync_failed` | ArgoCD application enters `OutOfSync+Degraded` or `Degraded` state; or an `ArgoCDApplicationDegraded` / `ArgoCDApplicationSyncFailed` AlertManager alert is received | Diagnoses the failure pattern and posts recovery commands to the operator Telegram channel. **No autonomous fix** — the operator must execute the commands. |
| `rollback` | Image tag drift detected in a GitOps manifest | Opens a PR reverting the image to the previous tag from GitOps history. |

#### `argocd_sync_failed` in detail

The skill recognises two known failure patterns and provides tailored recovery
commands for each:

1. **CRD storedVersion conflict** — when the ArgoCD sync status contains
   `"must remain in spec.versions"` or `"missing from spec.versions"`.
   This typically occurs after a Helm chart major-version revert that leaves a
   stale `storedVersion` entry in the CRD. Recovery involves a `kubectl patch`
   to remove the stale entry.

2. **managedFields poisoning** — when the status contains
   `"request to convert CR from an invalid group/version"`. This can occur
   after a temporary CRD recovery window. Recovery involves `kubectl` commands
   to strip the affected `managedFields`.

When neither pattern matches, the skill still fires (at lower priority) and
posts the raw ArgoCD sync status to Telegram so the operator has the full
context without having to open the ArgoCD UI.

> **Human approval required.** `argocd_sync_failed` never applies changes
> to the cluster autonomously. All recovery commands appear in Telegram as
> plain text; the operator reviews and runs them.

**Available since:** mctl-agent 1.10.1 (deployed 2026-05-07).
```

---

> No `<TODO>` markers — all information is derived directly from the commit
> `74ee766` message and diff, which are detailed and self-contained.
> If the existing `components.md` already has a skills table, merge the
> `argocd_sync_failed` row into it rather than creating a new table.
