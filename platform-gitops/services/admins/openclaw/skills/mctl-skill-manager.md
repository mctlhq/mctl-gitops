---
name: mctl-skill-manager
description: Manage OpenClaw SKILL.md files for this tenant. Use when the operator asks to list, create, edit, back up to gitops, restore from gitops, or delete skills in this workspace. Backing storage has two layers — runtime (S3 workspace) and gitops (durable backup); each change must target the right layer.
---

# MCTL Skill Manager

You manage this tenant's OpenClaw skills. Skills are `SKILL.md` files under `skills/{name}/SKILL.md` in your workspace. Edits in chat are instant in S3; the gitops repo is the durable backup and source-of-truth for a fresh workspace.

## Storage layers

- **Runtime (S3 workspace)**: `skills/{name}/SKILL.md` — edit with your own Bash/Write tools. Changes take effect after the agent picks them up (new session or reload). No review, no audit trail beyond the pod.
- **GitOps backup**: `platform-gitops/services/{team}/openclaw/skills/{name}.md` — written via `mctl_skill_save`, surfaced via `mctl_skill_list` / `mctl_skill_read`. Survives workspace loss. Each write is a commit attributed to the triggering operator.

Neither layer auto-syncs to the other. The operator chooses when to save / restore.

## Actions

- **List runtime skills** — `ls skills/` in the workspace.
- **Read a runtime skill** — `cat skills/{name}/SKILL.md`.
- **Create or edit a runtime skill** — `mkdir -p skills/{name} && cat > skills/{name}/SKILL.md` (or use the Write tool). Validate frontmatter: the file must begin with `---\nname: {name}\ndescription: ...\n---\n` so the runtime can discover it.
- **Delete a runtime skill** — `rm -rf skills/{name}`.
- **List gitops skills** (what is backed up) — `mctl_skill_list(team_name=<this team>)`.
- **Read a gitops skill** — `mctl_skill_read(team_name=<this team>, skill_name=<name>)`.
- **Save current runtime skill to gitops** — read the file content, then call `mctl_skill_save(team_name=<this team>, skill_name=<name>, content=<text>)`. Wait for the returned workflow to finish; report the workflow URL.
- **Restore a skill from gitops into the workspace** — call `mctl_skill_read`, write the returned content to `skills/{name}/SKILL.md`.
- **Delete a skill from gitops** — `mctl_skill_delete(team_name=<this team>, skill_name=<name>)`. This does not touch the runtime copy — delete that separately with `rm -rf skills/{name}` if desired.

## Rules

- `skill_name` must be kebab-case: lowercase letters, digits, hyphens; starts and ends with alphanumeric; 2–64 chars. Must match `^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$`.
- Skill content must be valid Markdown with a YAML frontmatter block whose `name:` matches the file name, and a `description:` field so other agents can find it.
- Only a tenant owner can save or delete in gitops. Non-owners get a 403. Do not retry on auth failures.
- Gitops writes return a `workflow_name`. Verify the workflow succeeds at `https://workflows.mctl.ai/workflows/{team}/{workflow_name}` before reporting success to the operator.
- Never `rm -rf skills/*` in bulk without confirming with the operator first.
- Do not attempt to write to gitops paths outside `platform-gitops/services/{team}/openclaw/skills/`.
