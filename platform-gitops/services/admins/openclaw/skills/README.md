# admins OpenClaw skills (source of truth)

These SKILL.md files are the admin-tenant-specific OpenClaw skills.

**Runtime authority**: S3 `platform-state/admins/openclaw/workspace/skills/` (edits in chat persist there).

**Role of this directory**: source of truth / backup. Seed when provisioning a fresh admins workspace; periodic cron syncs runtime changes back here.

Do not expect edits here to auto-apply to the running pod without a workspace sync.
