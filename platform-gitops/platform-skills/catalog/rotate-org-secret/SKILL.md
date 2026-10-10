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
! for repo in .github mctl-academy mctl-agent mctl-agents mctl-alice mctl-api mctl-claude-remote mctl-design mctl-docs mctl-gitops mctl-loyalty mctl-pairdesk mctl-portal mctl-telegram mctl-web newton-mcp-gateway portfolio projects-mcp seerrsense; do
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

## Repos covered (as of 2026-10-10)

Both `CLAUDE_CODE_OAUTH_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN_2` exist as
**org-level** secrets with `visibility: all`, so every public repo inherits
them and Option B is the rotation. Per-repo loops are for repo-level copies.

Non-archived repos with `.github/workflows/claude-review.yml` (19):
- .github, mctl-academy, mctl-agent, mctl-agents, mctl-alice, mctl-api
- mctl-claude-remote, mctl-design, mctl-docs, mctl-gitops, mctl-loyalty
- mctl-pairdesk, mctl-portal, mctl-telegram, mctl-web, newton-mcp-gateway
- portfolio, projects-mcp, seerrsense

Repo-level copies: only **projects-mcp** sets both names itself, and it must
keep them. It is private, and the org is on the GitHub Free plan, where org
secrets are not available to private repos. Do not delete these copies. An
org-only rotation leaves projects-mcp on the old token, so always rotate it
per-repo as well.

Not covered on purpose: the temporary `*-ghsa-*` advisory forks.

Re-derive this list instead of trusting it:
```bash
for r in $(gh repo list mctlhq --no-archived --limit 200 --json name --jq '.[].name'); do
  gh api "repos/mctlhq/$r/contents/.github/workflows/claude-review.yml" --jq .name >/dev/null 2>&1 \
    && echo "$r $(gh api "repos/mctlhq/$r/actions/secrets" --jq '[.secrets[].name|select(test("CLAUDE"))]|join(",")')"
done
```

## Special case — CLAUDE_CODE_OAUTH_TOKEN (claude-review)

The token comes from `claude setup-token`. It is stored as an org-level
secret, so the rotation is Option B with this name, plus the repo-level
overrides listed above. The per-repo loop below is the fallback, for when an
org-level secret is not an option:
```
! for repo in .github mctl-academy mctl-agent mctl-agents mctl-alice mctl-api mctl-claude-remote mctl-design mctl-docs mctl-gitops mctl-loyalty mctl-pairdesk mctl-portal mctl-telegram mctl-web newton-mcp-gateway portfolio projects-mcp seerrsense; do
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
