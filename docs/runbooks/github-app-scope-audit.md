# GitHub App scope audit

Which GitHub App backs which automation, what permission each consumer
actually needs, and the rule for adding new ones.

Written for mctlhq/mctl-gitops#761. Audit performed 2026-08-10, applied
2026-08-13.

## The rule

**MCTL App never gets write.**

`mctl-app` is the App customers install themselves from
`mctl.ai/#request-access`. Its published description says:

> MCTL needs limited access to automate GitHub Actions and manage
> deployments. We follow the principle of least privilege and request only
> what is necessary to operate securely.

New internal automation goes on `mctl-agents`. If you find yourself adding
`secrets.APP_ID` to a workflow that pushes, opens a PR, or dispatches
anything, that is the wrong App.

## Why the split is forced, not stylistic

A GitHub App's permissions are **declared once on the App** and apply
identically to **every installation** — mctlhq's own and each customer's.
There is no per-installation narrowing: `repository_selection` limits
*which repos* an installation covers, never *what may be done* to them.

So "write for us, read for customers" is not expressible on one App. The
only mechanism is two Apps with different audiences.

This is also why the drift kept recurring: whenever an internal workflow
needed one more permission, the path of least resistance was to widen the
App — and every widening silently landed on customers too. See #761 for the
2026-08-03 instance.

## The two Apps

| | `mctl-app` (MCTL App) | `mctl-agents` |
|---|---|---|
| app_id | `2902192` | `4450852` |
| mctlhq installation | `114645135` | `150422769` |
| Vault creds | `secret/platform/github-app` | `secret/platform/github-app-agents` |
| Actions secrets | `APP_ID` / `APP_PRIVATE_KEY` | `AGENTS_APP_ID` / `AGENTS_APP_PRIVATE_KEY` |
| Audience | **customers** install it | internal only, never offered |
| Target permissions | `contents:read`, `metadata:read` | `contents/issues/pull_requests/workflows:write`, `actions:write`, `checks:read`, `metadata:read` |

`mctl-agents` is also the App on the `main-protection` ruleset's
`bypass_actors` list (ruleset `18465404`), which is what lets the tag-bump
workflows push straight to `main`.

## Consumers

### MCTL App — the only legitimate uses

| Consumer | Needs |
|---|---|
| `.github/workflows/build-image.yaml` Tier 2 | `contents:read` — checks out the **customer's** repo to build its image. Pinned with `permission-contents: read`. |
| `mctl-portal` `plugins/github-app-connect-backend/src/router.ts` (`GET /repos/{repo}`, `/tags`, `/contents/{path}`) | `contents:read`, `metadata:read` — repo discovery for the connect flow |
| OAuth sign-in at `mctl.ai` (`OAUTH_GITHUB_CLIENT_ID/SECRET` ← `platform/github-app`, wired in `bootstrap/templates/mctl-platform/mctl-api-secrets.yaml`) | client id/secret only. Note a user-to-server token is bounded by the App's declared permissions, so narrowing the App also narrows what a signed-in user's token can do. |

### mctl-agents — everything internal

| Consumer | Needs |
|---|---|
| `release-deploy.yaml` / `gitops-bump.yaml` bump jobs | `contents:write` on mctl-gitops + ruleset bypass |
| `release-please.yml` dispatch step in mctl-api, mctl-agent, mctl-agents, mctl-portal, mctl-docs, mctl-academy, mctl-telegram, mctl-design, pfeifenpatenschaft-backend | `actions:write` on mctl-gitops |
| `mctl-telegram/.github/workflows/preview-deploy.yml` | `actions:write` on mctl-gitops |
| `mctl-agents/.github/workflows/release-please.yml` release-please step | `contents/pull_requests/issues:write` on mctl-agents |
| `cwft-rotate-github-token.yaml`, both targets | mints the tokens `mctl-agent` and `mctl-agents` consume |

## Things that were removed rather than repointed

Both were live consumers of MCTL App's private key that turned out to do
nothing:

- **`tpl-git-commit.yaml`** mounted the key and signed a JWT to mint an
  installation token on every run. `$GH_TOKEN` was set, null-checked, and
  never read — all git traffic goes over the SSH deploy key. Block and
  mount deleted (#785).
- **`github:actions:dispatch-and-stream`** (mctl-portal
  `scaffolderActions.ts`) dispatched a workflow in an arbitrary repo and
  streamed its logs. No scaffolder template ever called it. It was the only
  code justifying `actions:write` on customer repos. Deleted
  (mctl-portal#56).

## Open decision: `members:read`

`members:read` is **not** unused, contrary to the first pass of this audit.

`infrastructure/k3s-preview/cluster-bootstrap/helm-values/argocd.yaml`
bootstraps ArgoCD with a dex **GitHub** connector using
`$github-client-id` / `$github-client-secret` (synced from
`platform/github-app` by `platform-gitops/argocd/templates/argocd-github-oauth.yaml`)
and gates on `orgs: [mctlhq]`. Resolving org membership is exactly what
`members:read` backs.

The self-managed production ArgoCD does **not** use this — it runs an OIDC
connector against Backstage (`platform-gitops/argocd/values.yaml`), so the
GitHub connector only matters during bootstrap.

Either:

1. Migrate the preview bootstrap to the same Backstage OIDC connector prod
   already uses, then drop `members:read` and the two ExternalSecret keys; or
2. Keep `members:read` on MCTL App and accept that customers are asked for
   org-membership read.

Option 1 is the one consistent with the rule at the top of this file.
Not yet done — it changes how operators log in to the preview cluster's
ArgoCD, so it needs a deliberate window rather than riding along with a
scope cleanup.

## Verifying current state

```bash
# Declared permissions, per App, as actually installed
gh api orgs/mctlhq/installations \
  --jq '.installations[] | select(.app_slug|test("^mctl-")) |
        {app_slug, app_id, repository_selection, permissions}'

# Every workflow still minting as MCTL App across the workspace.
# Expected: only mctl-gitops/.github/workflows/build-image.yaml
grep -rn "secrets.APP_ID" --include="*.yml" --include="*.yaml" .
```

`gh api repos/mctlhq/<repo>/collaborators/mctl-app[bot]/permission` is
**not** a valid check — it returns `"none"` for installed Apps that plainly
have write. Use the installations endpoint above.
