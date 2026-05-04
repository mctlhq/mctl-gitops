# Proposed content: openclaw-diagnostics-commands

> **Apply to:** `mctl-docs/docs/platform/openclaw.md` (UPDATE)
> **Source:** mctl-openclaw@6ce1058
> **version-status: unverified, see commit 6ce1058**

---

## New section to ADD to `docs/platform/openclaw.md`

Append the block below at the end of the current page content (before any existing
"See also" or footer block, if one is present).

---

```markdown
## Privileged commands & diagnostics

::: warning version-status: unverified, see commit 6ce1058
The features described in this section were introduced in
`mctl-openclaw` commit `6ce1058` (2026-04-28). They have not yet been
confirmed as live in production via GitOps. Verify against your deployed
OpenClaw version before relying on these commands.
:::

All three capabilities below require **owner-level access**. OpenClaw
will always request explicit exec approval from the owner before running
any privileged operation — no command executes silently.

### `/diagnostics` slash command

Type `/diagnostics` (optionally followed by a short freetext note) in
any channel chat where OpenClaw is active to request a local Gateway
diagnostics export.

**Approval flow:**

1. OpenClaw receives the `/diagnostics [note]` message.
2. OpenClaw prompts the channel owner for explicit exec approval.
3. After approval, OpenClaw runs `openclaw gateway diagnostics export --json`
   on the local Gateway.
4. OpenClaw replies with:
   - the path to the exported bundle
   - a manifest summary
   - privacy notes relevant to the bundle contents

**Group-chat privacy routing:** In group or multi-participant channels,
the diagnostics output (bundle path + manifest) is delivered privately
to the owner only, not posted to the shared channel thread. This
prevents sensitive gateway state from being visible to non-owner
participants.

Use `/diagnostics` as your first step when a problem occurred inside a
live conversation and you need one copy-pasteable report to share with
support. See [Troubleshooting](/reference/troubleshooting) for the
broader diagnostic workflow.

### `sessions export-trajectory` CLI subcommand

Export a redacted trajectory bundle for any stored session:

```bash
openclaw sessions export-trajectory --session-key <key>
```

- `--session-key <key>` — the session identifier as returned by
  `openclaw sessions list` or the session store. `<TODO: confirm key
  format with author of 6ce1058>`
- **Output:** a redacted trajectory bundle written to the current
  working directory. `<TODO: confirm output filename pattern and whether
  --output flag is supported, from author of 6ce1058>`

This subcommand is also the code path triggered by the
`/export-trajectory` slash command after owner approval in chat.
Sensitive fields in the trajectory are redacted automatically before
the bundle is written; the exact redaction policy is
`<TODO: confirm with author of 6ce1058>`.

### Pairing owner bootstrap

Starting from commit `6ce1058`, approving an incoming DM pairing code
does more than establish the channel connection. If **no
`commands.ownerAllowFrom` value is currently configured**, OpenClaw
automatically sets `commands.ownerAllowFrom` to the identity of the
sender whose pairing code you approved.

This means first-time setups gain an automatic owner for all privileged
commands (including `/diagnostics` and `/export-trajectory`) without a
separate configuration edit. If `commands.ownerAllowFrom` is already
set, approving a pairing code does **not** overwrite it.

To verify or update the owner identity after bootstrap, inspect your
OpenClaw configuration:

```bash
# Example: check current ownerAllowFrom value
openclaw config get commands.ownerAllowFrom
```

`<TODO: confirm the exact config key path and CLI getter syntax with
author of 6ce1058>`
```

---

## Also update: `docs/reference/troubleshooting.md` (UPDATE, minor)

> Add a tip pointing to `/diagnostics` under the section that discusses
> gathering diagnostic information (for example "Collecting logs" or
> "Before opening a support ticket"). If no such section exists, add the
> tip near the top of the page.

**Before (representative existing prose — adjust to match actual surrounding text):**

```markdown
## Collecting diagnostic information

When reporting an issue, include the following:
- mctl version (`mctl version`)
- ArgoCD application status (`argocd app get <name>`)
- Relevant pod logs (`kubectl logs ...`)
```

**After (add the `::: tip` callout immediately after the section heading or
introductory sentence):**

```markdown
## Collecting diagnostic information

::: tip OpenClaw channel diagnostics
If the issue occurred inside an OpenClaw channel session, type
`/diagnostics` in that channel chat to generate a one-shot Gateway
diagnostic bundle. See
[Privileged commands & diagnostics](/platform/openclaw#privileged-commands-diagnostics)
for the full workflow and approval requirements.

**version-status: unverified, see commit 6ce1058**
:::

When reporting an issue, include the following:
- mctl version (`mctl version`)
- ArgoCD application status (`argocd app get <name>`)
- Relevant pod logs (`kubectl logs ...`)
```

> Note: the anchor `#privileged-commands-diagnostics` is generated by
> VitePress from the H2 heading "Privileged commands & diagnostics". Verify
> the exact anchor slug after the `openclaw.md` edit is applied
> (`vitepress build docs` will warn on broken anchors).
