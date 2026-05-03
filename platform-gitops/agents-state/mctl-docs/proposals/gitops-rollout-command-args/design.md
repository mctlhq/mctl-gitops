# Design: gitops-rollout-command-args

## Source Commits

- `mctl-gitops:1e3f42f` — fix(base-service): add command/args support to rollout.yaml
  (mirrors deployment.yaml)

## Current State of Documentation

**Existing page:** `docs/guides/gitops-workflows.md`

The page covers:
- The GitOps loop (mermaid sequence diagram: operator → mctl-api → Argo Workflows →
  mctl-gitops → ArgoCD → Kubernetes)
- Argo Workflows (list/check status, link to workflows.mctl.ai)
- Repository structure (`platform-gitops/services/{admins,tenants}/`)
- CI/CD integration (tag → image push → mctl-gitops update → ArgoCD sync)
- Grant repository access

The page has **no section on service Helm values** — it describes the workflow
mechanics but not the knobs available to configure a service. A user asking "how do I
override the container command for my service?" gets no answer from docs.mctl.ai.

A secondary candidate page is `docs/guides/services.md` ("Service Deployment"), which
may already cover `image`, `port`, `env`, etc. — but the docs are not locally
available for confirmation.
  
**Decision:** Update `docs/guides/gitops-workflows.md` with a compact "Service
Configuration Values" subsection. If `docs/guides/services.md` is a better home after
the implementer reads it, the content block is identical — just move the section.

## Proposed Solution

Add a new subsection **"Overriding Container Command and Arguments"** (or embed it in
a broader "Helm Values Reference (quick)" callout) to `docs/guides/gitops-workflows.md`.

Content:
1. One-sentence explanation of what `command` and `args` do.
2. Parity note: both `deployment.yaml` and `rollout.yaml` base templates honour these
   values (the omission in rollout.yaml was fixed in `mctl-gitops@1e3f42f` on
   2026-05-02).
3. Minimal YAML example in a fenced code block.
4. A callout (`::: warning`) for operators who previously relied on the broken
   behaviour (rollout + custom command → silently ignored).

No sidebar/nav changes needed — this is an update to an existing page.

## Alternatives

1. **New standalone `docs/reference/helm-values.md` page** covering all base-service
   values. Dropped: significantly higher effort; the rollout parity fix is the only
   timely signal. A full reference page is a separate proposal.

2. **Add to `docs/guides/services.md`** instead. Reasonable alternative; the
   implementer should check whether `services.md` already has a values section. If so,
   place the `command`/`args` content there and add a cross-link from
   `gitops-workflows.md`.

## Impact

- **VitePress sidebar / nav:** no change.
- **Mermaid diagrams:** not needed.
- **Doc versioning:** applies to current `mctl-docs` v0.1.x (base-service chart in
  prod as of 2026-05-02).
- **Cross-links:** consider adding a brief mention in `docs/reference/troubleshooting.md`
  ("service starts with wrong command → check command/args values and confirm rollout
  template parity").
