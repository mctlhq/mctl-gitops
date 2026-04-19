---
name: mctl-github-remediation
description: Create or update deterministic remediation pull requests in allowlisted GitHub repos after mctl evidence gathering. Use for incident runs that are safe for PR-backed changes and require a real pr_created callback.
---

# MCTL GitHub Remediation

- This skill applies after a successful `mctl_agent_external` claim.
- Use GitHub MCP tools only for explicit repo-backed remediation.
- Respect the GitHub repo allowlist exposed to the runtime.
- Prefer one deterministic remediation branch per ticket, reusing the same open PR when it already exists.
- Use `pr_created` only when a real GitHub pull request exists.
- Include repo, branch, pr_url, pr_number, and commit_sha in callback artifacts when available.
- Do not merge PRs automatically in v1.
