# Reduce blast radius of the mctl-agents App private key as an org-wide Actions secret

## Context

`AGENTS_APP_ID` / `AGENTS_APP_PRIVATE_KEY` back the internal `mctl-agents`
GitHub App (app_id `4450852`). Per `docs/runbooks/github-app-scope-audit.md`
(written for #761, applied 2026-08-13/14), this App now carries
`contents/issues/pull_requests/workflows:write`, `actions:write`,
`checks:read`, `metadata:read`, and it sits on the `main-protection`
ruleset's `bypass_actors` list (ruleset `18465404`) — the only identity
allowed to push straight to `mctl-gitops` main (see `CLAUDE.md`'s "Branch
Protection Exception" section, and `gitops-bump.yaml` /
`release-deploy.yaml`'s `bump` jobs, which rely on exactly that bypass).

Since 2026-08-13 the two secrets that authenticate as this App are org
Actions secrets with visibility `ALL` — readable by a workflow in any
mctlhq repository, not just the ones that legitimately mint from it. That
is a different failure mode than the one #761 fixed. #761 narrowed *what
the App can do* (its declared permissions) and left a documented
"consumers" list; it did not narrow *which repositories can read the raw
private key*. `actions/create-github-app-token`'s `repositories:` /
`permission-*` inputs are supplied by the caller, not enforced by the App
or by GitHub — so today, any workflow change merged into any one of the 16+
mctlhq repos (compromised maintainer account, a malicious PR that slips
review, a compromised transitive Action) can read the secret and mint a
token scoped however the attacker's own workflow YAML asks, including
`repositories: mctl-gitops` + `permission-contents: write`, which rides the
same ruleset bypass this repo's legitimate bump jobs use to push to main.

This proposal is scoped to what a single `mctl-gitops` change can carry:
grounding the audit in this repo's own workflows, closing the concrete gap
this repo's own `create-github-app-token` call sites leave open (several
mint the App's full permission set instead of the one permission each job
needs), and producing a decision-ready runbook for the org-level actions
(secret visibility, per-purpose Apps, a central-mint reusable workflow)
that require org-owner access or a change in a different repo
(`mctlhq/.github`) this clone cannot make.

## User stories

- AS a platform maintainer I WANT every `create-github-app-token` call in
  `mctl-gitops` to request only the permission its job actually uses SO
  THAT a leaked token from any one call site carries the smallest possible
  blast radius, independent of what the App is granted at the installation
  level.
- AS an org owner I WANT a single, evidence-backed document listing every
  known `AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` consumer, what each needs,
  and the three remediation options from issue #1033 with a recommended
  order SO THAT I can execute the org-level fix (secret visibility, App
  split, or a central-mint workflow) without re-deriving the investigation.
- AS a future contributor adding a new automation SO THAT I have a written
  rule to follow instead of copying whichever existing `create-github-app-token`
  call is closest at hand (some of which are already under-scoped).

## Acceptance criteria (EARS)

- WHEN a `mctl-gitops` workflow step calls `actions/create-github-app-token`
  with `AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` THE SYSTEM SHALL declare an
  explicit `permission-*` input (or inputs) naming only the permission(s)
  that step's job uses, instead of relying on the App's full installed
  permission set.
- WHEN a `mctl-gitops` workflow step calls `actions/create-github-app-token`
  scoped to a single target repo THE SYSTEM SHALL also pass an explicit
  `repositories:` input naming that repo (this already holds for
  `gitops-bump.yaml` and `release-deploy.yaml`; the requirement is to keep
  it true after this change, not to introduce it).
- THE SYSTEM SHALL document, in a runbook committed to this repo, every
  `AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` consumer visible from a
  `mctl-gitops` clone (`gitops-bump.yaml`, `release-deploy.yaml`,
  `release-drift.yml`), each with its required permission and its current
  scoping.
- THE SYSTEM SHALL record, in the same runbook, the four external consumers
  named in issue #1033 (`mctl-telegram#498`, `mctl-api#248`, `mctl-web#97`,
  `mctl-agents` release-please, plus `mctl-telegram`'s
  `preview-deploy.yml`) as unverified from this clone, with the exact
  command a human (or a future agent run with org-wide `gh` access) needs
  to confirm or refute each.
- THE SYSTEM SHALL present the issue's three remediation options (central
  mint reusable workflow, per-purpose Apps, secret visibility `selected`)
  in the runbook with a recommended sequencing, explicitly marking which
  steps require org-owner action or a change in a repository other than
  `mctl-gitops` (`mctlhq/.github`) and are therefore out of this proposal's
  direct edit scope.
- IF a future workflow step needs the App's `actions:write` or
  `pull_requests:write` permission for something other than the bump job's
  `contents:write` THEN THE SYSTEM SHALL require that step to declare its
  own explicit `permission-*` input rather than inherit an unscoped one.
- WHILE `release-drift.yml`'s `create-github-app-token` step already
  declares `permission-contents: read`, `permission-actions: read`, and
  `permission-metadata: read` (needed because it reads across every repo
  under `owner: mctlhq` without a `repositories:` filter) THE SYSTEM SHALL
  leave that call's cross-repo, no-`repositories:` shape unchanged — it is
  a genuine use case a single-repo-scoped reusable workflow cannot serve
  without modification, and the runbook must call that out explicitly so a
  future central-mint design does not silently break it.

## Out of scope

- Actually flipping `AGENTS_APP_ID`/`AGENTS_APP_PRIVATE_KEY` org secret
  visibility from `ALL` to `selected` (issue option 3). This requires
  org-owner access to GitHub org settings; not reachable from this
  read-only `mctl-gitops` clone or its automation credentials. Documented
  as a manual follow-up with the exact target repo list.
- Authoring a central-mint reusable workflow (issue option 1). The org's
  existing reusable-workflow alignment pattern (`claude-review.yml`
  pinning `mctlhq/.github/.github/workflows/claude-review.yml@<sha>`)
  shows where this would live — `mctlhq/.github` — which is a different
  repository than this clone. Documented as a recommended follow-up issue,
  not implemented here.
- Splitting `mctl-agents` into per-purpose Apps (issue option 2). Creating
  a new GitHub App is an org-owner UI action with no API path available to
  this agent, same constraint #761's proposal hit for App permission
  changes.
- Editing workflow files in `mctl-telegram`, `mctl-api`, `mctl-web`, or
  `mctl-agents` — those repos are not present in this clone. The runbook
  records what the issue reports about them and flags it unverified.
- Re-litigating #761's App-permission narrowing (already applied, per
  `docs/runbooks/github-app-scope-audit.md`) or the `mctl-agent`/`mctl-app`
  label rename it made in `cwft-rotate-github-token.yaml`.
- Narrowing the `mctl-agents` App's *installed repository list*
  (`repository_selection`). That is a different lever than Actions secret
  visibility (it limits which repos a minted token can ever target,
  regardless of who mints it) and is worth a follow-up, but issue #1033 is
  scoped to secret readability, not installation scope — recorded as an
  open question below rather than folded in silently.

## Open questions

- Should narrowing the `mctl-agents` App's `repository_selection` (not just
  Actions secret visibility) be pursued in the same follow-up as option 3?
  It closes a related but distinct gap (a token minted with an over-broad
  `repositories:` input by a legitimate caller vs. an illegitimate caller
  reading the raw key at all). Recorded here; not blocking — the runbook
  notes it as a related follow-up without expanding this proposal's task
  list to cover it.
- The issue's recommended repo list for secret visibility `selected` is
  "the repos that actually mint" — this proposal can only confirm the
  three `mctl-gitops` call sites plus transcribe the issue's own claim
  about the other four repos (`mctl-telegram`, `mctl-api`, `mctl-web`,
  `mctl-agents`). Whether that six/seven-repo list is complete is
  unverifiable from this clone; the runbook's "NOT YET VERIFIED" section
  gives the org owner the commands to close that gap before acting.
- Whether option 1 (central mint) or option 3 (visibility `selected`) should
  land first is not stated by the issue beyond "3 is a five-minute change
  ... independent of the others; 1 is the real fix." This proposal
  recommends sequencing (3 immediately, this proposal's permission-scoping
  hardening alongside it, 1 as a tracked follow-up) in the runbook rather
  than leaving it ambiguous — treat that recommendation as the
  interpretation to proceed with.
- Not fully specified by the issue: whether a compromised repo that is
  legitimately on the future `selected` visibility list (e.g. `mctl-web`,
  which mints for its own `release-please.yml`) could still misuse its
  legitimate read access to mint a token scoped to `mctl-gitops` instead of
  itself. Secret visibility narrows *who can read the key*, not *what a
  legitimate reader can ask the key to authorize* — that residual gap is
  exactly what option 1 (central mint) closes and option 3 does not. Noted
  in the runbook so it isn't mistaken for a complete fix.
