---
name: rotate-org-secret
description: Rotate or set a GitHub Actions secret across all mctlhq repos without leaking the value into chat or shell history. Use when rotating CLAUDE_CODE_OAUTH_TOKEN (or any org-wide Actions secret), adding the secret to a new repo, or verifying which repos have it.
user-invocable: true
---

# rotate-org-secret — rotate a GitHub Actions secret across all mctlhq repos

Triggered by: `/rotate-org-secret <SECRET_NAME>`
Example: `/rotate-org-secret CLAUDE_CODE_OAUTH_TOKEN_2`

## What this skill does

1. Lists all mctlhq repos that currently have the named secret set (or all repos with claude-review.yml if secret name is CLAUDE_CODE_OAUTH_TOKEN or CLAUDE_CODE_OAUTH_TOKEN_2).
2. Instructs the user how to securely supply the new token value without pasting it into chat.
3. Accepts the token via a no-history pattern (see below) and sets it across all target repos.

## How to supply the token securely

NEVER paste a raw token into the chat — it ends up in session logs. And never
ask the user to `export SECRET=<value>` directly — that form is stored in shell
history.

### Option A — from a file (most secure)
Store the token in a local file, then run in the chat prompt field:
```
! gh secret set CLAUDE_CODE_OAUTH_TOKEN_2 --org mctlhq --visibility all < ~/.secrets/claude-review-token-2.txt
```
or per-repo:
```
! for repo in mctl-telegram mctl-api mctl-gitops mctl-agent mctl-agents mctl-portal mctl-web mctl-openclaw mctl-docs mctl-design mctl-claude-remote mctl-trading-data mctl-mcp; do
    gh secret set CLAUDE_CODE_OAUTH_TOKEN_2 -R mctlhq/$repo < ~/.secrets/claude-review-token-2.txt && echo "OK: $repo" || echo "FAIL: $repo"
  done
```

### Option B — org-level secret (propagates to all repos automatically)
If the org allows it:
```
! gh secret set CLAUDE_CODE_OAUTH_TOKEN_2 --org mctlhq --visibility all < ~/.secrets/claude-review-token-2.txt
```
This is the single-command rotation — one secret, all repos, no per-repo loop.

### Option C — macOS Keychain
```
! security find-generic-password -a claude-review-token-2 -w | \
    gh secret set CLAUDE_CODE_OAUTH_TOKEN_2 --org mctlhq --visibility all
```

### Option D — interactive, no file (`read -rs`)
`read -rs` does NOT log to `~/.zsh_history`. Feed the value to `gh` via stdin
(builtin `printf` does not exec, so the secret never appears in argv /
`ps aux`) — never via `--body "$VAR"`:
```
! read -rs SECRET_VALUE && for repo in <target repos>; do
    printf '%s' "$SECRET_VALUE" | gh secret set <SECRET_NAME> -R "mctlhq/$repo" && echo "OK: $repo" || echo "FAIL: $repo"
  done; unset SECRET_VALUE
```
The terminal waits silently — paste the token and press Enter.

## When the agent invokes this skill

After the user runs the `!` command above:
1. Verify the secret was set: `gh secret list -R mctlhq/mctl-telegram | grep <SECRET_NAME>`
2. Report which repos have it and which are missing.
3. If repos are missing, provide the exact `!` command to set them.

Verification loop across all repos:
```bash
for repo in <target repos>; do
  echo -n "$repo: "
  gh secret list --repo "mctlhq/$repo" --json name --jq '.[].name' | grep "<SECRET_NAME>" || echo "MISSING"
done
```

## Repos covered (as of 2026-05-30)

All repos with claude-review.yml:
- mctl-gitops, mctl-telegram, mctl-web, mctl-openclaw, mctl-docs
- mctl-design, mctl-claude-remote, mctl-api, mctl-agent, mctl-agents
- mctl-portal, mctl-trading-data, mctl-mcp

When a new repo gets `claude-review.yml`, add its name to the loops and re-run
the skill.

## Special case — CLAUDE_CODE_OAUTH_TOKEN (claude-review)

The primary token is per-repo (not org-level) because it was set with
`claude setup-token`:
```
! for repo in mctl-telegram mctl-api mctl-gitops mctl-agent mctl-agents mctl-portal mctl-web mctl-openclaw mctl-docs mctl-design mctl-claude-remote mctl-trading-data mctl-mcp; do
    gh secret set CLAUDE_CODE_OAUTH_TOKEN -R mctlhq/$repo < ~/.secrets/claude-review-token.txt && echo "OK: $repo" || echo "FAIL: $repo"
  done
```

Getting a new Claude Code OAuth token:
```bash
claude setup-token
# Opens browser → log in → copy token → paste into file
echo "<token>" > ~/.secrets/claude-review-token-2.txt
chmod 600 ~/.secrets/claude-review-token-2.txt
```

Token scope: Claude Code OAuth — grants claude-review.yml access to post PR
comments; does not grant repo write access.
