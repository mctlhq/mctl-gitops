# Migrate create-github-app-token app-id input to client-id in mctl-gitops workflows

## Context

`actions/create-github-app-token@v3` deprecates the `app-id` input in favour
of `client-id`, printing
`##[warning]Input 'app-id' has been deprecated with message: Use 'client-id'
instead.` on every run that sets it. Issue #1034 reports this across 16
workflows in 12 repos org-wide and proposes swapping `app-id: ${{
secrets.APP_ID }}` for `client-id: ${{ secrets.APP_CLIENT_ID }}` (and the
`AGENTS_APP_ID` equivalent), backed by two new org secrets holding each
GitHub App's client ID.

This proposal covers only the `mctlhq/mctl-gitops` repository, which is the
one clone available to this investigation. Verified against the actual
files in this clone:

- `.github/workflows/release-drift.yml:45` uses `actions/create-github-app-token@v3`
  (floating major tag) and does emit the warning today — this is the run
  the issue cites as first evidence (mctl-gitops#1032).
- `.github/workflows/build-image.yaml:224`, `.github/workflows/gitops-bump.yaml:66`,
  and `.github/workflows/release-deploy.yaml:122` are all pinned to commit
  `d72941d797fd3113feb6b93fd0dec494b13a2547`, annotated `# v1`. Comparing
  against upstream tags (`git ls-remote` / GitHub API), that SHA is exactly
  the `v1` tag, and `v1`'s `action.yml` has no deprecation on `app-id` (only
  `app_id`, `private_key`, `skip_token_revoke` underscore aliases are
  deprecated at v1; `client-id` does not exist as an input until v3). These
  three steps do **not** emit the warning today and would break token
  minting if `app-id` were swapped for `client-id` without also bumping the
  pin to v3, since v1 does not understand `client-id`.

So the issue's org-wide `gh search code` sweep over-counts mctl-gitops:
only one of its four call sites is actually noisy right now. The other
three are two majors behind and will need the same fix bundled with a
version bump whenever they move to v2/v3 (which `dependabot.yml`'s weekly
`github-actions` update job will eventually propose).

## User stories

- AS a maintainer watching CI run summaries I WANT the `create-github-app-token`
  deprecation warning gone from `release-drift.yml` SO THAT genuine warnings
  are not buried in noise repeated on every scheduled run.
- AS a maintainer who eventually merges a Dependabot bump of the three
  v1-pinned `create-github-app-token` steps I WANT those steps already using
  `client-id` SO THAT the version bump does not reintroduce the same warning
  the same week it's fixed elsewhere.
- AS the org admin rotating the two GitHub Apps' credentials I WANT the
  client ID pattern (secret name mirrors the existing `*_ID`/`*_PRIVATE_KEY`
  pair) SO THAT the credential set for each App stays discoverable in one
  place, matching the existing `APP_ID`/`APP_PRIVATE_KEY` and
  `AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` convention.

## Acceptance criteria (EARS)

- WHEN `release-drift.yml`'s "Generate read token" step runs THE SYSTEM
  SHALL authenticate as the mctl-agents App using `client-id: ${{
  secrets.AGENTS_APP_CLIENT_ID }}` instead of `app-id: ${{ secrets.AGENTS_APP_ID }}`,
  and SHALL NOT emit the `app-id` deprecation warning.
- WHEN `build-image.yaml`, `gitops-bump.yaml`, or `release-deploy.yaml`'s
  "Generate GitHub App token" step is changed to use `client-id` THE SYSTEM
  SHALL also bump the action's pin from the `v1` SHA to a current `v3.x.x`
  SHA in the same commit, since `client-id` does not exist at `v1`.
- IF a workflow step is changed to reference `client-id: ${{ secrets.APP_CLIENT_ID }}`
  or `client-id: ${{ secrets.AGENTS_APP_CLIENT_ID }}` THEN THE SYSTEM SHALL
  remove the corresponding `app-id:` line from that same step (not add
  `client-id` alongside a still-present `app-id`), since the GitHub Action
  treats them as alternatives and leaving `app-id` set is what triggers the
  warning regardless of `client-id` also being set.
- WHEN `build-image.yaml` is changed to consume `APP_CLIENT_ID` THE SYSTEM
  SHALL add `APP_CLIENT_ID` to its `on: workflow_call: secrets:` block
  (`required: false`, matching `APP_ID`'s existing declaration) SO THAT the
  reusable workflow can receive it from callers.
- WHEN `release-deploy.yaml` calls `build-image.yaml` THE SYSTEM SHALL pass
  `secrets: APP_CLIENT_ID: ${{ secrets.APP_CLIENT_ID }}` alongside the
  existing `APP_ID` passthrough.
- WHILE the new org secrets `APP_CLIENT_ID` and `AGENTS_APP_CLIENT_ID` do
  not yet exist THE SYSTEM SHALL treat their creation as an external,
  manual prerequisite (GitHub org Settings, not a gitops-managed resource —
  this repo has no Terraform `github` provider or other IaC for GitHub
  Actions org secrets) and SHALL NOT merge the workflow changes before both
  secrets exist, to avoid a hard token-minting failure.
- IF the `# vN` comment on a pinned action reference is updated THEN THE
  SYSTEM SHALL keep the comment accurate to the SHA it annotates, matching
  the convention already used for `actions/checkout` pins in this repo
  (e.g. `gitops-bump.yaml:73`).

## Out of scope

- Any workflow file outside `mctlhq/mctl-gitops` (the other 11 repos and 12
  remaining call sites listed in the issue's table) — each needs its own
  proposal against its own repo clone.
- Issue #1033 ("central mint" of App tokens) — referenced by #1034 as a
  possible prerequisite; this repo's clone has no visibility into #1033's
  content or status, so this proposal does not assume or block on it.
- `platform-gitops/argo-workflows/cluster-templates/cwft-rotate-github-token.yaml`,
  which mints a GitHub App JWT itself via a Python script reading
  `creds["app-id"]` from a Vault-sourced dict. This is an unrelated,
  hand-rolled mechanism (not the `actions/create-github-app-token` Action)
  and has no `app-id`/`client-id` deprecation surface.
- Creating the `APP_CLIENT_ID` / `AGENTS_APP_CLIENT_ID` org secrets
  themselves (a GitHub org-settings action, not a gitops repo change).
- Any change to `private-key` handling; v3 makes `private-key` a required
  input (it was optional-with-fallback at v1), but all four call sites
  already always supply it, so this is a no-op in practice.

## Open questions

- Should the three v1-pinned steps be bumped to `client-id` + v3 now
  (pre-emptive, matches the issue's "sweep everything" framing) or left at
  v1 until Dependabot naturally proposes the version bump (lower risk,
  smaller diff, defers the change until it's actually needed)? This
  proposal takes the pre-emptive route since the issue explicitly lists all
  four files and a bundled pin-bump-plus-input-swap is one coherent,
  reviewable change per file — but a reviewer may prefer the deferred
  option to keep this PR's blast radius to the one file that's actually
  noisy today.
- Exact target v3 patch version to pin to (`v3.2.0` was current at
  investigation time; use whatever `dependabot.yml`'s next proposal or
  `gh api repos/actions/create-github-app-token/tags` shows as latest v3.x.x
  when the task is executed).
- Whether `AGENTS_APP_CLIENT_ID` / `APP_CLIENT_ID` should be repo-level
  secrets (matching where `AGENTS_APP_ID`/`APP_ID` currently live, per the
  `secrets.AGENTS_APP_ID` / `secrets.APP_ID` references, which resolve at
  the repo unless already promoted to org level) or genuinely new org-wide
  secrets as the issue suggests. The issue calls them "org secrets" but
  this repo's existing `APP_ID`/`AGENTS_APP_ID` are referenced the same way
  whether repo- or org-scoped; whoever creates the new secrets should match
  the existing `APP_ID`/`AGENTS_APP_ID` scope for consistency. Proceeding
  with the assumption that they should live at the same scope as the
  existing `*_ID`/`*_PRIVATE_KEY` pairs.
