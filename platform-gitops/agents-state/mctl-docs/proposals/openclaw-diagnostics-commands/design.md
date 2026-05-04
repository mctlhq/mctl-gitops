# Design: openclaw-diagnostics-commands

## Source commits
- `mctl-openclaw:6ce1058` — Wire diagnostics through the core chat command (#72936)
  (2026-04-28)

  Diff highlights sourced from openclaw repo's internal docs tree:
  - `docs/gateway/diagnostics.md` — added `/diagnostics [note]` usage guidance and
    privacy notes.
  - `docs/channels/pairing.md` — pairing owner bootstrap documented.
  - `docs/cli/sessions.md` — `sessions export-trajectory` subcommand added.
  - `docs/cli/pairing.md` — pairing docs updated.

**version-status: unverified, see commit 6ce1058**
(mcp__mctl__* tools were unavailable; whether this commit is live in production has
not been confirmed via gitops.)

## Current state of documentation

`docs/platform/openclaw.md` (title: "OpenClaw Integration")

The page exists and covers OpenClaw at an integration level: what OpenClaw is, how it
connects to the mctl platform, and how tenants (`admins`, `labs`, `ovk`) use it for
multi-channel AI routing. There is no section on slash commands, owner-privileged
operations, diagnostic workflows, exec-approval gating, or the pairing-owner
bootstrap mechanism. The page is outdated with respect to 6ce1058.

`docs/reference/troubleshooting.md` (title: "Troubleshooting")

Exists. Contains general guidance for diagnosing platform issues. Has no reference to
`/diagnostics` as a first-step action for channel-level problems. A short tip or
callout would make this page more useful for operators and support engineers.

## Proposed solution

### Primary change: update `docs/platform/openclaw.md`

Add a new H2 section **"Privileged commands & diagnostics"** after the existing
integration content. The section covers three capabilities introduced in 6ce1058:

1. `/diagnostics` slash command — purpose, invocation, exec-approval requirement,
   output (bundle path + manifest summary + privacy notes), and group-chat private
   routing behaviour.
2. `sessions export-trajectory` CLI subcommand — full syntax with the
   `--session-key <key>` flag, what the output bundle contains (redacted trajectory),
   and the connection to the `/export-trajectory` slash command.
3. Pairing owner bootstrap — one paragraph explaining that approving a DM pairing
   code now auto-sets `commands.ownerAllowFrom` for first-time setups, removing the
   manual config step.

A short note at the top of the section states that all three capabilities require
owner-level access and that exec approval is requested before any privileged command
runs. A version-status callout marks the section as unverified against production.

No structural reorganisation of the page is needed; the new section slots in at the
bottom of the current page (before any footer / see-also block if one exists).

### Secondary change: update `docs/reference/troubleshooting.md`

Add a single-sentence tip (VitePress `::: tip` callout) in the "gathering diagnostic
info" area (or equivalent section) pointing readers to `/diagnostics` in their
channel chat and to the new OpenClaw page section. This is a minor, targeted edit.

### `.vitepress/config` impact

No sidebar or nav change is required. `docs/platform/openclaw.md` is already
registered. The troubleshooting page is already registered. No new files, no new nav
entries.

## Alternatives

**Option A — New standalone page `docs/platform/openclaw-commands.md`**

Creates a dedicated reference page for all OpenClaw slash commands. Pros: clean
separation; easier to extend as more commands ship. Cons: three capabilities do not
yet justify a standalone page; splits context that readers need to understand in one
place; requires a sidebar/nav config change. Dropped in favour of a section within
the existing page. Revisit if the command surface grows beyond five or six entries.

**Option B — Document under `docs/reference/` as a command reference stub**

Puts the material alongside other reference tables. Pros: consistent with how the
`docs/mcp/tools-reference.md` page works. Cons: OpenClaw slash commands are
operational concepts tied to a specific platform component, not a generic reference
artefact; the audience overlap with `docs/platform/openclaw.md` readers is strong.
Dropped.

## Impact

- **VitePress sidebar / nav config**: no change required.
- **Mermaid diagrams**: not needed for this update. The approval flow is simple enough
  to describe in prose with a numbered list. If the command surface expands, a
  sequence diagram would be warranted.
- **Documentation versioning**: mctl-docs is single-branch, no versioned docs.
  Changes apply to the current `main` branch of `mctl-docs` and will be live on
  `docs.mctl.ai` after the next ArgoCD sync following the PR merge.
- **Cross-links**: `docs/reference/troubleshooting.md` should gain a tip pointing to
  the new section. No other pages need updating at this time.
