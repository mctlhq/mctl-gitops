# Design: issue-761-audit-and-narrow-mctl-app-mctl-agents-gi

## Current state

Grounded in what is actually readable in this `mctl-gitops` clone.

### The two Vault-backed app credentials and their rotation

`platform-gitops/argo-workflows/cluster-templates/cwft-rotate-github-token.yaml`
is the single source of truth for both apps' installation-token lifecycle.
It runs every 30 minutes (installation tokens expire after 60) and defines
two `TARGETS`:

```
{"label": "mctl-agent",  "creds_path": "platform/github-app",         "dest_path": "platform/mctl-agent/tokens", "dest_key": "github-token",
 "es_namespace": "admins", "es_name": "admins-mctl-agent-base-service"}
{"label": "mctl-agents", "creds_path": "platform/github-app-agents",  "dest_path": "platform/mctl-agents",       "dest_key": "github-token",
 "es_namespace": "argo-workflows", "es_name": "mctl-agents-secrets"}
```

The template's header comment records the app IDs: `mctl-agent` ->
2902192, `mctl-agents` -> 4450852. These match the issue's audit table
exactly for `mctl-app` (app_id 2902192) and `mctl-agents` (app_id 4450852)
— i.e. **the app GitHub calls `mctl-app` is labeled `mctl-agent` (singular)
inside this repo's rotation config.** The template's own annotation says it
was "Renamed 2026-08-01 from rotate-mctl-agent-github-token (singular) now
that it rotates for both mctl-agent and mctl-agents" — the CronWorkflow
name was fixed, but the internal `label`/Vault-path naming for the first
target was not, leaving `mctl-app` (GitHub's name) / `mctl-agent` (this
repo's internal label) as two names for one app. This is exactly the kind
of drift that makes an audit like #761 hard to trust — a future reader
grepping for "mctl-app" in this repo will not find this target.

### Consumers of `platform/github-app` (app_id 2902192, GitHub name `mctl-app`)

Found via grep for `APP_ID`, `APP_PRIVATE_KEY`, `github-app`,
`create-github-app-token` across `platform-gitops/` and `.github/`:

1. `platform-gitops/argo-workflows/cluster-templates/tpl-git-commit.yaml`
   — mounts `github-app-credentials` (secret, `optional: true`) at
   `/var/run/secrets/github-app` in both `commit-service` and
   `delete-service` templates. Used only for an opportunistic API-call
   token (`GH_TOKEN`); the actual git push authenticates over SSH via a
   separate `mctl-gitops-deploy-key` secret, so this app credential is
   non-critical here per the template's own comment ("non-fatal, git uses
   SSH deploy key"). This is the workflow behind every
   `mctl_deploy_service action=onboard|deploy|update-config` call.
2. `.github/workflows/build-image.yaml` — Tier 2 fallback
   (`create-github-app-token`, `continue-on-error: true`) used ONLY when
   a per-team Vault PAT (`teams/<team>/<component>/repo-pat`, Tier 1) is
   absent. Critically, this call already passes
   `repositories: ${{ steps.vault_pat.outputs.repo_name }}` — i.e. it
   already *requests* a token scoped to one repo. Today that scoping is
   advisory only, because the installation covers "all repos" so the
   call can mint a token for literally any repo passed in; narrowing
   `repository_selection` to `selected` is what turns this existing
   per-call scoping into an actual enforced boundary.
3. `platform-gitops/bootstrap/templates/mctl-platform/mctl-portal.yaml`
   — Backstage's GitHub integration: `GITHUB_APP_ID`,
   `GITHUB_APP_PRIVATE_KEY`, `GITHUB_APP_INSTALLATION_ID` sourced from
   the same `platform/github-app` Vault path, used for Backstage's
   GitHub auth provider and (per the `integrations.github[].apps` Helm
   values referenced at lines ~318-327) its scaffolder/catalog GitHub
   API calls.
4. `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-secrets.yaml`
   — same Vault path, feeding `mctl-api` (the platform API backend).
5. `platform-gitops/argocd/templates/argocd-github-oauth.yaml` — ArgoCD
   SSO login, same Vault path.
6. `cwft-rotate-github-token.yaml` itself (mints/rotates it).

### Consumers of `platform/github-app-agents` (app_id 4450852, `mctl-agents`)

1. `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`
   — the Tier 2 implementer. Reads `GITHUB_TOKEN` from
   `mctl-agents-secrets` key `github-token` (the exact secret
   `cwft-rotate-github-token.yaml` writes). Documented requirement:
   "PAT must have repo write scope on `mctlhq/*`" — this is the token
   used for `gh repo clone` + `gh pr create` against whichever service
   repo a proposal targets. `GITHUB_TOKEN_FILE` is re-read before every
   `gh`/`git` call so a long-running implementation survives the ~60 min
   token TTL via the 30-minute rotation.
2. `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`
   / `cronworkflow-mctl-agents-shepherd.yaml` — drives PRs through review
   to merge; needs the same write scope on whatever repo the PR lives in.
3. `cwft-mctl-agents-issue-poll.yaml` / `cwft-mctl-agents-investigate.yaml`
   — comment back on GitHub issues (`issues:write`) across whichever repo
   the triggering issue lives in (any `mctlhq/*` repo, per
   `mctl_trigger_issue`'s `issue_url` parameter accepting any org repo).
4. `cwft-rotate-github-token.yaml` itself (mints/rotates it).

The set of repos the agents pipeline actively manages proposals for today
is exactly the directory list under `platform-gitops/agents-state/`
(excluding `_mentor` and `OPERATOR.md`, which are not per-repo):
`mctl-academy, mctl-agent, mctl-agents, mctl-api, mctl-design, mctl-docs,
mctl-gitops, mctl-openclaw, mctl-pairdesk, mctl-portal, mctl-telegram,
mctl-web` — 12 repos. The issue states the org has 16 repos total, so at
least 4 org repos exist that the agents pipeline has no active proposal
history for.

### Things this clone cannot answer

This is a single, read-only clone of `mctl-gitops`. It cannot see:
- The other 15 org repos' own workflow files (e.g. `mctl-api`'s and
  `mctl-agents`'s release-please workflows, referenced by name in the
  issue and in `docs/` proposal files across `agents-state/*/proposals/`,
  but not present in this clone).
- Which repos actually have `APP_ID`/`APP_PRIVATE_KEY` org secrets wired
  into a `create-github-app-token` step, versus repos that merely dispatch
  `gitops-bump.yaml`/`release-deploy.yaml` in this repo using a token
  minted elsewhere.
- The live GitHub API state (`gh api orgs/mctlhq/installations`) — the
  issue's own audit table is already a point-in-time snapshot the design
  treats as ground truth for current scope, but any change to it since
  2026-08-08 is invisible here.

## Proposed solution

Given the human-in-the-loop constraint (GitHub's app-permission/scope
changes require an org owner in a sudo-mode-gated UI — no API path exists
in this environment), this proposal's deliverable is a decision-ready audit
artifact plus the minimum workflow-side documentation change, not a
mechanical repo edit that narrows anything by itself.

1. **Commit an audit findings document** at
   `docs/runbooks/github-app-scope-audit.md`. Contents:
   - The two apps, their app_id, current `repository_selection`, and
     current permission grants (transcribed from the issue's live-audit
     table, dated).
   - The consumer list above, each with file path + one-line justification
     (exactly what this design section already establishes, reused instead
     of re-derived).
   - The recommended narrowed repo list per app:
     - `mctl-app`: repos with a `platform-gitops/services/<team>/<x>/`
       directory or `mctl-api`/`mctl-portal` bootstrap wiring — i.e. repos
       actually deployed through `tpl-git-commit.yaml`/`build-image.yaml`,
       plus `mctl-gitops` itself (self-referential: the app must be able
       to see the repo whose settings it is used from, for Backstage/ArgoCD
       OAuth). Marked provisional pending the Backstage/ArgoCD SSO open
       question (see requirements.md) — narrowing this app is higher risk
       because login-flow breakage is user-facing and immediate, unlike a
       deploy pipeline hiccup.
     - `mctl-agents`: the 12-repo `agents-state/` roster, since that is the
       verifiable, evidence-backed "repos the agent pipeline actually opens
       PRs/issues against" list requested in issue item 3. Adding a 13th
       repo to the agents pipeline becomes an explicit two-step change:
       onboard it under `agents-state/`, AND add it to this app's repo
       list — preventing silent scope creep for a repo nobody currently
       automates.
   - An explicit "NOT YET VERIFIED — requires org-wide `gh` access" section
     listing the exact commands to complete the cross-repo sweep (below),
     so a human operator (or a follow-up agent run with broader repo
     access) can close the remaining gap without re-deriving the approach:
     ```
     gh api orgs/mctlhq/installations
     for repo in $(gh repo list mctlhq --limit 100 --json name -q '.[].name'); do
       gh secret list -R "mctlhq/$repo" 2>/dev/null | grep -qE '^(APP_ID|APP_PRIVATE_KEY)\b' \
         && echo "$repo: has APP_ID/APP_PRIVATE_KEY org-style secret"
       gh api "repos/mctlhq/$repo/contents/.github/workflows" --jq '.[].name' 2>/dev/null \
         | xargs -I{} gh api "repos/mctlhq/$repo/contents/.github/workflows/{}" --jq '.content' 2>/dev/null \
         | base64 -d 2>/dev/null | grep -l create-github-app-token && echo "$repo: uses create-github-app-token"
     done
     ```
   - A short "why this happened" postmortem paragraph cross-referencing the
     2026-08-03/05 incident and the pattern to avoid ("fixing" a permission
     issue at the installation-wide level instead of the specific repo).

2. **Reconcile the `mctl-agent`/`mctl-app` naming drift** in
   `cwft-rotate-github-token.yaml`: rename the first target's `label` from
   `"mctl-agent"` to `"mctl-app"` (matching GitHub's actual app name) and
   update the header comment's target list line accordingly. This is a
   comment/string-literal-only change — `creds_path`, `dest_path`,
   `dest_key`, `es_namespace`, `es_name` are untouched, so no Vault path or
   ExternalSecret target moves. Low risk, purely a clarity fix that makes
   future audits (including automated greps like this one) actually find
   this target when searching for "mctl-app".

3. **Document the per-team-PAT pattern as the target shape for new
   consumers**, referencing `build-image.yaml`'s existing Tier 1 (Vault
   PAT at `teams/<team>/<component>/repo-pat`, tried before the Tier 2 App
   token fallback) directly in the new runbook. No code change needed here
   — the pattern already exists and already works; the runbook just states
   it as policy: *"a new automation that needs write access to exactly one
   repo should get a scoped Vault PAT for that repo, not be added as a new
   caller of the shared org-wide app."*

4. **Leave the actual GitHub App installation edit as a documented manual
   step** in the runbook: which org owner action to take (App settings ->
   Repository access -> Only select repositories -> pick the narrowed
   list from step 1), and what to verify afterward
   (`gh api orgs/mctlhq/installations` should show `repository_selection:
   "selected"` and the expected repo count for each app).

No Helm chart, RBAC, or ExternalSecret changes are needed for this
proposal — narrowing `repository_selection` does not change which Vault
path/Kubernetes Secret a workflow reads from, only which repos the minted
installation token is valid against. If a repo is removed from either
app's install and a workflow later tries to mint a token scoped to it
(e.g. `build-image.yaml`'s Tier 2 fallback, or the implementer opening a
PR against a repo not in the narrowed list), the GitHub API call fails
loudly (a `create-github-app-token` step errors, or the implementer's
`gh pr create` 404s) rather than silently degrading — this is the intended
fail-closed behavior of narrowing.

## Alternatives

1. **Have this proposal directly edit `repository_selection` via the
   GitHub API/CLI.** Rejected: issue item 5 states plainly that this
   requires org-owner sudo-mode UI approval; there is no automatable path,
   and no `gh`/API credential available to this agent even if there were.
2. **Skip the audit-document deliverable and just recommend "narrow both
   apps to selected repos" in the PR description.** Rejected: the issue
   explicitly asks for an enumerated, evidence-backed consumer list (item
   1) that an org owner can review before clicking through a
   permission-narrowing confirmation that is hard to reverse-engineer
   after the fact. A throwaway PR description doesn't survive as the
   reference doc the next audit (or the next incident) needs.
3. **Migrate every consumer to a per-repo fine-grained PAT immediately,
   retiring both shared apps.** Rejected for this pass: issue item 4 asks
   only to *decide* whether shared apps are still the right shape, not to
   execute a full migration; the implementer/shepherd pipeline's dynamic,
   any-`mctlhq/*`-repo PR-authoring need is a poor fit for a single
   pre-provisioned per-repo PAT and would need its own design (e.g. a
   PAT-per-active-proposal-repo scheme) — scoped out per requirements.md.

## Platform impact

- **Migrations / backward compatibility:** none required by this proposal
  itself. The rotation CronWorkflow's `label` rename (step 2) is a
  string-only change with no Vault path, secret name, or ExternalSecret
  reference changes, so it is a no-op for every consumer.
- **Resource impact:** none — this is documentation plus one comment/label
  edit in an existing CronWorkflow template.
- **Risks:**
  - The eventual manual narrowing (once an org owner executes it) can break
    any consumer this audit missed, especially ones in the 15 repos this
    clone cannot see. Mitigation: the runbook's explicit "NOT YET
    VERIFIED" section with ready-to-run commands, and the recommendation
    to narrow `mctl-agents` first (12-repo evidence is strong, blast
    radius is "agent PR pipeline fails on an unlisted repo," which is
    loud and low-stakes) before `mctl-app` (weaker evidence around
    Backstage/ArgoCD SSO's actual repo-visibility needs, blast radius is
    "operators can't log in").
  - `create-github-app-token` in `build-image.yaml` already
    `continue-on-error: true`s and falls through to `github.token` for
    public repos — a narrowed `mctl-app` failing to mint a token for a
    private repo not on its list would silently degrade to using
    `github.token`, which likely lacks cross-repo checkout rights and
    fails at the checkout step instead, not silently. Flagged in the
    runbook as a specific case to smoke-test after narrowing.
  - Renaming the rotation label (`mctl-agent` -> `mctl-app`) touches a
    CronWorkflow that runs every 30 minutes; mitigated by the change being
    string-literal-only (no path/key changes) and by the standard "wait
    ~3 min for ArgoCD sync, then watch the next scheduled rotation tick"
    verification already documented in this repo's `CLAUDE.md`.
