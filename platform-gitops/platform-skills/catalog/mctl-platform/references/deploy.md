# Deploy & Service Configuration

## Quick Start

Before any deploy that references `dockerfile_repo` and `git_tag`, create and push a fresh git tag in the source repository. The platform build consumes that repo ref; if the tag does not exist or points to the wrong commit, the deployed artifact will not match the intended code. For `onboard` and `deploy` with `dockerfile_repo`, prefer a new immutable tag per rollout instead of reusing an old tag.

### Create workspace + deploy a service
```
git tag <new-tag>                   → in the source repo
git push origin <new-tag>
mctl_whoami                         → check identity
mctl_create_tenant("my-team")       → provision workspace
mctl_deploy_service(
  action="onboard",
  team_name="my-team",
  component_name="hello-world",
  dockerfile_repo="user/hello-world",
  git_tag="1.0.0"
)
→ Service live at https://my-team-hello-world.mctl.ai
```

Tenant creation writes desired state to `mctl-gitops/platform-gitops/tenants/<team>/`, ArgoCD creates Application `tenant-<team>`, and Kubernetes creates namespace `<team>`. Portal/OIDC access is separate: Backstage stores tenant membership in database `backstage`, schema `tenant-management`, table `tenant_members`; OIDC group claims are read from that table.

### Default Tenant Quotas

`mctl_create_tenant` provisions a `ResourceQuota` sized for one OpenClaw pod
plus headroom:

| key | default |
|---|---|
| `requests.cpu` | `500m` |
| `requests.memory` | `1280Mi` |
| `limits.cpu` | `3` |
| `limits.memory` | `4Gi` |
| `pods` | `10` |
| `persistentvolumeclaims` | `5` |

Per-container `LimitRange` (also defaulted by tenant onboarding):
- `default.cpu = 500m`, `default.memory = 256Mi`
- `defaultRequest.cpu = 50-100m`, `defaultRequest.memory = 128Mi`
- `max.cpu = 1500m` (legacy labs) or `2` (new tenants)

A pod that does not declare `limits.cpu` will silently inherit the
LimitRange `default = 500m` — see the CPU Throttling section in
troubleshooting.md.

The defaults live in three places that must stay in sync:
- `mctl-gitops/platform-gitops/helm-charts/tenant/values.yaml`
- `mctl-gitops/platform-gitops/argo-workflows/cluster-templates/wft-create-tenant.yaml`
- `mctl-gitops/platform-gitops/backstage/templates/create-tenant/template.yaml`
- `mctl-api/internal/operations/registry.go` (`quota_cpu_lim` default)
- `mctl-api/internal/api/handlers_openclaw.go` (`openClawStartupQuotaFloor`)

### Deploy OpenClaw (AI Gateway)
```
mctl_deploy_service(
  action="onboard",
  team_name="my-team",
  component_name="openclaw",
  service_template="openclaw",
  telegram_owner_id="<user_telegram_id>",    # optional: auto-approve owner
  telegram_bot_token="<bot_token>"           # optional: per-tenant Telegram bot
)
→ Dashboard at https://my-team-openclaw.mctl.ai/#token={auto-generated}
```
> `dockerfile_repo` is NOT required when `service_template` is set to anything other than `default`.
> The template provides the image source — no GitHub build step is triggered.

> OpenClaw now deploys in OAuth-first mode. Primary UX is:
> deploy first, then connect a provider in the Control UI.
> A model API key is not required at onboard time.

> Initial `auth-profiles.json` should be created by the OpenClaw OAuth flow itself.
> Operators should not seed S3 manually for normal tenant onboarding. Persisted state lives
> under `platform-state/{team}/{service}/...`, with fallback restore from the legacy
> `platform-state/{service}/{team}/...` layout during migration.

> Current image limitation: the deployed OpenClaw build can refresh OAuth credentials in memory,
> but does not reliably persist the refreshed `auth-profiles.json` back to state.
> That requires an application-level fix in the OpenClaw image, not just GitOps changes.

> If a team wants headless setup or a non-OAuth provider, an API key can still be
> passed via `secret_env_vars`. Store it only at `secret/data/teams/{team}/{service}`,
> never in a platform-wide shared secret.

**Optional: preconfigure or add a key later**
```
mctl_deploy_service(
  action="update-config",
  team_name="my-team",
  component_name="openclaw",
  secret_env_vars="OPENAI_API_KEY=<openai-codex-api-key>"
)
```

## Release → Auto-Deploy Patterns

Two different conventions exist across mctlhq/* service repos for getting a
new version deployed after code merges to `main`. Check which one a repo
actually uses (grep its `.github/workflows/`) before assuming either —
`mctl_deploy_service`'s own onboarding guidance only documents pattern B,
which is now the less common one for actively-developed service repos.

**Pattern A — release-please + centralized dispatch (current default for
mctlhq/* org repos: mctl-agent, mctl-api, mctl-agents, mctl-docs,
mctl-portal, mctl-telegram).** `release-please` accumulates conventional
commits into a version-bump PR; merging it cuts a real tag + GitHub release
(`release_created == true`). A step in that same `release-please.yml`
job then mints a short-lived GitHub App token scoped to `mctl-gitops`
(`actions/create-github-app-token`, org secrets `APP_ID`/`APP_PRIVATE_KEY`)
and dispatches `mctl-gitops`'s `release-deploy.yaml` (`workflow_dispatch`)
with the new tag, image name, team, and component — that reusable workflow
builds the image and bumps `image.tag` in
`platform-gitops/services/<team>/<component>/values.yaml`, which ArgoCD then
syncs. Deploys are therefore versioned and deliberate (one per release), not
one per commit. Copy an existing repo's `release-please.yml` verbatim when
onboarding a new one — team_name/component_name/image_name are the only
things that change; add `values_path` or `values_glob` only if that repo's
gitops values file isn't at the default
`platform-gitops/services/<team>/<component>/values.yaml`.

Onboarding checklist for Pattern A on a **new** repo:
- `release-please.yml`'s deploy-dispatch step (above) — easy to forget if
  the repo starts release-please before it's actually onboarded as a
  service; nothing fails loudly when it's missing, releases just silently
  never deploy (this happened to mctl-academy — onboarded, but the dispatch
  step was never added after the fact; every release since produced a tag
  with nothing consuming it, until fixed in mctl-academy#154).
- The release-please PR itself needs a passing review to merge under normal
  branch protection (`required_approving_review_count: 1`). If the repo's
  `claude-review.yml` calls the centralized reusable workflow
  (`mctlhq/.github/.github/workflows/claude-review.yml`), its default
  `allowed-bots: mctl-claude-remote,github-actions` already covers this —
  nothing to add. If a repo instead inlines `claude-code-action` directly
  (older repos, pre-dating the reusable workflow), it needs
  `allowed_bots: "github-actions"` added explicitly or release-please PRs
  can never pass review — see the 11-repo fix landed 2026-07-31. Separately,
  first-time/held Actions runs on a release-please PR (`action_required`
  conclusion, 0 jobs started) are a different, unrelated gate — approve them
  with `gh api --method POST repos/<owner>/<repo>/actions/runs/<id>/approve`
  (once per held run) rather than treating that as a review-bot problem.

**Pattern B — direct per-push deploy (older/simpler repos: e.g.
mctl-instruments).** A `deploy` job in the repo's own `ci.yml` POSTs
straight to `https://api.mctl.ai/api/v1/operations/deploy-service/execute`
on every push to `main`, authenticated with a classic PAT
(`MCTL_GITHUB_TOKEN`, scope `read:user`) stored as a repo secret. No
release-please, no semver tag gate — every merge to main deploys. This is
what the scaffolding guide at docs.mctl.ai and `mctl_deploy_service`'s own
onboarding instructions describe; it's the simplest path for a brand-new
repo that doesn't need controlled/versioned releases, but do not assume an
established service repo uses it — check first.

## Deploy Actions

| Action | When to use | What happens |
|--------|-------------|--------------|
| `onboard` | First deploy of a service | Build image → create Helm manifests → commit to GitOps → ArgoCD sync |
| `deploy` | New version / image tag update | Rebuild image → update image tag in GitOps → ArgoCD sync |
| `update-config` | Env vars, secrets, resource changes | Update values.yaml only → ArgoCD sync (no rebuild) |

## Service Templates

| Template | Port | Memory | dockerfile_repo required? | Special Config |
|----------|------|--------|-----------------------------|----------------|
| `default` | 8080 | 256Mi | Yes | Standard HTTP service |
| `openclaw` | 18789 | 1Gi | No | Gateway config ConfigMap, 5min startup probe, `NODE_OPTIONS=--max-old-space-size=768` |

The `openclaw` template pre-configures: LAN bind, token auth, trusted K8s proxies, Control UI enabled.

**Rule:** when `service_template != "default"`, `dockerfile_repo` is optional. The platform uses the
pre-built image from the template. No GitHub Actions build is triggered.

## Repo Access Patterns

1. **Org repos** (`mctlhq/*`) — automatic via GitHub App, no setup needed
2. **User public repos** — install GitHub App: `mctl_grant_repo_access(team, repo)` → open URL → `mctl_sync_repos`
3. **External public repos** (e.g. `openclaw/openclaw`) — deploy directly, no registration needed
4. **Private external repos** — store PAT in Vault:
   ```
   secret/data/teams/{team}/{service}/repo-pat → {"pat": "ghp_..."}
   ```

## Vault Secrets Structure

- **Root Path:** `secret/` (KV version 2).
- **Platform Secrets:** System components use `platform/` (e.g., `platform/minio`, `platform/argo-workflows/database`).
- **Team Secrets:** Tenant apps use `teams/{team}/{service}/database`.
- **Internal URL:** `http://vault.vault.svc.cluster.local:8200`.
- **ExternalSecret:** Synced to K8s automatically via `ExternalSecret` resources.

## Workflow Tracking

Every write operation returns a `workflow_name`. Always follow up:
```
mctl_get_workflow_status(workflow_name)
→ Link: https://workflows.mctl.ai/workflows/{namespace}/{workflow_name}
```
Report the link to the user so they can monitor progress in the UI.
