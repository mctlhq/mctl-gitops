# Design: issue-1034-ci-create-github-app-token-v3-deprecates

## Current state

Four steps in this repo use `actions/create-github-app-token` to mint a
short-lived installation token, all under `.github/workflows/`:

1. **`release-drift.yml:45`** — `uses: actions/create-github-app-token@v3`
   (floating tag). Step id `app`, authenticates as the mctl-agents App with
   `app-id: ${{ secrets.AGENTS_APP_ID }}` / `private-key: ${{ secrets.AGENTS_APP_PRIVATE_KEY }}`,
   requests `permission-contents: read` / `permission-actions: read`. This
   is the step the issue's first evidence link (mctl-gitops#1032) points at,
   and confirmed live: `v3`'s `action.yml` (fetched from
   `actions/create-github-app-token`) declares
   `app-id: { deprecationMessage: "Use 'client-id' instead." }`, which is
   exactly the warning text in the issue.

2. **`gitops-bump.yaml:66`** and **`release-deploy.yaml:122`** — both
   `uses: actions/create-github-app-token@d72941d797fd3113feb6b93fd0dec494b13a2547 # v1`,
   same SHA in both files. Confirmed via `gh api
   repos/actions/create-github-app-token/git/refs/tags/v1` that this SHA
   *is* the `v1` tag — the `# v1` comment is accurate, this is not a stale
   comment on a newer pin. Both authenticate as the mctl-agents App
   (`AGENTS_APP_ID` / `AGENTS_APP_PRIVATE_KEY`) to push a tag-bump commit
   past the `main-protection` ruleset's required-PR rule, per the
   documented bypass in this repo's `CLAUDE.md` ("Branch Protection
   Exception — Automated Bot Commits") and the inline comments referencing
   issue #761 and #779.

3. **`build-image.yaml:224`** — same v1 SHA pin, step id `app_token`, guarded
   by `if: steps.vault_pat.outputs.has_pat != 'true'` and
   `continue-on-error: true` (one tier in a documented credential fallback
   ladder — see the comment block at `build-image.yaml:70-88`). Authenticates
   as the *other* App (`APP_ID` / `APP_PRIVATE_KEY`, the user-facing "MCTL
   App"), received as reusable-workflow secrets declared under `on:
   workflow_call: secrets:` (`build-image.yaml:81-88`, both `required:
   false`). Its sole caller in this repo, `release-deploy.yaml:58`, passes
   `secrets: APP_ID: ${{ secrets.APP_ID }}` (`release-deploy.yaml:93`) when
   invoking it via `uses: ./.github/workflows/build-image.yaml`.

Fetched `action.yml` for both `v1` (the pinned SHA) and `v3` (the tag
`release-drift.yml` floats on) via `gh api
repos/actions/create-github-app-token/contents/action.yml?ref=...` to
compare inputs directly rather than assume the changelog:

- `v1` inputs: `app-id`, `app_id` (deprecated, use `app-id`), `private-key`,
  `private_key` (deprecated), `owner`, `repositories`,
  `skip-token-revoke`/`skip_token_revoke` (deprecated), `github-api-url`,
  plus permission inputs. **No `client-id` input exists at v1**, and
  `app-id` itself carries no deprecation notice at v1.
- `v3` inputs: `client-id` (new), `app-id` (now deprecated, message "Use
  'client-id' instead."), `private-key` (now `required: true`, was
  optional at v1), `owner`, `repositories`, `enterprise` (new),
  `skip-token-revoke` (default `"false"`), `github-api-url`, permission
  inputs.

This confirms: the three v1-pinned steps in mctl-gitops do not emit the
warning today, and cannot simply have `app-id:` swapped for `client-id:` in
place — v1 has no such input and would fail to identify the App (client-id
is silently unknown to it), breaking the token mint. Only
`release-drift.yml` is both noisy today and safely fixable by an in-place
input swap.

No Terraform `github` provider or other IaC in this repo (`infrastructure/`
only contains the `k3s-preview` and `k3s-prod` clusters — checked, no
`github_actions_*secret*` resources anywhere) manages GitHub Actions
secrets. `APP_ID`/`APP_PRIVATE_KEY`/`AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY`
are opaque to this repo — they exist only as `${{ secrets.X }}` references,
created and rotated out-of-band in GitHub's own UI. The new
`APP_CLIENT_ID`/`AGENTS_APP_CLIENT_ID` secrets follow the same pattern:
this proposal's file changes assume they exist but cannot create them.

`dependabot.yml` runs a weekly `github-actions` ecosystem update
(`.github/dependabot.yml:1-9`, no `ignore` block), so a bump PR moving the
three v1 pins toward v2/v3 is a matter of time regardless of this proposal.

## Proposed solution

Per-file changes, grouped by whether the pin needs to move:

**`release-drift.yml`** (no pin change needed, already on v3):
- Replace `app-id: ${{ secrets.AGENTS_APP_ID }}` with
  `client-id: ${{ secrets.AGENTS_APP_CLIENT_ID }}` at line 47.

**`gitops-bump.yaml`, `release-deploy.yaml`** (bundled pin bump + swap):
- Update `uses: actions/create-github-app-token@d72941d797fd3113feb6b93fd0dec494b13a2547 # v1`
  to the current `v3.x.x` release SHA with an accurate `# vN.N.N` (or `# v3`)
  comment, matching this repo's existing pin-with-comment convention (e.g.
  `actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4`).
- Replace `app-id: ${{ secrets.AGENTS_APP_ID }}` with
  `client-id: ${{ secrets.AGENTS_APP_CLIENT_ID }}`.
- No other input changes needed: `private-key` is already always supplied,
  satisfying v3's new `required: true`.

**`build-image.yaml`** (bundled pin bump + swap + threading through the
reusable-workflow boundary):
- Bump the same SHA pin as above.
- Add `APP_CLIENT_ID: { required: false }` next to the existing `APP_ID:
  { required: false }` entry in `on: workflow_call: secrets:`
  (`build-image.yaml:81-88`), and update the adjacent comment ("These four
  are every inheritable secret build-image references...") to say five.
- Replace `app-id: ${{ secrets.APP_ID }}` with `client-id: ${{
  secrets.APP_CLIENT_ID }}` at the "Generate GitHub App token" step.
- In `release-deploy.yaml`'s call site (`release-deploy.yaml:92-93`), add
  `APP_CLIENT_ID: ${{ secrets.APP_CLIENT_ID }}` alongside the existing
  `APP_ID` passthrough.

This is a pure CI-workflow change: no Helm chart, ArgoCD Application, or
cluster-facing manifest is touched, so the "Everything else... still goes
through a feature branch and a PR" rule in this repo's `CLAUDE.md` applies
in full (the direct-to-main bot exception is scoped narrowly to
`image.tag` bumps in `gitops-bump.yaml`/`release-deploy.yaml`'s *own*
push-to-main step, not to editing the workflow files themselves). The
change goes on a feature branch, through `claude-review.yml` and
`validate-manifests.yml`, same as any other repo change.

## Alternatives

1. **Swap `app-id` to `client-id` in-place on all four files without
   touching the v1 pin.** Rejected: verified against the fetched v1
   `action.yml` that `client-id` does not exist as an input at that
   version; the App identification would silently fall through with
   neither `app-id` nor `client-id` recognized as set, breaking the token
   mint for `gitops-bump.yaml`, `release-deploy.yaml`, and the App-tier
   path in `build-image.yaml`. This is the mistake the issue's own
   `gh search code` sweep risks if applied mechanically across all matches
   without checking each pin's actual resolved version.

2. **Only fix `release-drift.yml` now; leave the v1-pinned three alone
   until Dependabot's own bump PR lands, and fix `app-id` in that same PR.**
   Considered as the minimal, lowest-risk option — it changes exactly the
   one file emitting a warning today. Not chosen as the primary design
   because the issue explicitly frames this as a sweep across all matching
   call sites and a bundled pin-bump is a single reviewable diff either way;
   recorded as a live open question in `requirements.md` since a reviewer
   may reasonably prefer it.

3. **Introduce a single reusable/composite `create-app-token` workflow or
   action in this repo that all four steps call, centralizing the
   App-auth logic (this is effectively what issue #1034 says #1033 might
   do).** Rejected for this proposal: no visibility into #1033's actual
   design from this clone, and it is a larger refactor than the issue's own
   "trivially reviewable one-line change per file" framing calls for. If
   #1033 lands a central mint first, this proposal's per-file diffs would
   likely be superseded/no-ops at three of the four sites — noted as a risk
   below, not a blocker.

## Platform impact

- **Migrations:** none in the data/infra sense. Two new GitHub secrets
  (`APP_CLIENT_ID`, `AGENTS_APP_CLIENT_ID`) must exist before these
  workflow changes are merged, or the affected steps will hard-fail
  (`client-id`/`private-key` combination unresolved) instead of just
  warning. This is a strictly worse failure mode than today's
  warn-but-succeed, so sequencing matters — see Rollback in tasks.md.
- **Backward compatibility:** `app-id` continuing to work in v3 means this
  change is not forced; it can be merged file-by-file and any one file
  reverted independently without affecting the others.
- **Resource impact:** none — no replica, CPU, or memory change; pure CI
  YAML.
- **Risk — wrong pin comment:** if the chosen v3.x.x SHA/comment pair is
  copy-pasted incorrectly (SHA from one version, comment from another),
  future readers get a misleading pin, same class of error this proposal
  found (and fixed the framing around) in the existing `# v1` comment.
  Mitigation: verify with `gh api repos/actions/create-github-app-token/git/refs/tags/vN`
  before writing the pin, same method used during this investigation.
  `dependabot.yml` will also catch a stale pin on its next weekly run.
  `validate-manifests.yml`/`claude-review.yml` should be checked to confirm
  neither already asserts SHA-pin/comment consistency; if not, this is a
  manual reviewer check.
  - **Risk — overlap with #1033:** if #1033 also changes these same lines,
  the two proposals will conflict at merge time. Mitigation: none within
  this proposal's scope (no visibility into #1033); flagged for the human
  reviewer to check #1033's status before merging.
