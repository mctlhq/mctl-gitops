# GitHub App scope audit

Which GitHub App backs which automation, what permission each consumer
actually needs, and the rule for adding new ones.

Written for mctlhq/mctl-gitops#761. Audit performed 2026-08-10, applied
2026-08-13/14. **Complete** — MCTL App is now `contents:read` +
`metadata:read`, verified through the installations endpoint:

```
mctl-app     {"contents":"read","metadata":"read"}
mctl-agents  {"actions":"write","checks":"read","contents":"write",
              "issues":"write","metadata":"read","pull_requests":"write",
              "workflows":"write"}
```

## The rule

**MCTL App never gets write.**

`mctl-app` is the App customers install themselves from
`mctl.ai/#request-access`. Its published description says:

> MCTL needs limited access to automate GitHub Actions and manage
> deployments. We follow the principle of least privilege and request only
> what is necessary to operate securely.

That text is now **stale** — the App has no Actions permission at all. The
"Add a note to users" field still carries it; replacing it is pending, and
the field has a hard **240-character limit** that rejects the whole form
submission (the existing text must be cleared first, not appended to).

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

## `members:read` — resolved, no consumer

An intermediate pass of this audit claimed `members:read` was load-bearing
because `infrastructure/k3s-preview/cluster-bootstrap/helm-values/argocd.yaml`
bootstrapped ArgoCD with a dex **GitHub** connector gated on
`orgs: [mctlhq]`. That connector existed, but it could never function, so
the permission had no working consumer.

ArgoCD's live SSO is the OIDC connector against Backstage in
`platform-gitops/argocd/values.yaml`, applied by the `argocd-self-managed`
Application. The Terraform values are a **one-shot bootstrap**
(`bootstrap_argocd`, default `false`, deliberately removed from state — see
`cluster-bootstrap/argocd.tf`), and `argocd-self-managed` overwrites
`dex.config` as soon as it first syncs.

The GitHub connector referenced `$github-client-id` / `$github-client-secret`.
Those keys are written into `argocd-secret` by
`platform-gitops/argocd/templates/argocd-github-oauth.yaml` — part of the
**self-managed chart**, not of the bootstrap release. So:

- during bootstrap the keys do not exist yet (nor does ESO, which arrives via
  `root-app`), and dex cannot resolve them;
- by the time they exist, the same sync has already replaced `dex.config`
  with the Backstage connector.

Dead in every state. The connector and the two now-orphaned ExternalSecret
keys were removed (#788), and `members:read` dropped from MCTL App.

There is consequently no ArgoCD SSO between the bootstrap release coming up
and `argocd-self-managed` syncing — unchanged behaviour, now documented in
`infrastructure/k3s-preview/README.md` under "Disaster recovery" (`argocd
--core` against the kubeconfig Terraform just wrote).

Note: because that ExternalSecret targets `argocd-secret` with
`creationPolicy: Merge`, ESO does not delete keys it stops managing — so
`github-client-id` / `github-client-secret` lingered in the live secret
after the chart stopped writing them. **Deleted by hand 2026-08-13** and
confirmed not to return across a forced ESO resync. Note this was only safe
after #790: while the ExternalSecret still listed them, ESO rewrote both
within seconds of any deletion.

## Verifying current state

```bash
# Declared permissions, per App, as actually installed
gh api orgs/mctlhq/installations \
  --jq '.installations[] | select(.app_slug|test("^mctl-")) |
        {app_slug, app_id, repository_selection, permissions}'

# Every workflow still minting as MCTL App across the workspace.
# Expected: only mctl-gitops/.github/workflows/build-image.yaml
grep -rnE '^[^#]*\$\{\{ *secrets\.APP_(ID|PRIVATE_KEY) *\}\}' \
  --include="*.yml" --include="*.yaml" .
```

Anchor the pattern outside comments. Several workflows now carry an
explanatory line naming `secrets.APP_ID` precisely to say they must *not*
use it; a bare `grep -rn "secrets.APP_ID"` reports all of them and makes a
clean workspace look dirty.

`gh api repos/mctlhq/<repo>/collaborators/mctl-app[bot]/permission` is
**not** a valid check — it returns `"none"` for installed Apps that plainly
have write. Use the installations endpoint above.

## Changing an App's permissions

Both directions go through the App's own settings page
(`/organizations/mctlhq/settings/apps/<slug>/permissions`) — there is no
REST endpoint for editing declared permissions.

**Widening takes two steps.** Saving on the App page only updates the
declaration; every existing installation keeps its old grant until it
*accepts* the change at
`/organizations/mctlhq/settings/installations/<installation_id>`, where a
banner reads "<app> is requesting an update to its permissions". This bit
the `actions: read → write` change on `mctl-agents`: the API still reported
`"actions":"read"` after a successful save, and only flipped after the
installation was accepted.

**Narrowing applies immediately** — no acceptance step, no banner.

Verify either way through `gh api orgs/mctlhq/installations`, not the page.
