# Audit and narrow mctl-app / mctl-agents GitHub App permissions

## Context

Two shared GitHub Apps back nearly all of the platform's GitHub automation:

- `mctl-app` (installation 114645135, app_id 2902192) — used for gitops
  commit tokens, Backstage OAuth login, and ArgoCD SSO login. In this repo
  its Vault-facing label is `platform/github-app`, but the rotation
  CronWorkflow (`cwft-rotate-github-token.yaml`) calls the same app_id
  `mctl-agent` (singular) — a naming drift the audit should reconcile.
- `mctl-agents` (installation 150422769, app_id 4450852) — mints the
  `GITHUB_TOKEN` the Tier 2/3 mctl-agents pipeline (implementer, shepherd)
  uses for `gh repo clone` + `gh pr create` against `mctlhq/*` repos.

Both installations currently have `repository_selection: "all"` (org-wide,
all 16 repos) with write scopes (`contents`, `issues`, `pull_requests`, and
for `mctl-agents` also `workflows`). Per the issue, `mctl-app` drifted to
this state when a permissions fix during an incident (2026-08-03/05,
release-please breakage on `mctl-api`) was applied at the installation
level rather than scoped to the repos that needed it. `mctl-agents` has
independently drifted the same way, so the previously-identified "use the
narrower app" fix no longer has a narrow app to point at.

This matters because a leaked or misused private key for either app can
write to or open PRs/issues against every org repo, not just the ones each
app actually automates. This is a hardening/least-privilege pass, not an
active incident — deploy automation and the agent PR pipeline are real,
load-bearing uses that must keep working.

A key constraint (issue item 5): GitHub requires an org owner to approve
any change to an installed app's permissions or repository selection via
GitHub's own sudo-mode-gated UI. No API/CLI in this environment can perform
that change. This proposal can only prepare the audit, the target
repository lists, and any workflow-side changes needed to consume
per-repo-scoped credentials — the actual app-scope edit is a human,
out-of-band step.

## User stories

- AS a platform operator I WANT a concrete, evidence-backed list of which
  repos actually need `mctl-app`'s token and which need `mctl-agents`'s
  token SO THAT I can narrow both installations to `repository_selection:
  "selected"` without breaking deploy automation or the agent PR pipeline.
- AS an org owner reviewing the narrowing change SO THAT I can approve it
  in GitHub's UI with confidence, I WANT the recommended repo list and its
  supporting evidence (which workflow/file references each app) committed
  to gitops, not just asserted in a PR description.
- AS a future contributor adding a new consumer of either app SO THAT the
  org-wide-grant path of least resistance does not recur, I WANT a
  documented, repeatable audit procedure and a policy statement on when a
  new consumer must be added to the narrowed list vs. get its own scoped
  credential.

## Acceptance criteria (EARS)

- WHEN the audit is performed THE SYSTEM SHALL produce a document,
  committed under `mctl-gitops`, enumerating every known consumer of
  `mctl-app` (`platform/github-app`) and `mctl-agents`
  (`platform/github-app-agents`) credentials found in this repo, each
  citing the specific file and line/section that references it.
- WHEN the audit covers consumers outside `mctl-gitops` THE SYSTEM SHALL
  record that cross-repo enumeration (grepping the other 15 org repos for
  `APP_ID`/`APP_PRIVATE_KEY` secrets and `create-github-app-token` usage)
  requires an operator with `gh` access to the full org and could not be
  completed from this repo's read-only single-repo clone, and SHALL
  provide the exact `gh`/grep commands to run to complete it.
- WHEN the target repository lists are proposed THE SYSTEM SHALL express
  them as an explicit, named list per app (not "all") derived from the
  enumerated consumers, with a clearly marked provisional/needs-confirmation
  status for any repo whose need could not be verified from this clone.
- IF a workflow in `mctl-gitops` currently depends on the app's token being
  valid for a repo that is NOT on the derived narrowed list THEN THE SYSTEM
  SHALL flag it explicitly as a blocker to narrowing, rather than silently
  omitting it.
- WHEN documenting the actual GitHub-side change THE SYSTEM SHALL state
  plainly that it requires a human org owner to execute via GitHub's app
  settings UI (sudo-mode confirmation), and SHALL NOT propose or imply an
  automated/API path for changing `repository_selection` or permissions.
- WHILE both apps remain shared, org-wide-scoped credentials for automation
  that only ever needs a handful of repos THE SYSTEM SHALL propose at least
  one concrete alternative pattern already present in this codebase (the
  per-team Vault PAT tier in `.github/workflows/build-image.yaml`, tried
  before the App-token fallback) as a model for moving low-frequency or
  single-repo consumers off the shared org-wide app entirely.
- WHEN the naming drift between the app's real name (`mctl-app`) and its
  rotation-config label (`mctl-agent`, singular, in
  `cwft-rotate-github-token.yaml`) is documented THE SYSTEM SHALL propose a
  concrete reconciliation (rename the label, or document why it is
  intentionally different) so a future reader does not conflate it with
  the separate `mctl-agents` (plural) app.
- IF this proposal's scope grows to include a decision on per-repo
  fine-grained PATs replacing either shared app for some workflows THEN THE
  SYSTEM SHALL record that decision with rationale, but SHALL NOT implement
  a full migration in this proposal — it is a decision + first-mover
  example, not a repo-by-repo migration.

## Out of scope

- Actually changing `repository_selection` or permissions on the
  `mctl-app` / `mctl-agents` GitHub App installations — this requires a
  human org owner clicking through GitHub's sudo-mode UI (issue item 5)
  and cannot be automated from this proposal or by the Tier 2 implementer.
- Revoking either app's access entirely. Both apps back real, load-bearing
  automation (deploy pipeline, agent PR pipeline).
- A full migration of every consumer to per-repo fine-grained PATs. This
  proposal identifies the pattern and where it already exists
  (`build-image.yaml`'s Tier 1 Vault PAT) and recommends it as the target
  shape for new/low-frequency consumers, but does not migrate existing
  high-frequency consumers (e.g. the mctl-agents implementer pipeline)
  in this pass.
- Enumerating consumers in the 15 org repos other than `mctl-gitops` end to
  end — this proposal documents the exact commands to run and the findings
  from what is greppable inside this repo's own workflows/manifests, but a
  human/operator with `gh` access to the full `mctlhq` org must run the
  cross-repo sweep to get a complete list before the actual narrowing.
- Blocking any other work on this landing — this is a hardening pass per
  the issue's own non-goals.

## Open questions

- The issue's audit table lists `mctl-app` permissions as `actions:write,
  contents:write, issues:write, pull_requests:write, members:read,
  statuses:read, metadata:read`. Nothing in this repo's workflows uses
  `actions:write` or `statuses:read` against `mctl-app`'s credential
  directly (gitops-bump's caller-side `actions: write` requirement is
  documented as needed "on mctlhq/mctl-gitops" for `workflow_dispatch`,
  but the calling repos and their token source live outside this clone).
  Whether `actions:write`/`members:read`/`statuses:read` are load-bearing
  for any consumer, or leftover from an earlier configuration, needs the
  cross-repo sweep to answer definitively. Recorded as a finding, not
  blocked on.
- Whether Backstage's GitHub integration (`mctl-portal.yaml`,
  `GITHUB_APP_INSTALLATION_ID` templating) and ArgoCD SSO
  (`argocd-github-oauth.yaml`) — both riding on the same `platform/github-app`
  Vault path as the gitops-commit token — need the app installed on ALL
  repos to function (e.g. Backstage catalog discovery across the org), or
  only on the repos it manages `catalog-info.yaml` for. This changes what
  "narrow" can safely mean for `mctl-app`. Recorded as an open question the
  design flags explicitly rather than assuming either answer.
- Whether the shepherd/implementer pipeline will ever need to open PRs
  against repos not yet onboarded to mctl-agents (i.e., whether the
  narrowed `mctl-agents` list should include some headroom beyond today's
  active proposal repos). Default assumption: narrow to repos with an
  existing `platform-gitops/agents-state/<service>/` directory (today's
  active roster), and treat onboarding a new service to the agents
  pipeline as the trigger to also add it to the app's repo list.
