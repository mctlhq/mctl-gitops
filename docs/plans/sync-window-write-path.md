# Sync-window write path: what is built, and the mctl-api step (#2828 S1)

**Status: proposed. Nothing in the mctl-api step is built. Owner GO is
requested on the decisions in section 5; merging this file is not that GO.**

This is the "new proposal" that section 1 of the #2828 design
(`platform-gitops/agents-state/mctl-gitops/proposals/issue-2828-spike-release-governed-release-calendar/design.md`)
asks for before S1. That design is research-only and authorises nothing, and
it says any AppProject, window, MCP tool or production change needs a separate
owner security GO. Steps 1 and 2 below were built on the owner's direction in
a working session, without a written GO. Section 5 asks for it to be recorded.
None of them applies a window: every step opens or checks a pull request that
a person reviews and merges.

## 1. What exists

| Piece | Where | Effect |
|---|---|---|
| Read tool for live windows | mctl-api 4.172.0, gitops #2857 and #2864 | admin-only list of what Argo CD holds; writes nothing |
| Window validator | `scripts/validate-argocd-sync-windows.py`, gitops #2880, run in `validate` | refuses default project, `allow`, `manualSync`, globs, bad schedule |
| Render-only proposal tool | `scripts/render-sync-window.py`, gitops #2881 | patch and matched set against the rendered inventory; refuses recovery-chain, unknown and foreign applications |
| Protected paths | gitops #2889: CODEOWNERS and `protected_re` for the project templates, both scripts and `app-project-consumers.json` | a window PR is never machine-merged |
| PR-opener | `.github/workflows/release-window-pr.yml` and `scripts/release-window-insert.py`, gitops #2890 | dispatch on main, App `mctl-gitops-pr`, opens `release-window/<id>`; does not enqueue or merge |

A trial run of the PR-opener on a preview application (run 45031165987, PR
#2893, closed unmerged) produced one commit authored by `mctl-gitops-pr[bot]`
with a resolvable identity, one changed file, and a PR that passed all 26
checks and the Claude review, including the validator reporting
`sync windows found: 1; violations: 0`. No window was ever on `main`.

Where a window lives: patched straight into `spec.syncWindows` of the `apps`
or `platform` AppProject template (never `default`). There is no separate
policy file. The #2828 design assumes one; this plan deliberately does not
build it yet, because the render tool and the validator already bound the
change and a second file would be a second thing to keep in step.

### How the PR-opener binds to an approval

Inputs are `window_id`, `project`, `applications`, `schedule`, `duration`,
`base_sha` and `window_sha256`. The job refuses unless the window rebuilt from
the inputs hashes to `window_sha256`, `base_sha` is an ancestor of main and the
target template is unchanged since, and the window passes the render tool and
the validator. The hash is over `{"project": P, "window": W}`, canonical JSON
(sorted keys, compact separators). It is the contract the caller must match.

Test vector for any other implementation: project `apps`, window
`{"kind":"deny","schedule":"0 3 1 1 *","duration":"1h","applications":["labs-agent-worker-preview"]}`
hashes to `fb49bf984cc92acaf28e86e9a92630b798f7f9981dcfb84db2a8ba03556ad4e5`.

## 2. The remaining step: an mctl-api tool that asks for the PR

`mctl_propose_release_window` (design section 8.1): admin-only REST route and
MCP tool, next to the existing read tool. It validates the request, computes
the hash, reads main's head as `base_sha`, and dispatches
`release-window-pr.yml`. It returns the run, then the PR once it exists. It
does not approve, merge, sync, or touch Argo CD. The server never renders
the window itself: the workflow does, on main, against the live inventory, so
there is one source of truth for what a window matches.

Scope, as agreed so far:

- `kind` is always `deny`; no `allow`, no namespaces or clusters selectors,
  no `manualSync`. Applications are exact names.
- Project is `apps` or `platform`; the tool refuses `default`.
- Duration and schedule use the shapes the workflow already checks.
- Idempotent per `(caller, window_id)`. The workflow refuses an existing
  branch or an open PR for the same id; the tool reports that as "already
  requested" with the PR number, never retries by overwriting.
- Audit: request id, caller, window id, hash, run id, PR number.

Not in this step: removing or shortening a window, the exception path
(`release.freeze_exception`, broker), a calendar policy file, activation
checks. Each needs its own proposal.

Verification before release: a cross-language test that reproduces the test
vector above; refusal cases mirrored from the workflow (default project, unknown
application, malformed duration); the two live checks already owed on the read
tool (non-admin gets 403, no token gets 401); one live dispatch on a preview
application, closed unmerged, as the trial above was. The mctl-api release goes
through the release ledger and hold like any other, with the allow record
written at GO time.

## 3. Facts about mctl-api not re-verified here

From a read-only scouting pass on 2026-11-22 against the default branches; to
be re-checked when the work starts: the read tool lives in
`internal/api/handlers_syncwindows_read.go` and `internal/argocd/syncwindows.go`;
`internal/ghactions/dispatch.go` already dispatches workflows (the portal apply
tool uses it); `release_approvals.go` defines the dedicated kind
`release.grant`, and `release.*`, `deploy.*` and `glovo.*` are refused by every
generic route.

## 4. Risks

1. **The dispatch credential is wider than the App.** mctl-api's existing
   dispatch token is the broad agents installation. Whoever compromises
   mctl-api could dispatch any workflow it can reach, not only this one. The
   workflow's own guards (main-only environment, input shape, hash and base
   binding, validator) limit what a dispatch can produce, not who can send it.
2. **A window that reaches the recovery chain cannot be reverted through
   GitOps**, because the ruleset bypass is gone. The validator and render tool
   run on the PR and in the merge queue; they are the guard, and a person's
   review is the second.
3. **Queue churn.** Bot pushes to main move the base constantly. A stale
   `base_sha` is refused by design and the request has to be made again; plan
   for that instead of force-pushing over a PR.

## 5. Decisions for the owner

1. **Record a GO for steps 1 and 2 as built** (section 1). They were built on
   direction in session; the #2828 text asks for a written security GO.
2. **Dispatch credential.** (a) the existing broad token now, the way the
   portal apply tool does, with the narrow `mctl-gitops-dispatch` App as a
   follow-up; (b) move to the narrow App first, which needs its key held where
   mctl-api can read it and a rotation path. Recommendation: (a), because it
   adds no new secret, and the workflow's guards bound what a dispatch can do.
3. **MFA on the request.** The design's section 8.2 sends a window through
   normal review with no self-approval and the merge queue, with no
   `release.*` kind for it. Options: (a) admin RBAC plus that review, no new
   kind (recommended: the real approval is the merge, which is a person and a
   protected path); (b) a new dedicated kind and MFA decide page on the
   request, which needs its own proposal and an mctl-api owner GO and adds
   spam control only.
4. **GO to implement the tool** on the scope in section 2.
