# main-protection bypass actors

Who can write to `main` of this repository without a reviewed pull request,
why the current `DeployKey` bypass entry admits more than the two automated
writers it was meant for, and the staged plan that replaces it.

Written for mctlhq/mctl-gitops#2543 (P1, open). Sensitive specifics live in
the private repository security advisory; this page states the class of the
problem and the fix, nothing more. Nothing on this page has been executed:
every ruleset, key, secret and App step below is **operator-only** and waits
for the approvals listed under [Approvals](#approvals).

## The finding

Ruleset `18465404` (`main-protection`, active, `refs/heads/main`) requires a
pull request with one approval and the `validate`, `reserved-hosts` and
`cloudflare-plan` checks. Its only bypass actor is:

```json
{"actor_id": null, "actor_type": "DeployKey", "bypass_mode": "always"}
```

GitHub's REST reference states that for `actor_type: DeployKey` the
`actor_id` "should be null": a DeployKey bypass entry can never name one
key. It admits **every write deploy key on the repository**, present and
future. The ruleset cannot be narrowed to one key by editing this entry;
narrowing needs the writers to change identity.

On a public repository two other levers are also unavailable or weak:

- **Path restrictions.** Branch rulesets have no path condition, and a bypass
  actor skips every rule of the ruleset. Push rulesets (`file_path_restriction`)
  are documented for private and internal repositories only.
- **A required "bump-only" status check in a second ruleset.** Any principal
  that can push a branch here (both deploy keys can) can run a workflow that
  reports a check under the same name from the GitHub Actions integration, so
  the check would not prove what produced it. It also doubles every bump's
  push. It can be added later as defence in depth, not as the boundary.

## Inventory (read-only, 2026-11-11)

Reproduce with the commands in [Re-run the inventory](#re-run-the-inventory).

### Write deploy keys

| id | title | read_only | created | last_used (GitHub, coarse) |
|---|---|---|---|---|
| 165489378 | `gitops-bump` | false | 2026-10-05 | 2026-11-10T00:44Z |
| 166128843 | `argo-workflows-bot-2026-10` | false | 2026-10-11 | 2026-11-09T06:24Z |

`last_used` is not a per-push timestamp: 71 `mctl-agents[bot]` commits and 9
`mctl-ci` commits reached `main` after the respective `last_used` values. Use
it as "used recently", never as "unused since".

### Who uses which key to push to `main`

| key | holder | callers | committer identity on `main` |
|---|---|---|---|
| 165489378 | Actions environment `gitops-bump` (secret `GITOPS_BUMP_DEPLOY_KEY`, deployment branch policy: `main` only) | `.github/workflows/gitops-bump.yaml`, `bump` job of `.github/workflows/release-deploy.yaml` | `mctl-ci <ci@mctl.ai>` |
| 166128843 | Kubernetes Secret `mctl-gitops-deploy-key` from Vault `platform/argo-workflows/gitops-deploy-key`, in `argo-workflows` **and in every tenant namespace** (`helm-charts/tenant/templates/argo-workflow.yaml`) | `cwft-mctl-agents-{investigate,implement,shepherd,reconcile,approve,run}`, `tpl-git-commit`, `wft-deploy-service`, `wft-rollback-service`, `wft-create-tenant`, `wft-delete-tenant-safe`, `wft-retire-service`, `wft-provision-database`, `wft-{add,remove}-custom-domain`, `wft-platform-skill-*`, `wft-lifecycle-bootstrap` | `mctl-agents[bot]`, `argo-workflows[bot]`, `Argo Workflows Bot`, `mctl-rollback` |

The complete list of files that mount or render either credential is the
shrink-only ledger `tests/fixtures/gitops-write-credential-holders.yaml`,
enforced by `tests/test_gitops_write_credential_holders.py`.

### Direct pushes to `main` (first-parent, non-merge commits)

| author | since 2026-10-12 | since 2026-11-04 | paths |
|---|---|---|---|
| `mctl-agents[bot]` | 1199 | 313 | `platform-gitops/agents-state/**` only |
| `mctl-ci` | 1098 | 187 | 25 files: service `values.yaml`, `cwft-mctl-agents-*.yaml` image refs, `bootstrap/templates/mctl-platform/mctl-api.yaml` |
| `argo-workflows[bot]` | 77 | 2 | services, tenants, `infra-components/data`, `argocd/rbac`, `argo-workflows/sso-team-*.yaml` |
| `Argo Workflows Bot` | 9 | 0 | tenants, `argocd/rbac`, `argo-workflows/sso-team-*.yaml` |
| `mctl-rollback` | 1 | 0 | one service `values.yaml` |

All 2384 are unsigned (`%G? = N`). Commit metadata does not record which SSH
key pushed a commit; the key column above comes from the workflow and
template code that sets each identity, not from GitHub. 598 PR merge commits
landed on `main` in the same window.

`agents-state/**` (93% of the argo key's pushes) is not deployed by Argo CD:
`bootstrap/templates/bootstrap/applicationset-apps.yaml` limits refreshes to
app paths for exactly that reason (#970).

### Every principal that could put a commit on `main`

| principal | can push to `main` directly? | can change the ruleset? | verified how |
|---|---|---|---|
| deploy key 165489378 | **yes**, via the DeployKey bypass | no | ruleset + keys API |
| deploy key 166128843 (and every copy of the Secret) | **yes**, via the DeployKey bypass | no | ruleset + keys API |
| any write deploy key added later by an admin | **yes**, same entry | no | GitHub API reference |
| `mashkovd` (only org owner, only repo admin, no teams, no outside collaborators) | no: `current_user_can_bypass: never`, admin bypass removed 2026-08-25 | **yes**: an admin can edit or delete the ruleset (audited, deliberate) | collaborators / members / ruleset API |
| Apps with `contents: write` (`mctl-agents`, `claude`, `chatgpt-codex-connector`, `mctl-claude-remote` on all repos; `mctl-codex`, `mctl-gitops-pr`, `mctl-repo-bot` on selected repos) | no: none is a bypass actor; they can push branches and open PRs, which still need an approval and checks | no: no App on the org has repository `administration` permission | `orgs/mctlhq/installations` |
| `staten-platform-argocd` (`organization_administration: write`) | no | not a repository ruleset; an org ruleset can only add rules, its bypass list does not lift a repository ruleset | installations API |
| Actions `GITHUB_TOKEN` | no: default workflow permissions `read`, cannot approve PRs, not a bypass actor | no | `actions/permissions/workflow` |
| classic branch protection on `main` | adds no reviewer and no push restriction; blocks force-push and deletion | n/a | `branches/main/protection` |
| other rulesets | `14564982` (`main`, **disabled**, no bypass actors) | n/a | ruleset listing |

### What could not be verified

- **Fine-grained and classic personal access tokens.** Listing the org's
  fine-grained PATs needs a GitHub App token with organization permissions;
  classic PATs are invisible to the org. Any PAT inherits its user's rights,
  so the bound is the user table above (one admin, no bypass), but a PAT of
  `mashkovd` with `admin:repo` scope could edit the ruleset like the admin.
- **The repository list of `selected` App installations** (`mctl-codex`,
  `mctl-gitops-pr`, `mctl-repo-bot`, `staten-platform-argocd`,
  `mctl-gitops-dispatch`): the user-token endpoint refuses it. None is a
  bypass actor and none has `administration`, so this does not change the
  table, but which of them can push branches here is unconfirmed.
- **What changed in the ruleset at `updated_at` 2026-11-09T11:38Z.** The org
  is on the Free plan; the audit-log API is not available. Check
  Settings → Rules → main-protection → history in the UI.
- **Which pods actually read the Secret at runtime**, and every reader with
  cluster-wide Secret access: covered by the owner's phase-1 inventory on
  #2543, not repeated here (this repository is public).
- **Whether a write deploy key may push changes under `.github/workflows/`.**
  GitHub documents the `workflows` permission for Apps and OAuth tokens;
  for deploy keys this was not tested (no live write was attempted).
- **Whether an App's approving review satisfies the `pull_request` rule.**
  That is the PR path, not the bypass; untested here.

## Options

| option | closes the wildcard? | breaks the deploy path? | verdict |
|---|---|---|---|
| (a) Replace the DeployKey entry with GitHub Apps that have resolvable ids | yes | no, if each writer moves first | **chosen**, staged below |
| (b) Path restrictions in a ruleset | no: not available for a public repo, and bypass skips all rules anyway | n/a | rejected |
| (c) Required "bump-only" status check | no: forgeable by any branch writer, doubles pushes | adds latency | defence in depth later, not the boundary |
| delete one deploy key now | no: the entry still admits the other key | yes, either path stops | rejected (#2543: never just delete a live key) |

The smallest change that closes the wildcard without stopping deploys is
(a), in three operator stages. It closes the **class** (any write deploy key,
present or future, including every tenant-namespace copy of the Argo key).
It does **not** by itself close the broader #2543 concern that the Argo
writer's content is model-influenced: Stage 2A keeps one powerful,
transitional bypass for that writer, with an expiry the verifier enforces.
#2543 stays P1 and open until Stage 2B removes that entry too.

### Stage 1: the CI bump path gets its own App

1. Owner creates a GitHub App `mctl-gitops-bump-writer`: owner `mctlhq`,
   no webhook, repository permissions `contents: write` (and the implied
   `metadata: read`) **only**: no `workflows`, no `administration`, no
   `pull_requests`. Install it on `mctl-gitops` only.
2. Owner stores its private key as environment secret
   `GITOPS_BUMP_APP_PRIVATE_KEY` of environment `gitops-bump` (deployment
   branch policy stays `main`) and its Client ID as an environment variable.
   Never as a repository or organization secret.
3. Read the App id (public): `gh api apps/mctl-gitops-bump-writer --jq .id`.
4. Ruleset change S1 (adds the App next to the DeployKey entry; the
   wildcard is still there).
5. Code PR (reviewed): `gitops-bump.yaml` and `release-deploy.yaml` mint a
   token with `actions/create-github-app-token` (`repositories: mctl-gitops`,
   `permission-contents: write`) and check out with it instead of `ssh-key`.
   Update the holder ledger and `scripts/ruleset-bypass-allowlist.json` in the
   same PR.
6. Watch three real bumps land (`git log --first-parent --author=mctl-ci`).
7. Owner deletes environment secret `GITOPS_BUMP_DEPLOY_KEY`, then deploy key
   165489378.

### Stage 2A (transitional): the Argo writer gets its own App

Prerequisite, reviewed separately: no tenant namespace holds the write
credential any more. Commit steps that run in tenant namespaces hand their
change to a writer step in `argo-workflows` (or to the broker of #2543
option B); otherwise a new App key would spread exactly like the deploy key.

1. Owner creates `mctl-gitops-argo-writer`, same permission shape as Stage 1,
   installed on `mctl-gitops` only. Its key goes to Vault and is mounted only
   in the commit steps of `argo-workflows` (never in an agent container, an
   agent-writable worktree, or a tenant namespace).
2. Ruleset change S2 (adds it, entry carries an `expires` date in the
   allowlist, at most 30 days).
3. Code PR: templates mint an installation token in the commit step and push
   with it; ledger and allowlist updated in the same PR.
4. Watch one of each: DevLoop state write, deploy-service, rollback,
   create-tenant.

### Stage 3: remove the wildcard

1. Ruleset change S3 (DeployKey entry gone).
2. Owner deletes deploy key 166128843, removes `platform/argo-workflows/gitops-deploy-key`
   from Vault and the ExternalSecrets (ledger rows shrink in the same PR).
3. `python3 -I scripts/check-ruleset-bypass-actors.py --gh` exits 0.

### Stage 2B (target, separate issue): the Argo writer loses its bypass

`agents-state/**` moves off `main` (its own branch with its own ruleset, or
its own repository); the remaining ~90 deploy/tenant/rollback writes a month
go through pull requests merged by the trusted writer or the #2543 broker.
Ruleset change S4 then leaves the bump App as the only bypass actor.

## Ruleset payloads (reviewed text, NOT executed)

Each change replaces only `bypass_actors`. Take a snapshot first, apply,
then diff to prove nothing else moved. `<BUMP_APP_ID>` and `<ARGO_APP_ID>`
are the integer ids from `gh api apps/<slug> --jq .id`. Write each payload
to a scratch file outside the checkout.

S1, after Stage 1 step 3:

```json
{"bypass_actors": [
  {"actor_id": null,          "actor_type": "DeployKey",   "bypass_mode": "always"},
  {"actor_id": <BUMP_APP_ID>, "actor_type": "Integration", "bypass_mode": "always"}
]}
```

S2, after Stage 2A step 1:

```json
{"bypass_actors": [
  {"actor_id": null,          "actor_type": "DeployKey",   "bypass_mode": "always"},
  {"actor_id": <BUMP_APP_ID>, "actor_type": "Integration", "bypass_mode": "always"},
  {"actor_id": <ARGO_APP_ID>, "actor_type": "Integration", "bypass_mode": "always"}
]}
```

S3, closes the wildcard:

```json
{"bypass_actors": [
  {"actor_id": <BUMP_APP_ID>, "actor_type": "Integration", "bypass_mode": "always"},
  {"actor_id": <ARGO_APP_ID>, "actor_type": "Integration", "bypass_mode": "always"}
]}
```

S4, target:

```json
{"bypass_actors": [
  {"actor_id": <BUMP_APP_ID>, "actor_type": "Integration", "bypass_mode": "always"}
]}
```

Apply (operator, as `mashkovd`):

```sh
R=repos/mctlhq/mctl-gitops/rulesets/18465404
TS=$(date -u +%Y%m%dT%H%M%SZ)
gh api "$R" > "fix2543-before-${TS}.json"
gh api -X PUT "$R" --input fix2543-S<n>.json > "fix2543-after-${TS}.json"
# nothing but bypass_actors (and updated_at) may differ:
diff <(jq -S 'del(.bypass_actors,.updated_at,.current_user_can_bypass)' "fix2543-before-${TS}.json") \
     <(jq -S 'del(.bypass_actors,.updated_at,.current_user_can_bypass)' "fix2543-after-${TS}.json")
jq .bypass_actors "fix2543-after-${TS}.json"
python3 -I scripts/check-ruleset-bypass-actors.py --gh
```

Rollback (restores the exact prior list, wildcard included; use only when
the automated deploy path is broken, and say so on #2543):

```sh
jq '{bypass_actors}' "fix2543-before-${TS}.json" | gh api -X PUT repos/mctlhq/mctl-gitops/rulesets/18465404 --input -
```

Never delete or disable the ruleset as a rollback, and never re-add the
`mctl-agents` App or the admin role as a bypass actor.

## The verifier

`scripts/check-ruleset-bypass-actors.py` reads every ruleset that applies to
the repository and compares the bypass actors with
`scripts/ruleset-bypass-allowlist.json`. Exit 0 clean, 10 findings, 20
unknown. A null or non-integer `actor_id`, an actor that is not allowlisted,
more actors than allowlist entries, an expired transitional entry, or
`main-protection` missing, disabled, no longer covering `main` (include or
exclude, matched the way GitHub does: a single `*` does not cross `/`),
missing one of its `required_rules`, requiring fewer approvals than
`min_approving_review_count`, or missing a context in
`required_status_checks` is a finding. A failed,
partial or malformed read, or a response without `bypass_actors`, is
unknown, never clean.

It is an **operator check**, not a scheduled CI job: GitHub returns
`bypass_actors` only to a caller that can edit the ruleset, and `GITHUB_TOKEN`
has no repository administration permission. A scheduled job would need an
admin-capable credential in Actions, which is a worse exposure than the one
it watches. CI runs the self-test (`tests/test_ruleset_bypass_check.py`) in
the `validate` job.

Today the live result is `findings` (exit 10) on purpose: the allowlist is
empty and the DeployKey entry is present.

## Re-run the inventory

```sh
gh api repos/mctlhq/mctl-gitops/rulesets/18465404 --jq '{enforcement,bypass_actors,updated_at}'
gh api repos/mctlhq/mctl-gitops/keys --jq '.[]|{id,title,read_only,created_at,last_used}'
gh api 'repos/mctlhq/mctl-gitops/collaborators?affiliation=all' --jq '.[]|select(.permissions.push)|.login+" "+.role_name'
gh api orgs/mctlhq/installations --jq '.installations[]|"\(.app_slug) \(.repository_selection) contents=\(.permissions.contents) admin=\(.permissions.administration)"'
git log --first-parent --no-merges --since=2026-10-12 origin/main --format='%an' | sort | uniq -c
python3 -I scripts/check-ruleset-bypass-actors.py --gh
```

Never print a key body, a Secret's `.data` or a token while doing this.

## Approvals

Per #2543: independent Claude and agy review of the staged proposal, then a
separate, exact-digest approval by the owner (`mashkovd`, the only org owner
and repository admin, and therefore the only principal who can execute any
ruleset or key step). Each stage is its own approval; Stage 3 is not
implied by Stage 1. Update the private advisory at each stage.

## Residual risk

- Until Stage 3, every write deploy key, and every holder of a copy of the
  Argo key's Secret, can push to `main` without review.
- After Stage 3 and before Stage 2B, the Argo writer App is still a
  repository-wide bypass: its commit steps remain a trusted boundary whose
  content the model influences (#2543 phase 1). The allowlist expiry makes
  that window visible; it does not make it safe.
- The admin can always edit the ruleset. That is deliberate and audited, and
  the verifier will show it afterwards, not prevent it.
- The verifier sees a change only when an operator runs it.
