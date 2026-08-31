# scripts/workstation/

Workstation-local automation — runs on a developer Mac, not in the cluster.
Distinct from `scripts/`, whose contents are one-shot cluster incident helpers.

| File | Purpose |
|---|---|
| `sync-platform-skills.sh` | Keep `~/.claude/skills` pointed at the platform-skills catalog on `main`. |
| `com.mctlhq.skills-sync.plist` | launchd agent running the above every 15 min. |

## skills sync

`~/.claude/skills/<name>` are symlinks Claude Code loads at session start.
They used to point into a working checkout of this repo — which is shared with
concurrent agents and routinely sits on a feature branch with uncommitted
changes, so the skills that got loaded were whatever branch someone last left
it on.

On 2026-08-31 that served a `review-watch` from before its quota fix for hours
after the fix was published to `main`, and it also emerged that
`mcp-troubleshooting` had never been symlinked at all.

The script replaces that with a dedicated read-only mirror:

- `~/.claude/skills-catalog` — sparse, blobless clone of this repo pinned to
  `origin/main`, containing only `platform-gitops/platform-skills/catalog`
  (~4 MB).
- `fetch` + `reset --hard origin/main` (not `pull`) — the mirror is a view of
  `main`, so a stray local edit must never wedge the sync.
- Symlinks are reconciled each run: new catalog skills are linked, dangling
  ones removed. A **real directory** under `~/.claude/skills` is treated as a
  hand-made local skill and left alone.
- `/tmp/review-watch.sh` is dropped whenever the catalog commit changes. That
  script is generated from the `review-watch` skill body and cached across
  sessions; its own freshness check only runs when the skill is next invoked,
  so a stale copy can otherwise outlive an update to the skill.

Skill edits still go through the `mctl_publish_platform_skill` MCP tool, which
commits to `main`; the mirror picks them up on the next run. Editing files in
the mirror is pointless — `reset --hard` discards them.

### Install

```bash
cp scripts/workstation/sync-platform-skills.sh ~/.claude/scripts/
cp scripts/workstation/com.mctlhq.skills-sync.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.mctlhq.skills-sync.plist
```

Run once by hand with `~/.claude/scripts/sync-platform-skills.sh`; log is
`~/.claude/skills-sync.log`. Requires an SSH key with read access to this repo.
