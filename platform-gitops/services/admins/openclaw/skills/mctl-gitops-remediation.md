---
name: mctl-gitops-remediation
description: Prepare conservative PR-oriented remediation for MCTL incidents. Use for resource tuning, probe fixes, workflow verification, and safe GitOps changes.
---

# MCTL GitOps Remediation

- Conservative v1 policy: prefer operator-ready summaries and PR-oriented fixes.
- Allowed safe targets include resource requests and limits, probe and timeout fixes, and clear GitOps config corrections backed by evidence.
- Do not perform destructive actions directly.
- If evidence is incomplete or the action is risky, return `needs_human`.
- Treat `mctl-gitops` as the source of truth for desired config.
