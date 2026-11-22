# Sync-window write path: what is built, and the mctl-api step (#2828 S1)

**Status (updated 2026-11-22, evening): steps 1 and 2 are built and merged.
The mctl-api step is built in three slices: S1, S2 and S3 are merged
(mctl-api#1153, #1154, #1155), released as mctl-api 4.173.0, and switched on
with `RELEASE_WINDOWS_ENABLED=true` (gitops#2909). The first real run was
made and watched the same evening (section 2). No window is on `main`.
Section 5 records which decisions are now made and which are still open. This
file authorises nothing; merging it is not a GO.**

This is the "new proposal" that section 1 of the #2828 design
(`platform-gitops/agents-state/mctl-gitops/proposals/issue-2828-spike-release-governed-release-calendar/design.md`)
asks for before S1. That design is research-only and authorises nothing, and
it says any AppProject, window, MCP tool or production change needs a separate
owner security GO. Steps 1 and 2 below were built on the owner's direction in
a working session, without a written GO. That GO is still not written down;
section 5, item 1, stays open.
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

## 2. The mctl-api step: slices and status

`mctl_propose_release_window` (design section 8.1) is built in three slices,
all dark by default (`RELEASE_WINDOWS_ENABLED`). The slice names S1 to S3 are
mctl-api's own, not the S0 and S1 stages of the #2828 design:

- **S1, merged 2026-11-22 (mctl-api#1153).** The dedicated kind
  `release.window` (policy `release.window.owner`; the `release.*` namespace
  means every generic route refuses it) and an admin-only
  `POST`/`GET /api/v1/release/windows` to request and read an approval. The
  window rides in the approval's `target` as `<project>/<window_id>#<window
  JSON>`. The server reads main's head itself and treats a failed read as
  unavailable, never as a guess. It computes the same `window_sha256` as the
  workflow, checked against shared golden vectors.
- **S2, merged 2026-11-22 (mctl-api#1154).** The MFA decide page for
  `release.window` at `/release/window-approvals/{aar_id}`, a clone of the
  release-grant page: fresh sign-in, MFA, only the owner decides. It decides
  and does nothing else. The fork was settled as a new callback path with a
  second redirect URI on the same ZITADEL client (`mctl-api-release-approval`,
  gitops#2905); the live grant page is unchanged.
- **S3, merged 2026-11-22 (mctl-api#1155).** The MCP tool
  `mctl_propose_release_window` and the REST route
  `POST /api/v1/release/windows/{approval_id}/execute`, in two calls.
  The first returns the pending approval and its decide URL. The second, with
  the same arguments once the approval is granted, consumes it and dispatches
  `release-window-pr.yml`. A dispatch returns no run id, so the tool answers
  with the workflow's runs link and the branch `release-window/<window_id>`,
  not a guessed run.

The tool validates the request, computes the hash, reads main's head as
`base_sha`, and dispatches. It does not approve, merge, sync, or touch Argo CD.
The server never renders the window itself: the workflow does, on main,
against the live inventory, so there is one source of truth for what a window
matches.

Scope, as agreed so far:

- `kind` is always `deny`; no `allow`, no namespaces or clusters selectors,
  no `manualSync`. Applications are exact names.
- Project is `apps` or `platform`; the tool refuses `default`.
- Duration and schedule use the shapes the workflow already checks.
- Idempotent per `(caller, window_id)`. The workflow refuses an existing
  branch or an open PR for the same id; the tool reports that as "already
  requested" with the PR number, never retries by overwriting.
- Audit: request id, caller, window id, hash, the workflow runs link, PR
  number once it exists.

First real run, 2026-11-22: request `aar_a495ad1bbdbb4c7cb3c1415f2c0482df`
(window `w-cb40a0fccceb`: project `apps`, `admins-umami`, deny, `0 3 * * 1`,
1h) decided by the owner with MFA at 18:36Z, executed at 18:37Z
(`approved -> in_flight -> executed`). Workflow run 45056122362 opened PR
#2915 from `release-window/w-cb40a0fccceb` as `mctl-gitops-pr[bot]`, one file,
a diff identical to the approved window. The PR was closed unmerged and its
branch deleted before its CI finished, so the validator result for that PR was
not observed (the trial PR #2893 did pass it). Observed: the REST read
`GET /api/v1/release/windows` lists windows from git, not approval state; the
approval state is read by repeating the same `POST`, which is idempotent.

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

## 3. Facts about mctl-api, and what is verified

Verified on GitHub on 2026-11-22: mctl-api#1153, #1154 and #1155 (S1 to S3)
are merged and shipped in release 4.173.0, and #1153's description says the
slices were agreed with the owner. The rest is from a read-only scouting pass
the same day against the default branches, to be re-checked if the code
moves: the read tool lives in
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

1. **Record a GO for steps 1 and 2 as built** (section 1). Still open. They
   were built on direction in session; the #2828 text asks for a written
   security GO.
2. **Dispatch credential.** Still open. (a) the existing broad token now, the
   way the portal apply tool does, with the narrow `mctl-gitops-dispatch` App
   as a follow-up; (b) move to the narrow App first, which needs its key held
   where mctl-api can read it and a rotation path. The S3 plan assumes (a),
   because it adds no new secret and the workflow's guards bound what a
   dispatch can do. No explicit owner answer is recorded for it.
3. **MFA on the request.** Decided 2026-11-22 (the slices are described as
   agreed with the owner in mctl-api#1153): option (b), a dedicated kind
   `release.window` with an MFA decide page. This replaces the recommendation
   of (a) that the first version of this file made. The earlier reasoning is
   kept for the record: the design's section 8.2 sends a window through normal
   review with no self-approval and the merge queue, and the real approval is
   the merge, which is a person on a protected path. The kind adds a second,
   earlier human step on the request.
4. **GO to implement the tool.** Given in session on 2026-11-22 for the
   release of S1 to S3 and for the first real run, both done (4.173.0, flag on
   through gitops#2909). Any real window on `main` is a separate decision.
   Open follow-ups from the S3 review (mctl-api#1155, P3): settle on
   `context.WithoutCancel` so a client disconnect does not leave the approval
   `in_flight` for the 10-minute reclaim, and an `in_flight` row past
   `expires_at` reports `ErrApprovalInFlight` instead of expired.
