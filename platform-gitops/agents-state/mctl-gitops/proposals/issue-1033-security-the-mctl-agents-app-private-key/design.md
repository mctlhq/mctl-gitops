# Design: issue-1033-security-the-mctl-agents-app-private-key

## Current state

### What #761 already fixed, and what it left open

`docs/runbooks/github-app-scope-audit.md` (committed, "Complete" as of
2026-08-13/14) narrowed the `mctl-agents` App's *declared permissions* down
to what its consumer list uses:
`actions:write, checks:read, contents:write, issues:write, metadata:read,
pull_requests:write, workflows:write`. It also confirms `mctl-agents` sits
on the `main-protection` ruleset's `bypass_actors` list
(ruleset `18465404`) — the only identity that can push straight to
`mctl-gitops` main, which is what lets `gitops-bump.yaml` and
`release-deploy.yaml`'s `bump` jobs commit directly (see `CLAUDE.md`'s
"Branch Protection Exception — Automated Bot Commits" section).

That audit did not touch two separate levers, both of which #1033 is
actually about:
1. **Actions secret visibility** — `AGENTS_APP_ID` / `AGENTS_APP_PRIVATE_KEY`
   are org secrets with visibility `ALL` (per #1033, set 2026-08-13, i.e.
   the same week #761 landed). Any repo's workflow can read the raw key,
   regardless of whether that repo is a legitimate consumer.
2. **Per-call-site permission scoping within this repo** — `#761`'s audit
   table documents the App's *installed* permission ceiling, but does not
   verify every `create-github-app-token` call actually narrows down to a
   subset of it. Grep confirms it does not, consistently.

### `create-github-app-token` call sites in this clone

Grep for `AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` across `.github/workflows/`
finds exactly three:

1. `.github/workflows/gitops-bump.yaml` lines 64-71 — mints with
   `owner: mctlhq`, `repositories: mctl-gitops`, **no `permission-*`
   input**. The job (`bump`, line 43-46) declares
   `permissions: contents: write` for its own `GITHUB_TOKEN`, and the step's
   own comment (lines 48-60) states the App is used *only* to push a
   tag-bump commit past branch protection — i.e. the minted token only ever
   needs `contents:write`, but because no `permission-contents` input is
   set, the action mints a token carrying the App's **full** installed
   permission set (`actions:write`, `pull_requests:write`,
   `issues:write`, `workflows:write`, `checks:read` included) scoped to
   just the one repo. `repositories:` is correctly narrowed; the permission
   dimension is not.
2. `.github/workflows/release-deploy.yaml` lines 120-127 — same pattern:
   `repositories: mctl-gitops`, no `permission-*` input, same
   `contents:write`-only actual use in its `bump` job (line 98-102:
   `permissions: contents: write`).
3. `.github/workflows/release-drift.yml` lines 39-49 — the one call site
   that already does this correctly:
   `permission-contents: read`, `permission-actions: read`,
   `permission-metadata: read`, and deliberately **no** `repositories:`
   input, because the job (comment lines 32-34) reads release/tag/compare
   state "across every mctlhq source repository" via
   `.github/scripts/release-drift.sh` under `owner: mctlhq`. This is the
   one caller with a genuine need for a multi-repo, read-only token — it
   cannot be rewritten to a single-repo scope without dropping its actual
   purpose.

`.github/workflows/build-image.yaml` lines 221-231 uses the *other* App
(`APP_ID`/`APP_PRIVATE_KEY`, MCTL App, per the audit doc's "the only
legitimate uses" table) with `permission-contents: read` already
declared — proof the codebase already has the pattern this proposal asks
`gitops-bump.yaml`/`release-deploy.yaml` to adopt; it just is not applied
to the `AGENTS_APP_*` call sites yet.

### The actual gap #1033 raises that #761 does not close

Per `actions/create-github-app-token`'s own contract (cited in the issue
body and consistent with what `release-drift.yml` already relies on): the
token's `repositories:`/`permission-*` scope is whatever the **caller's
workflow YAML** asks for, bounded only by the App's installed ceiling. The
App's installed permission set is the same for every installation
(`docs/runbooks/github-app-scope-audit.md`'s "Why the split is forced, not
stylistic" section makes this point about MCTL App vs. mctl-agents, and it
applies identically within mctl-agents's single ceiling). Nothing in
`create-github-app-token`, Vault, or GitHub Actions prevents a workflow in
an unrelated repo from writing its own step:

```yaml
- uses: actions/create-github-app-token@...
  with:
    app-id: ${{ secrets.AGENTS_APP_ID }}
    private-key: ${{ secrets.AGENTS_APP_PRIVATE_KEY }}
    owner: mctlhq
    repositories: mctl-gitops
    permission-contents: write
```

as long as that repo's Actions workflow can read `AGENTS_APP_ID` /
`AGENTS_APP_PRIVATE_KEY` — which, at visibility `ALL`, every mctlhq repo
can. That token would ride the exact `main-protection` ruleset bypass
`gitops-bump.yaml` relies on. Narrowing `mctl-gitops`'s own call sites
(permission-scoping, this proposal) reduces the damage *those* call sites
can do if their output leaks; it does nothing about a workflow in some
other repo minting its own, independently-scoped token from the same raw
key. Only secret-visibility narrowing (issue option 3) or eliminating the
raw key from callers entirely (issue option 1) close that door — both are
outside what a `mctl-gitops`-only code change can execute, per the
"Proposed solution" below.

## Proposed solution

Following the precedent `docs/runbooks/github-app-scope-audit.md` set for
#761 — where the actual App-permission-narrowing action was manual
(org-owner UI, no API path) and the proposal's committed deliverable was
an audit document plus every in-repo change that *was* mechanically
reachable — this proposal splits the same way:

1. **Harden the two under-scoped call sites in this repo.**
   In `.github/workflows/gitops-bump.yaml` and
   `.github/workflows/release-deploy.yaml`, add `permission-contents: write`
   to the existing `create-github-app-token` step (alongside the
   already-correct `repositories: mctl-gitops`). This is a two-line,
   same-file, no-schema-change edit per file: the step already exists, only
   an input is added. It makes the minted token in each call carry
   `contents:write` and nothing else — no `actions:write`,
   `pull_requests:write`, `issues:write`, or `workflows:write` — regardless
   of what the App's installation-wide ceiling allows, matching what
   `build-image.yaml`'s MCTL App call and `release-drift.yml`'s own
   `AGENTS_APP_*` call already do. This is a real, if partial, mitigation
   for #1033's stated risk: a leaked/misused token minted *from these two
   call sites* now cannot dispatch workflows or open PRs even though the
   App itself still can.
   `release-drift.yml` is left untouched — it is already correctly scoped,
   and it is the concrete evidence that a future central-mint reusable
   workflow (option 1) must support "no `repositories:`, read scoped to
   several explicit permissions, across the whole org" as a first-class
   case, not just the single-repo write case the other two calls use.

2. **Write `docs/runbooks/agents-app-secret-exposure.md`** — a sibling to
   `github-app-scope-audit.md`, cross-linked from it and from `CLAUDE.md`,
   scoped specifically to the secret-readability gap #761 did not cover:
   - Restate the finding above: permission narrowing at the App level and
     even per-call-site scoping (this proposal's task 1) do not restrict
     *who can read the raw private key*; only Actions secret visibility or
     removing the key from callers does.
   - The three in-repo consumers (table: file, line, what it mints,
     `repositories:`/`permission-*` state before and after this proposal).
   - The externally-reported consumers from issue #1033
     (`mctl-telegram` `release-please.yml`/`preview-deploy.yml`,
     `mctl-api` `release-please.yml`, `mctl-web` `release-please.yml`,
     `mctl-agents` `release-please.yml`), explicitly marked "unverified from
     this clone" with the same style of ready-to-run verification commands
     `github-app-scope-audit.md` used for its own "NOT YET VERIFIED"
     section, adapted to secrets instead of permissions, e.g.:
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
   - Present the issue's three options with a recommended sequence:
     1. **Now, no org-owner action needed:** this proposal's task 1
        (permission-scoping the two under-scoped call sites).
     2. **Next, five-minute org-owner action (issue option 3):** flip
        `AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` visibility from `ALL` to
        `selected`, seeded with the verified consumer list from this
        runbook. Cheapest lever, closes the "any repo can read the key"
        gap directly, and is explicitly independent of the other two per
        the issue body.
     3. **Follow-up, cross-repo effort (issue option 1):** a reusable
        workflow in `mctlhq/.github` (same alignment shape this repo
        already uses for `claude-review.yml`'s
        `uses: mctlhq/.github/.github/workflows/claude-review.yml@<sha>`)
        that holds the key once, mints with the caller-supplied
        `repositories:`/permission set, and returns a token as an output —
        removing the raw key from every caller's own secrets, including
        the two hardened in this proposal. Recommended as a new tracked
        issue filed against `mctlhq/.github` (not implementable from a
        `mctl-gitops` clone), with `release-drift.yml`'s no-`repositories:`
        cross-repo-read shape flagged as a case that design must handle.
     4. **Deferred, not recommended as urgent (issue option 2):** per-purpose
        Apps. Runbook records it as the option requiring the most new setup
        (new App creation is an org-owner UI action, same constraint #761's
        App-permission changes hit) for a security benefit largely
        subsumed by option 1 once it exists.
   - A short cross-reference to `github-app-scope-audit.md`'s "Why the
     split is forced, not stylistic" reasoning, extended one step: the same
     "declared once, applies to every installation" limitation that forced
     the MCTL-App/mctl-agents split also means the App's permission ceiling
     is irrelevant to who can *read the signing key* — that is purely an
     Actions-secret-visibility question, orthogonal to anything on the
     App's settings page.

3. **Cross-link the new runbook** from `CLAUDE.md` (one line, alongside
   wherever `github-app-scope-audit.md` is referenced, or a new bullet if
   it is not yet referenced there) and from
   `docs/runbooks/github-app-scope-audit.md` itself (one line under
   "Consumers" or a new short section), so a future reader of either
   document finds the other without re-deriving which gap each one closes.

## Alternatives

1. **Flip the org secret visibility directly from this proposal.**
   Rejected: no `gh`/GitHub API credential with org-secret-write access is
   available to this agent, and org secret visibility changes are an
   org-owner action in GitHub's UI/API — the same class of constraint
   `github-app-scope-audit.md` hit for App permission changes in #761.
   Recorded as the immediate manual follow-up instead.
2. **Design and commit the central-mint reusable workflow now, inside this
   repo.** Rejected: the org's own established alignment pattern
   (`claude-review.yml`'s `uses: mctlhq/.github/.github/workflows/...`)
   places shared reusable workflows in `mctlhq/.github`, a repository not
   present in this clone. Committing a reusable-workflow file under
   `mctl-gitops/.github/workflows/` that other repos would `uses:` against
   would work mechanically but breaks the established convention and this
   agent cannot verify `mctlhq/.github`'s current contents or naming to
   avoid a collision. Recommended as a follow-up issue in the correct repo
   instead.
3. **Skip the audit-document deliverable; just ship the two-file
   permission-scoping change with a PR description.** Rejected for the same
   reason `github-app-scope-audit.md`'s design rejected the equivalent
   option for #761: the org-level decision (visibility `selected` seeded
   with which repos, and whether/when to pursue the central-mint follow-up)
   needs a durable, evidence-backed reference an org owner can act on
   without re-reading a stale PR description months later.
4. **Also narrow `mctl-agents`'s `repository_selection`
   (installation scope) in this same proposal.** Rejected for this pass:
   it is a materially different lever (which repos a token can ever target
   vs. who can read the key that mints it) and is not what issue #1033
   asks for. Recorded as an open question / related follow-up rather than
   silently expanding this proposal's scope.

## Platform impact

- **Migrations / backward compatibility:** none. Adding
  `permission-contents: write` to an existing `create-github-app-token`
  step is additive and narrows rather than widens what the resulting token
  can do; both call sites already only use the token for
  `git push`/checkout against `mctl-gitops`, which `contents:write` alone
  covers (confirmed by each job's own `permissions:` block already
  declaring `contents: write` for its native `GITHUB_TOKEN`, right next to
  the App-token step).
- **Resource impact:** none — workflow YAML edits and two markdown files.
- **Risks:**
  - If `permission-contents: write` is misspelled or the App's actual
    installed permission naming differs from `create-github-app-token`'s
    expected input key, the step fails at token-mint time (loud,
    `create-github-app-token` errors before checkout runs) rather than
    silently degrading — this is the same fail-closed shape
    `github-app-scope-audit.md` flagged for the analogous MCTL-App
    narrowing. Mitigation: verify the exact input name against
    `actions/create-github-app-token`'s documented `permission-contents`
    key (already used correctly in `release-drift.yml` and
    `build-image.yaml` in this same repo) before merging, and watch the
    next `gitops-bump`/`release-deploy` run's `Generate GitHub App token`
    step log.
  - The runbook's externally-reported consumer list (`mctl-telegram`,
    `mctl-api`, `mctl-web`, `mctl-agents`) is transcribed from the issue,
    not independently verified — if the org owner acts on the "recommended
    `selected` repo list" before running this runbook's verification
    commands, a real consumer missing from the list breaks on the next run
    after visibility narrows. Mitigation: the runbook's verification
    commands are written to run before, not instead of, the visibility
    change, mirroring `github-app-scope-audit.md`'s "NOT YET VERIFIED"
    pattern.
  - None of this proposal's changes affect the `cwft-rotate-github-token.yaml`
    Vault-based token rotation path (Argo Workflows, Kubernetes-side) — that
    is a separate credential-delivery mechanism from GitHub Actions org
    secrets and is unaffected by anything here. Explicitly out of scope,
    not silently assumed unaffected.
