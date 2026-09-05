# mctl-agents App secret exposure

Which workflows can read the raw `AGENTS_APP_ID` / `AGENTS_APP_PRIVATE_KEY`
signing key, why permission-level narrowing does not close that gap, and
what closes it.

Written for mctlhq/mctl-gitops#1033. Sibling to
`docs/runbooks/github-app-scope-audit.md` (#761) — that audit narrowed
*what the mctl-agents App can do* (its declared permissions); this one is
about a different lever: *who can read the raw key that mints tokens as
that App at all*.

## The finding

App-permission narrowing (#761, `docs/runbooks/github-app-scope-audit.md`,
applied 2026-08-13/14) and per-call-site permission scoping (this
proposal's tasks 1-2, below) both operate on the *permissions dimension* of
a minted token. Neither one touches the *secret-visibility* dimension.

`AGENTS_APP_ID` / `AGENTS_APP_PRIVATE_KEY` are org-level GitHub Actions
secrets with visibility `ALL`, set 2026-08-13 — the same week #761 landed.
At that visibility, a workflow in **any** mctlhq repository can read both
secrets and call `actions/create-github-app-token` itself, supplying
whatever `repositories:` / `permission-*` inputs it wants, bounded only by
the App's installed permission ceiling — not by anything this repo's own
workflows declare. A compromised maintainer account, a malicious PR that
slips review in an unrelated repo, or a compromised transitive Action in
any of the 16+ mctlhq repos can mint a token scoped to
`repositories: mctl-gitops` + `permission-contents: write`, which rides
the same `main-protection` ruleset bypass this repo's own
`gitops-bump.yaml` / `release-deploy.yaml` bump jobs rely on to push
straight to `main`.

Narrowing this repo's own `create-github-app-token` calls (tasks 1-2)
reduces the damage *those specific call sites* can do if their own output
leaks — it does nothing about a workflow in some other repo minting its
own, independently-scoped token from the same raw key. Only narrowing
Actions secret visibility from `ALL` to `selected` (issue option 3), or
removing the raw key from callers entirely via a central-mint reusable
workflow (issue option 1), closes that door.

This is the same "declared once, applies to every installation"
limitation that forced the MCTL-App / mctl-agents split documented in
`github-app-scope-audit.md`'s "Why the split is forced, not stylistic"
section, extended one step further: the App's permission ceiling is
irrelevant to who can *read the signing key* in the first place — that is
purely an Actions-secret-visibility question, orthogonal to anything on
the App's settings page.

## In-repo consumers (verified from this clone)

Grep for `AGENTS_APP_ID` / `AGENTS_APP_PRIVATE_KEY` across
`.github/workflows/` in this clone finds exactly three call sites.

| Consumer | Mints for | `repositories:` | `permission-*` scoping (after this proposal) |
|---|---|---|---|
| `.github/workflows/gitops-bump.yaml:64-72` (`Generate GitHub App token` step, `bump` job) | Pushes a tag-bump commit directly to `main`, bypassing the `main-protection` ruleset (the App is on its `bypass_actors` list) | `mctl-gitops` | `permission-contents: write` (added by this proposal's task 1; previously unset, so the minted token carried the App's full installed set: `actions:write`, `pull_requests:write`, `issues:write`, `workflows:write`, `checks:read`) |
| `.github/workflows/release-deploy.yaml:120-128` (`Generate GitHub App token` step, `bump` job) | Same as above — pushes an image-tag bump to `main` after a build succeeds | `mctl-gitops` | `permission-contents: write` (added by this proposal's task 2; same prior state as `gitops-bump.yaml`) |
| `.github/workflows/release-drift.yml:43-52` (`Generate read token` step, `check` job) | Reads release/tag/compare state across every mctlhq source repository via `.github/scripts/release-drift.sh` | none (deliberately unset — needs org-wide read) | `permission-contents: read`, `permission-actions: read`, `permission-metadata: read` — already correctly scoped before this proposal; left untouched |

`release-drift.yml`'s no-`repositories:`, multi-permission, cross-repo-read
shape is the one call site in this repo that a future single-repo-scoped
central-mint design (option 1, below) cannot serve without modification —
flagged here so that design doesn't silently drop it.

## Externally-reported consumers (unverified from this clone)

Issue #1033 names four additional consumers in repositories not present in
this clone. These are transcribed from the issue, not independently
confirmed.

| Repo | Workflow | Claimed use |
|---|---|---|
| `mctl-telegram` | `release-please.yml` | Dispatches `actions:write` on `mctl-gitops` |
| `mctl-telegram` | `preview-deploy.yml` | Dispatches `actions:write` on `mctl-gitops` |
| `mctl-api` | `release-please.yml` | Dispatches `actions:write` on `mctl-gitops` |
| `mctl-web` | `release-please.yml` | Dispatches `actions:write` on `mctl-gitops` |
| `mctl-agents` | `release-please.yml` | Dispatches `actions:write` on `mctl-gitops` |

**Unverified from this clone.** A human, or a future agent run with
org-wide `gh` access, must confirm or refute this list before it is used
to seed the `selected` visibility allowlist:

```bash
gh api orgs/mctlhq/actions/secrets/AGENTS_APP_PRIVATE_KEY \
  --jq '{visibility, selected_repositories_url}'
for repo in $(gh repo list mctlhq --limit 100 --json name -q '.[].name'); do
  gh api "repos/mctlhq/$repo/contents/.github/workflows" --jq '.[].name' 2>/dev/null \
    | xargs -I{} gh api "repos/mctlhq/$repo/contents/.github/workflows/{}" --jq '.content' 2>/dev/null \
    | base64 -d 2>/dev/null | grep -qE 'secrets\.AGENTS_APP_(ID|PRIVATE_KEY)' \
    && echo "$repo: mints from AGENTS_APP_*"
done
```

## Remediation options and recommended sequencing

1. **Now, no org-owner action needed** — this proposal's tasks 1-2:
   permission-scope the two under-scoped in-repo call sites
   (`gitops-bump.yaml`, `release-deploy.yaml`) to `permission-contents:
   write` only. **DONE by this commit.** Reduces the blast radius of a
   leak from these two call sites specifically; does not touch secret
   readability.
2. **Next, five-minute org-owner action (issue option 3)**: flip
   `AGENTS_APP_ID` / `AGENTS_APP_PRIVATE_KEY` Actions secret visibility
   from `ALL` to `selected`, seeded with the verified consumer list from
   this runbook (in-repo table above, plus the externally-reported table
   once confirmed). Cheapest lever; closes the "any repo can read the key"
   gap directly; independent of the other two options per the issue body.
3. **Follow-up, cross-repo effort (issue option 1)**: a reusable workflow
   in `mctlhq/.github` — the same alignment pattern this repo already uses
   for `claude-review.yml`'s
   `uses: mctlhq/.github/.github/workflows/claude-review.yml@<sha>` — that
   holds the key once and mints per-caller-scoped tokens, removing the raw
   key from every caller including the two hardened by this proposal.
   Recommend filing as a new tracked issue against `mctlhq/.github`.
   `release-drift.yml`'s no-`repositories:`, multi-permission,
   cross-repo-read shape (see table above) is a requirement that design
   must support — a single-repo-scoped design would silently break it.
4. **Deferred, not urgent (issue option 2)**: per-purpose Apps. Requires
   the most new setup (creating a new App is an org-owner UI action, no
   API path — the same constraint #761's App-permission changes hit), and
   the security benefit it would offer is largely subsumed once option 1
   exists.

## Manual follow-up

- Run this runbook's verification commands (above) and update the
  "unverified" table with real findings.
- Flip `AGENTS_APP_ID` / `AGENTS_APP_PRIVATE_KEY` org secret visibility
  from `ALL` to `selected`, seeded with the confirmed consumer repo list
  (issue option 3).
- Smoke-test `gitops-bump.yaml`, `release-deploy.yaml`, and
  `release-drift.yml` after narrowing — confirm the `Generate GitHub App
  token` / `Generate read token` steps still succeed and the subsequent
  git operations complete.
- File a tracking issue in `mctlhq/.github` for the central-mint reusable
  workflow (issue option 1), explicitly noting `release-drift.yml`'s
  no-`repositories:`, multi-permission, cross-repo-read shape as a
  requirement the design must support.
