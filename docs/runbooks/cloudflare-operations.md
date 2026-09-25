# Runbook — Cloudflare operations: break-glass, drift, apply, state

**Use this when** someone changed Cloudflare outside Git, when
`cloudflare-drift.yml` is red, when you are about to dispatch
`cloudflare-apply.yml`, or when the OpenTofu state for a Cloudflare root has to
be restored.

Written for mctlhq/mctl-gitops#1180, under the roadmap epic `mctlhq/.github#47`.
The background — layout, ownership boundary, credentials, what CI trusts — is in
`infrastructure/cloudflare/README.md`; this page is only the procedures and does
not repeat it.

Statements marked **Proposed** are policy the code does not determine. They are
drafts for review, not rules yet — confirm or change them in the pull request
that lands this page.

## The model in four lines

- **Git is the desired state.** Five roots, each an independent state key in
  `mctl-cloudflare-state`: `infrastructure/cloudflare/account`,
  `infrastructure/cloudflare/portal`, and `infrastructure/cloudflare/zones/mctl-ai`,
  `zones/mctl-me`, `zones/mctl-ru`. Roots are discovered by the presence of
  `versions.tf` (or `versions.tf.json`); `modules/` is not a root.
- **`cloudflare-apply.yml` is the only workflow that writes to Cloudflare.** It
  is `workflow_dispatch` only, one root per run, behind the `cloudflare-apply`
  environment. Merging a pull request changes nothing in Cloudflare.
- **`cloudflare-drift.yml` never applies.** It plans every root daily
  (`cron: '0 6 * * *'`, UTC), fails closed on any difference, and notifies
  Telegram. It has no write credential: it runs with the Object-Read-only
  `R2_PLAN_*` and passes `-lock=false`.
- **State has no versioning.** R2 has none; `opentofu-state-backup.yml`
  (`cron: '30 3 * * *'`) snapshots every state object to `_backups/<UTC
  timestamp>/` in the same bucket and keeps 30 days (`RETENTION_DAYS: '30'`).

What is **not** covered here, because it is not owned by these roots:

- objects owned by `mashkovd/mac-mini-infra` (see the ownership table in the
  README) — changes to them go through that repository's state, never this one;
- zone `dmitriimashkov.com` — intentionally unmanaged (#1089 decision 10), so a
  hand change there is the normal path, not break-glass, and nothing here will
  notice it;
- nothing on portal `mcp` any more: since mctlhq/mctl-gitops#1370 its switches
  and its tool mappings are `infrastructure/cloudflare/portal/mcp-portal.tf`,
  so a hand change there is break-glass like any other resource in that root,
  and the nightly plan reports it.

## 1. Break-glass — a dashboard or API mutation

### When it is permitted

From `infrastructure/cloudflare/README.md`: **a dashboard change is permitted
only to recover from an outage.** Anything that can wait for a pull request, a
green `cloudflare-plan`, a merge and a dispatched apply goes that way. Since
#1178 every managed root can apply from CI, so "the root cannot apply" is no
longer a reason to go around it.

An API call made with a personal or ad-hoc token is the same thing as a
dashboard click for the purposes of this section.

**Proposed:** who may perform a break-glass mutation — an operator who holds
Cloudflare dashboard access to the account and is responding to the outage. A
second person is informed at the time, not asked for approval, since approval
is what the outage does not leave time for. — confirm in review.

### What to record, at the time

Before or immediately after the change — not reconstructed afterwards:

| Field | Example |
| --- | --- |
| Object | `mctl.ai` zone setting `ssl`; or `cloudflare_dns_record.apex` in `zones/mctl-ai` |
| Root it belongs to | `infrastructure/cloudflare/zones/mctl-ai`, or "none — not declared anywhere" |
| Change | old value → new value, or "created" / "deleted", with the id the API returned |
| Actor | the operator's role, and whether dashboard or API |
| Timestamp | UTC, to the minute |
| Reason | the outage, with a link |

**Proposed:** where the record lives — a new issue in `mctlhq/mctl-gitops`,
titled `break-glass: <root> <object>`, opened by the operator who made the
change. The follow-up PR or apply run links to it and closes it. — confirm in
review.

This repository is **public**. The record names objects and values that are
already visible in `infrastructure/cloudflare/**`; it never carries a token, a
secret, a client secret or a personal address.

### The mandatory follow-up

**Proposed:** window — the follow-up PR (or, for a revert, the approved apply
run) is opened within one working day of the mutation, and the break-glass issue
stays open until drift is green on that root. — confirm in review.

The follow-up is exactly one of two things.

**A. Import the change into Git** — the change was right and should stay.

1. Write the configuration so it describes what is live.
   - For an object **already in state** (a managed record, ruleset or setting
     whose value was edited), change its attribute in the `.tf` file to the
     live value. No `import` block: the object is already tracked.
   - For an object that **did not exist in state** (created during the
     incident), add the resource *and* an `import` block pinning it to the id
     the API returned, in that root's `import.tf`. Without the `import` block
     the plan proposes creating an object that already exists.
   - A **zone setting** always exists at Cloudflare — there is no unset, only a
     default — so a newly declared setting always needs an `import` block, with
     id `"${local.zone_id}/<setting_id>"`.
2. Open the PR. The `cloudflare-plan` check for that root must read
   **`0 to add, 0 to change, 0 to destroy`**. `N to import` is expected and
   fine; anything else means the configuration does not yet match what is live
   — fix the configuration, do not "apply and re-import". Use
   `tofu plan -generate-config-out` and reduce the output rather than
   hand-writing resource bodies (the procedure is in
   `infrastructure/cloudflare/zones/mctl-me/README.md`, "How the configuration
   got here").
3. Merge, then run an import-only apply (section 3) against that root. Until
   that apply runs, the nightly drift run reports the pending import as
   `DRIFT` — expected, and it clears once the import is in state.

**B. Revert it via `cloudflare-apply.yml`** — the change was a stopgap and Git
is still right. No code change is needed: dispatch an apply against the root at
current `main` (section 3). Its plan shows the `update` (or `destroy`, for an
object created by hand *and* declared in the meantime — not the usual case) that
puts Git's value back; the reviewer approves that plan. Link the run from the
break-glass issue.

An object created by hand that is **not declared in any root** is invisible to
drift — OpenTofu only compares what is in state. It will never turn a run red.
If the decision is "revert", it has to be deleted by hand again and recorded the
same way; if "keep", path A above. Do not rely on drift to remind anyone.

### Worked example: the hand-applied zone settings of #1142, #1154, #1168

These three changes were not outage recoveries. They were made through the API
because, at the time, the zone roots held local state, were listed in
`.local-state-roots`, and `cloudflare-apply.yml` refused them. #1178 removed
that constraint, so today the same changes would be an ordinary PR and apply.
They are the worked example because they are the import path, done three times
end to end with the plan output recorded.

1. **#1142 — a new DNS record.** The Google Search Console TXT record for
   `mctl.ai` was created through the API. The PR added
   `cloudflare_dns_record.google_site_verify` to `zones/mctl-ai/dns.tf` and an
   `import` block with the id the API returned to `zones/mctl-ai/import.tf`.
   Attribute values followed what the API stored (content unquoted, `comment`
   set), not the surrounding style — either difference would have read back as
   a diff. CI: `Plan: 22 to import, 0 to add, 0 to change, 0 to destroy`.
2. **#1154 — two zone settings on existing zones.** `min_tls_version = "1.2"`
   and `always_use_https = "on"` were applied through the API on 2026-09-10 to
   all four zones, verified live (`curl -sI http://…` → `301`; a TLS 1.1
   handshake refused), then declared in `modules/zone-baseline/main.tf` and
   `zones/mctl-ai/tls.tf` with `import` blocks per zone. The first draft of that
   PR declared the values *before* applying them and would have left drift red
   every night on a root nobody could apply — the reason the order is "live
   first, declared second" for this path.
3. **#1168 — `ssl = strict`.** Rolled out one zone at a time (`mctl.ru` first),
   checked through the edge after each flip, then declared and imported the same
   way. Expected and observed: `mctl.ai 26`, `mctl.me 14`, `mctl.ru 7` to
   import, `0 to add, 0 to change, 0 to destroy`.

What each root's README records as its zero-diff plan is the number to compare
against. The import-only applies that finally put those imports into shared
state are tracked in mctlhq/mctl-gitops#1281.

## 2. Drift reconciliation — `cloudflare-drift.yml` is red

### What red means

Drift runs one matrix job per discovered root (roots listed in
`.local-state-roots` are skipped; none are today). Each job runs
`tofu plan -detailed-exitcode` and the job summary heading says which case it
is:

| Summary heading | Exit | Meaning |
| --- | --- | --- |
| `` `<root>` — in sync (N resources) `` | 0 | Git and Cloudflare agree for everything in state. |
| `` `<root>` — DESCRIBES NOTHING `` | 0, warning | The root's state is empty, so this run watched nothing. Not red, but not coverage. |
| `` `<root>` — DRIFT `` | 2 | The plan is not empty. The full plan is in the summary. |
| `` `<root>` — plan failed (exit 1) `` | 1 | Not drift — the plan could not be computed (credential, refresh, init). Nothing was compared. |

The `infrastructure/cloudflare/portal` job runs two further checks, only after a
clean plan, because they cover what `tofu plan` cannot see:

- **OAuth registration** (`scripts/portal-auth-credentials-drift.py`) —
  `auth_credentials` is write-only, so an out-of-band change never shows in a
  plan. Exit 1 = drifted, 2 = could not run (including a failed selftest).
- **Tool catalogue** (`scripts/portal-catalogue-drift.py`) — exit 1 = stale,
  re-snapshot per `infrastructure/cloudflare/portal/README.md`; 3 = a waiver
  needs deleting or narrowing, **do not** re-snapshot; 4 = an upstream is
  missing from the portal; 2 = could not run, or a server serves no tools. The
  summary text under each heading says what to do; follow it.

The Telegram message names the root and, for the portal, which check spoke.

**Drift never applies.** It holds no write credential, takes no lock, and
nothing in it calls `apply`. A red run is a report and stays red until a human
changes Git or dispatches an apply.

### How to read the plan it publishes

Open the run (`gh run list --repo mctlhq/mctl-gitops --workflow cloudflare-drift.yml --limit 5`),
then the red job's summary. The same plan text is in that job's `Plan` step log.
For each address in the plan:

- `will be imported` — an `import` block whose import-only apply has not run
  yet. Resolved by the apply, not by a change in Git.
- `will be updated in-place` / `must be replaced` — the attributes marked `~`
  are where live Cloudflare differs from Git. The value on the left of `->` is
  what is **live**; the right is what Git says.
- `will be created` — the object was deleted outside Git and the plan wants to
  recreate it. `will be destroyed` — the object is in state but no longer in
  configuration.
- An apply of the same root running at the same minute can produce a one-off
  spurious alert; drift and apply deliberately do not share a concurrency
  group. Re-dispatch drift before treating it as real.

### Decision tree

```
red job
 ├─ "plan failed (exit 1)"  → not drift. Fix the root or its credential
 │                            (see the credential chains in the README),
 │                            re-dispatch drift.
 ├─ only "will be imported" → pending import. Dispatch the import-only apply
 │                            (section 3). No Git change.
 └─ real difference
     ├─ the live value is right → ACCEPT INTO GIT: section 1, path A.
     │                            PR with a zero-diff plan, merge.
     ├─ Git is right            → REVERT: dispatch cloudflare-apply.yml on main
     │                            (section 3); approve the plan that restores Git.
     └─ the object should not   → INTENTIONALLY UNMANAGED: stop managing it
        be managed here            without destroying it (below), and record the
                                   decision next to the others in the README.
```

**Intentionally unmanaged** means removing the object from state, not from
Cloudflare. Deleting its resource block alone makes the next plan destroy it.
Use a `removed` block for the address (OpenTofu drops it from state without
touching the live object) and apply it through `cloudflare-apply.yml`; the
plan's **destroy** column must read `0` — and `cloudflare-apply.yml` refuses a
destroying plan anyway unless dispatched with `allow_destroy`. This path has not
yet been exercised in this repository; treat the first use as a walkthrough and
record it. The precedent for "intentionally unmanaged" as a decision is
`dmitriimashkov.com` (#1089 decision 10).

**Proposed:** who decides — the operator who picks up the red run triages it
and names the branch; accepting into Git or declaring an object unmanaged goes
through an ordinary PR review, and a revert is decided by the `cloudflare-apply`
required reviewer when approving the plan. — confirm in review.

**Proposed:** response time — a red drift run is triaged the same working day,
and a root is not left red for more than two consecutive scheduled runs without
a comment on an issue saying why. — confirm in review.

### How the run goes green

The next scheduled run (`0 6 * * *` UTC) goes green on its own once Git and
Cloudflare agree. To confirm sooner, dispatch it from `main`:

```sh
gh workflow run cloudflare-drift.yml --repo mctlhq/mctl-gitops --ref main
```

Every root must read `in sync`; `DESCRIBES NOTHING` is a warning, not a pass
for a root that is meant to hold resources.

## 3. Apply — dispatching `cloudflare-apply.yml`

### Dispatch

Inputs: `root` (required, string) and `allow_destroy` (boolean, default
`false`). Dispatch from `main` — both jobs carry `if: github.ref ==
'refs/heads/main'` and the environment's branch policy allows `main` alone, so
from any other ref nothing runs.

```sh
gh workflow run cloudflare-apply.yml --repo mctlhq/mctl-gitops --ref main \
  -f root=infrastructure/cloudflare/zones/mctl-ru
# only when the plan is meant to destroy something:
#   -f allow_destroy=true
```

Name the root in canonical form: the full path from the repository root, no
trailing slash, no `./`, no `//`. `.github/scripts/cloudflare-assert-applyable-root.sh`
rejects anything else, anything outside `infrastructure/cloudflare/`, a module,
a directory without `versions.tf`, and any root listed in `.local-state-roots`.

The run has two jobs:

1. **`plan <root>`** — no environment, read-only credentials. Validates the
   root, runs `tofu init -lockfile=readonly`, asserts the backend
   (`.github/scripts/cloudflare-assert-backend.sh`: bucket
   `mctl-cloudflare-state`, key `cloudflare/<root-relative-path>/terraform.tfstate`,
   the exact R2 endpoint, `use_lockfile = true`), plans with `-lock=false`, and
   publishes the summary. It refuses an unrequested destroy here, before anyone
   spends an approval on it.
2. **`apply <root>`** — `environment: cloudflare-apply`; waits for the required
   reviewer. Then re-validates, checks a write token is mapped for the root,
   re-plans **with** the lock, asserts the digest, re-checks destroy, and runs
   `tofu apply tfplan` on that saved plan.

Only five roots have a write token mapped in the `apply` job's chain
(`CF_APPLY_TOKEN_ACCOUNT`, `_MCTL_RU`, `_MCTL_ME`, `_MCTL_AI`, `_PORTAL`); the
chain is the allowlist, and a new root cannot be applied until it is added there
and as an environment secret on `cloudflare-apply`.

### What the required reviewer approves

The `plan` job's summary: the `import | create | update | destroy` table, the
list of destroyed addresses if any, the full plan under "Full plan", and the
line ``Plan digest `<16 hex>` — apply refuses if the plan has changed by then.``

The approval is of **that plan**, not of the intention behind the dispatch. The
digest is a SHA-256 over the plan's sorted `resource_changes` and
`output_changes` (`PLAN_PROJECTION`, identical in both jobs); the plan itself is
never stored as an artifact. The `apply` job recomputes it from its own fresh
plan and applies only if it matches — so what is written is what was read.

Before approving, the reviewer checks:

- the root in the heading is the one intended;
- the counts match what the PR or the root's README says to expect (an
  import-only apply is `N to import, 0 to add, 0 to change, 0 to destroy`);
- every `update`/`destroy` in the full plan is one they can name a reason for.

Environment configuration as read on 2026-09-24
(`gh api repos/mctlhq/mctl-gitops/environments/cloudflare-apply`): one
required-reviewers rule, a custom branch policy of exactly `main`, and
self-review **not** prevented — the person who dispatched a run can approve it.

**Proposed:** the approver reads the full plan in the `plan` job summary before
approving even when they dispatched the run themselves, and a destroying plan
(`allow_destroy`) is approved by someone other than the dispatcher where a
second reviewer is available. — confirm in review.

### When a check refuses

**Digest mismatch** — the `apply` job fails at "Assert the approved plan is
still the plan" with
`the plan changed after approval (approved <old>, now <new>) — refusing to apply`.
Nothing was written. Both jobs check out the same commit, so the change came
from Cloudflare (or its state), not from Git: the ordinary cause is out-of-band
drift arriving between the two jobs.

1. Read the new plan in the `apply` job's `Plan` step log and compare it with
   the approved summary. The difference is the out-of-band change.
2. Treat it as drift (section 2): decide accept / revert / unmanaged. If it is a
   break-glass change, it also gets its record (section 1).
3. **Re-dispatch** the workflow for a fresh `plan` job and a fresh approval.
   Do not use "Re-run failed jobs": that re-runs `apply` against the old
   digest and fails the same way while the difference persists.

**Other refusals, and what they mean:**

| Message (abridged) | Job | Action |
| --- | --- | --- |
| `name the root in canonical form …` / `is not under infrastructure/cloudflare/` / `is a module, not a root` / `is not a root — no versions.tf` | both | Re-dispatch with the right `root`. |
| `is listed in .local-state-roots — it has no remote state to apply against` | both | See section 5. The root has to move onto the backend first. |
| `backend … expected …` | both | The root's `backend.tf` does not match the convention; fix it by PR. Never work around it — a wrong key plans from empty state and proposes creating everything. |
| `this plan destroys N resource(s) and the run was dispatched without allow_destroy` | both | If every listed address is meant to go, re-dispatch with `allow_destroy`. Otherwise the destroy is the problem. |
| `no write token is mapped for '<root>'` | apply | Add the root to the `apply` job's token chain and its token as a `cloudflare-apply` **environment** secret (never a repository secret). |
| `1010` / `10000` in the `plan` step | plan | A read credential does not cover the root (see "Three workflows, not two" in the README). |

A stale state lock after a crashed apply: remove it only after confirming no
apply is running — the command is in `docs/runbooks/opentofu-state-restore.md`,
step 3.

## 4. State restore and the drill

The procedure is `docs/runbooks/opentofu-state-restore.md`; it is not repeated
here. The two points operators most often need from it:

- **Never apply a plan reached by losing state.** Restore first.
- The verification after a restore is a plan reading `No changes.` — nothing
  else counts.

The last drill — 2026-09-09, full restore on a scratch key
`_drill/mctl-ru/terraform.tfstate`, **passed** — and every later one are
recorded in the "Drill" table at the end of `opentofu-state-restore.md`. That
table is the one place drill results go; this page does not keep a second copy.

**Proposed:** cadence — re-run the drill once per quarter, and additionally
after any change to `opentofu-state-backup.yml`, to a root's `backend.tf`, or
to the state credentials. The next one is due by 2026-12-09. — confirm in
review.

Worth knowing when planning the next drill: the 2026-09-09 drill predates the
migration of the zone roots onto R2 (#1178) and predates `cloudflare-apply.yml`
writing shared state, so it exercised the snapshot and restore mechanics but not
a restore of a state object that CI applies against. Use the same scratch-key
approach so a failed drill cannot damage live state.

## 5. Roots off the shared backend — `.local-state-roots`

`infrastructure/cloudflare/.local-state-roots` lists roots knowingly **not** on
the shared R2 backend, one per line (`zones/mctl-ru` and
`infrastructure/cloudflare/zones/mctl-ru` are equivalent;
`.github/scripts/cloudflare-local-state-roots.sh` normalises them). It is
**empty** as of #1178, which is its normal end state — the file stays, so the
next exception is declared rather than worked around.

What listing a root does, operationally:

| Consumer | Effect on a listed root |
| --- | --- |
| `cloudflare-drift.yml` discovery | Skipped: printed as "not watched", never planned. An entry that names no discovered root stops the drift run. |
| `cloudflare-plan.yml` "Assert remote backend" | Allowed to resolve `local` (with a warning that its plan does not reflect live Cloudflare); fails if it resolves any other backend while still listed. |
| `cloudflare-apply.yml` (both jobs) | Refused by `cloudflare-assert-applyable-root.sh`. |

So a listed root is **unwatched and unappliable**. Its CI plan runs against
empty local state on a fresh runner, so it says nothing about what is live.

**Why its objects must not be changed by hand.** For a managed root, a hand
change is caught — drift goes red and this runbook takes over. For a listed
root nothing catches it: drift skips the root, there is no shared state to
compare against, and apply refuses it, so there is no revert path either. A
hand change there silently becomes the only record of itself. That is exactly
how #1142, #1154 and #1168 had to be done (section 1), and why #1178 moved the
zone roots onto the backend rather than normalising the exception.

To change a listed root, migrate it first: declare the `backend "s3"` block
(bucket `mctl-cloudflare-state`, key
`cloudflare/<root-relative-path>/terraform.tfstate`, `use_lockfile = true`),
remove its line from `.local-state-roots` in the same PR, then run its
import-only apply through `cloudflare-apply.yml` and confirm drift reads
`in sync`. #1178 and #1281 are the precedent.

## Current state (2026-09-24)

- mctlhq/mctl-gitops#1111 (the apply identity) is closed; every root has a
  write token mapped and `cloudflare-apply.yml` has applied the account and
  portal roots.
- The three zone roots have been on the R2 backend since #1178, but their
  import-only applies are **not done**: the runs dispatched on 2026-09-22 are
  still waiting on the `cloudflare-apply` reviewer (tracked in
  mctlhq/mctl-gitops#1281). Until they run, nightly drift is red on those roots
  with pending imports only — the "only will be imported" branch of the decision
  tree. A drift-reconciliation or break-glass walkthrough on a zone root has to
  wait for #1281; one on `account` or `portal` does not.

## Walkthrough record

mctlhq/mctl-gitops#1180 closes only after each procedure below has been walked
through once by an operator following this page. Record the date, the
operator's role (not a name) and the outcome, including anything in this page
that turned out wrong.

| Procedure | Date | Operator (role) | Outcome |
| --- | --- | --- | --- |
| Break-glass (section 1) | — | — | not yet walked through |
| Drift reconciliation (section 2) | — | — | not yet walked through |
| State restore (section 4) | — | — | not yet walked through |
