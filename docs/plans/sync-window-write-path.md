# Sync-window write path: what is built, and the mctl-api step (#2828 S1)

**Status (updated 2026-11-22, evening): steps 1 and 2 are built and merged.
The mctl-api step is built in three slices: S1, S2 and S3 are merged
(mctl-api#1153, #1154, #1155), released as mctl-api 4.173.0, and switched on
with `RELEASE_WINDOWS_ENABLED=true` (gitops#2909). The first real run was
made and watched the same evening (section 2). No window is on `main`.
On 2026-11-23 the owner decided that the MFA approval itself queues the
window pull request for merge (section 5, item 6); that is built and was run
live the same day (gitops#2975 merged). Removal of a window is designed in
section 6 and not built yet. Section 5 records which
decisions are now made and which are still open. This file authorises nothing;
merging it is not a GO.**

This is the "new proposal" that section 1 of the #2828 design
(`platform-gitops/agents-state/mctl-gitops/proposals/issue-2828-spike-release-governed-release-calendar/design.md`)
asks for before S1. That design is research-only and authorises nothing, and
it says any AppProject, window, MCP tool or production change needs a separate
owner security GO. Steps 1 and 2 below were built on the owner's direction in
a working session. The owner gave the written GO for them as built on
2026-11-22, in session (section 5, item 1).
None of them applies a window: every step opens or checks a pull request that
a person reviews and merges.

## 1. What exists

| Piece | Where | Effect |
|---|---|---|
| Read tool for live windows | mctl-api 4.172.0, gitops #2857 and #2864 | admin-only list of what Argo CD holds; writes nothing |
| Window validator | `scripts/validate-argocd-sync-windows.py`, gitops #2880, run in `validate` | refuses default project, `allow`, `manualSync`, globs, bad schedule |
| Render-only proposal tool | `scripts/render-sync-window.py`, gitops #2881 | patch and matched set against the rendered inventory; refuses recovery-chain, unknown and foreign applications |
| Protected paths | gitops #2889: CODEOWNERS and `protected_re` for the project templates, both scripts and `app-project-consumers.json` | a window PR is never machine-merged (true as built; section 5, item 6 changes this for the release-window PR only, once built) |
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

1. **GO for steps 1 and 2 as built** (section 1). Given by the owner in
   session on 2026-11-22 as an explicit yes to this exact item, and recorded
   here at the owner's direction. It covers the two steps as built and
   released, not a window on `main`.
2. **Dispatch credential.** Decided 2026-11-22: (a), the existing broad token
   now, the way the portal apply tool does, with the narrow
   `mctl-gitops-dispatch` App as a follow-up. The residual risk in section 4,
   item 1 is accepted for now: the workflow's own guards bound what a dispatch
   can produce, not who can send it. Revisit when the narrow App is built.
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
   The S3 review follow-ups (settle detached from the request, expired
   `in_flight` claim reports expired) are merged in mctl-api#1156 and go live
   with the next mctl-api release.
5. **Portal exposure.** Decided 2026-11-22: `mctl_get_sync_windows` and
   `mctl_propose_release_window` are enabled on the Cloudflare MCP portal,
   because the owner is its only user (mctl-api#1159). The portal switch
   decides visibility only; the API's role check, the MFA page and the receipt
   gate stay the access control.

6. **Auto-merge after the MFA approval.** Decided 2026-11-23, in session, by
   the owner. It reverses the rule that a window pull request is never
   machine-merged (section 1, protected paths; design section 8.2): the human
   merge stops being the approval, and the MFA approval on the decide page
   becomes it. What this item decides, and what it does not:
   - **Consent says so.** The decide page, and the description of call 2 of
     `mctl_propose_release_window`, must state that approving means the window
     is queued for merge into `main` and applied by Argo CD without a further
     review, next to the project, applications, schedule and duration being
     approved. The owner's reason: if the consent names the effect, the
     approval is informed and nothing else has to stand in for it.
   - **Who merges.** The `release-window-pr.yml` workflow, after it has opened
     the pull request, enqueues it through the merge queue with the
     `enqueuePullRequest` mutation and `expectedHeadOid` set to the head it
     opened. It does not merge directly, and `mctl-gitops-pr` does not become a
     bypass actor of `main-protection`: the queue still runs `validate`,
     `reserved-hosts` and `cloudflare-plan`, and the ruleset still wants its
     approving review; the job waits for that review and for green checks on
     the exact head before it enqueues.
   - **No exception in `auto-merge.yml`.** As built, `protected_re` is not
     lifted: `auto-merge.yml` keeps refusing these paths. The only way in is
     the `enqueue-window` job of `release-window-pr.yml`, on main, in the
     `app-gitops-pr` environment. `scripts/release-window-enqueue-wait.sh`
     enqueues only the head the opening job pushed (`EXPECT_HEAD`), only when
     the pull request is from `mctl-gitops-pr[bot]`, on a `release-window/`
     branch in this repository, and changes exactly one file, the apps or
     platform project template, with no rename. Anything else is refused.
   - **Fail closed.** A red check, a Claude review that does not approve, a
     stale `base_sha` or a refused enqueue leaves the pull request open and no
     window on `main`. Nothing here forces a merge.
   - **Not decided here.** Whether the Claude review approves a pull request on
     those paths is not verified; if it does not, the approval is the open
     question for the first live run, and the pull request simply stays open
     until it is settled. Removal of a window is its own proposal, section 6 and
     item 7.
   - **Order of work.** (1) this record; (2) mctl-api: decide-page and tool
     text; (3) mctl-gitops: the enqueue step and the narrowed exclusion, with a
     test that a pull request outside the exception is still refused. A window
     that reaches `main` still needs the live run and its own owner decision,
     as item 4 says. This item authorises none of the three steps' release.

7. **Removal of a window.** Decided 2026-11-23, in session, by the owner,
   after the first real window was merged and had no way out except a
   hand-made pull request: a new tool `mctl_propose_window_removal`, a
   separate kind, and the same shape of merge as item 6 (the MFA approval
   queues the removal pull request; no person merges it). The design is
   section 6. This item authorises building it; releasing it, switching it on
   the portal and the first live removal are separate steps, each asked for.

## 6. Removal of a window (design, not built)

Why it is not a flag on the existing tool: an approval to add a block is
never to be spendable as an approval to lift one. Removal is therefore its own
kind, its own hash domain and its own decide-page text.

**Tool.** `mctl_propose_window_removal`, two calls like the add tool. Call 1
takes `project` (`apps` or `platform`) and the window exactly as
`mctl_get_sync_windows` reports it (`applications`, `schedule`, `duration`),
reads main's template, and requires exactly one `deny` window in that
project's `spec.syncWindows` that matches field for field. No match, more than
one match, or a template it could not read is a refusal, never a guess or an
empty result. It returns a pending approval and a decide URL and changes
nothing. Call 2 takes only `approval_id` and dispatches the removal workflow.
Admin-only, requester-only, same as the add tool.

**Approval.** Kind `release.window.removal`, policy
`release.window.removal.owner`. The approval hash is over
`{"action":"remove","project":P,"window":W}` (canonical JSON, same rules as
`release-window-insert.py hash`), and the args digest uses its own domain
string, so an approval for an addition cannot be replayed as a removal or the
reverse, even for the same project and window. The idempotency key carries
`base_sha` as for additions.

**Decide page.** Same fresh sign-in and MFA as the add page, with its own text:
it names the project, the applications, the schedule and the duration being
lifted, and says that approving means the window is removed, a pull request
for it is queued for merge into `main` with no person reviewing or merging it,
and the listed applications may sync during that time once Argo CD has applied
it. Until the second call nothing is changed.

**Workflow.** `release-window-removal-pr.yml`, a sibling of
`release-window-pr.yml` with the same guards: dispatch on main, App
`mctl-gitops-pr`, environment `app-gitops-pr`, a branch
`release-window-removal/<id>`, an existing branch or open pull request for the
id is refused, the window is rebuilt from the inputs and must hash to the
approved value, `base_sha` must be an ancestor of main with the target
template unchanged since. Its own script deletes exactly one window block by
text (the templates are Helm templates, so never load and dump), and removes
the `syncWindows:` key too when that was the last window, so that adding and
then removing a window returns the file byte for byte. A shape the script does
not recognise is exit 2. The job re-renders and requires the matched window to
be gone and everything else unchanged. The diff must be deletions of that one
block in one file, the apps or platform template, with no added line.

**Merge.** The same `enqueue-window` shape as item 6, driven by
`scripts/release-window-enqueue-wait.sh`, which is parameterised by the kind
(`add` or `remove`, nothing else) and checks the branch prefix and the diff
direction for that kind. A removal pull request is refused by the add guard
and an addition by the removal guard. Fail closed: red checks, a review that
does not approve, a stale `base_sha` or a refused enqueue leave the pull
request open and the window in place.

**What it can and cannot remove.** Any `deny` window in the `apps` or
`platform` template that the read tool reports and that matches exactly,
including one that was not added by this path. It never touches `default`, and
it never edits anything but the window block. The decide page shows what is
being lifted, which is the control; nothing marks a window as one the tool may
not remove.

**Order of work.** (1) this record; (2) mctl-gitops: the removal script, the
workflow, the parameterised enqueue guard and tests, each guard proven by a
mutation; (3) mctl-api: the kind, the request route, the decide page, the
tool and the execute route, dark behind the existing flag; (4) release through
the ledger, the portal catalogue line and allowlist entry, then one live
removal of the `labs-portfolio` window, each with the owner's word. Until
then a window is removed by a hand-made gitops pull request.

**Open question, not decided here.** Whether the new tool is exposed on the
Cloudflare portal like the add tool. Recommended: yes, the owner is the only
portal user and the portal switch decides visibility only; asked at step 4.
