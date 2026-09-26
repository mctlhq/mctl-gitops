# Design: issue-1416-chore-cloudflare-iac-import-the-tg-seerr

## Current state

**The root.** `infrastructure/cloudflare/account/` is an independent OpenTofu
root (`versions.tf`: `cloudflare/cloudflare ~> 5`, `var.account_id` defaulting to
`6a09f637d20e1f66a8e9d45ebe778058`, credentials from `CLOUDFLARE_API_TOKEN`) on
the shared R2 backend (`backend.tf`; `infrastructure/cloudflare/.local-state-roots`
is empty, so no root is excused from it). It currently holds four files of
configuration:

- `projects-mcp.tf` — the customer-facing `projects.mctl.ai` application,
  created here rather than imported, with Access as its OAuth server.
- `portal-app.tf` — the portal's own application, `type = "mcp_portal"`,
  adopted through an `import` block with id
  `accounts/${var.account_id}/fd76d449-63a4-4c3a-83c5-4686a3815d2c` (lines
  24-27). Its body pins every live field so the import planned as a change of
  `session_duration` alone, including the three cookie flags at lines 56-58,
  whose comment records that leaving them unset made the provider plan
  `http_only_cookie_attribute` false -> true. Its policy is referenced by id
  only, `policies = [{ id = "5f0102c7-fd88-499c-9b15-9167633d6c63", precedence = 1 }]`
  (lines 64-69), with the comment explaining that writing it inline would rewrite
  the portal's own door as part of an import meant to change a duration.
- `portal-mcp-apps.tf` — three `type = "mcp"` member applications created by
  OpenTofu: `portal_member_projects`, `portal_member_alice`,
  `portal_member_coolify`. Each has `destinations = [{ type = "via_mcp_server_portal",
  mcp_server_id = "<server>" }]`, `session_duration = "8760h"`, and an **inline**
  policy named `Phase 0 pilot users` admitting two named addresses. Lines 34-36
  are the sentence this issue retires: "The three pre-existing sibling
  applications stay out of state for now … importing them is its own reviewed
  change rather than a rider on this one."
- The account `README.md`, whose "Imports arrive with" list still tracks `#1088`
  and a struck-through `#1092`, and whose opening paragraph ("Holds one
  application") predates every application added since.

There is no `import.tf` in this root — unlike `zones/mctl-*`, which collect
imports in one file — so the convention here is an `import` block sitting
immediately above the resource it adopts, with the reasoning in a comment
(`portal-app.tf`, and `portal/mcp-servers.tf` for `seerrsense` and `api`).

**No policy resource exists anywhere in the repository.** `grep -rn
"zero_trust_access_policy"` over the tree returns nothing: every policy in state
today is an app-scoped policy written inline inside an application's `policies`
list. This change introduces the first standalone policy resources, if the live
policies turn out to be reusable ones.

**The other side of the portal.** `infrastructure/cloudflare/portal/` is a
separate root with its own write token scoped to `Account -> MCP Portals`, and
already manages the seven server resources including `tg`, `seerrsense` and
`api` (`portal/mcp-servers.tf`, where `api` and `seerrsense` were themselves
adopted with `import` blocks of the form `${var.account_id}/<server id>`).
`portal-mcp-apps.tf:28-32` explains the split: an Access application belongs to
the root whose credential can write one, which is `account`.

**How the gate works.** `.github/workflows/cloudflare-plan.yml` discovers every
directory with a `versions.tf`, plans each on the pull request, and publishes a
summary table with `import | create | update | destroy` counts plus the full
plan (`Summarize` step, `imports` computed from
`select(.change.importing != null)`). It does not fail on adds or changes — it
surfaces them; the `0 to add, 0 to change, 0 to destroy` requirement is the
human rule stated in `docs/runbooks/cloudflare-operations.md` step 2. The plan
credential for this root is `CF_ACCOUNT_READ_TOKEN`, documented in that workflow
as `Account -> Access: Apps and Policies -> Read` on this account alone, which is
exactly the scope needed to refresh both an application and a policy during a
plan-time import. `cloudflare-apply.yml` then plans with the read token,
publishes a digest, waits on the `cloudflare-apply` environment reviewer, and
refuses to apply a plan whose digest moved.

**How adoptions are written here.** `docs/runbooks/cloudflare-operations.md`
step 2 and `infrastructure/cloudflare/zones/mctl-me/README.md` ("How the
configuration got here") are explicit: write the `import` blocks first, run
`tofu plan -generate-config-out=generated.tf`, reduce the generated bodies (the
generator emits every optional attribute as `null`), then **re-plan**, because
the first reduction of `mctl.me` silently set two TTLs wrong and only the
re-plan caught it. Hand-writing bodies is named as the thing not to do.

## Proposed solution

One pull request against `infrastructure/cloudflare/account`, import-only by
construction.

### 1. A new file for the adopted member applications

`infrastructure/cloudflare/account/portal-mcp-apps-adopted.tf`, holding, for each
of `tg`, `seerrsense` and `api`:

```hcl
import {
  to = cloudflare_zero_trust_access_application.portal_member_tg
  id = "accounts/${var.account_id}/${local.adopted_app_ids.tg}"
}

resource "cloudflare_zero_trust_access_application" "portal_member_tg" { ... }
```

Resource names continue the existing scheme (`portal_member_<server>`), so the
six member applications read as one set regardless of how each arrived. A new
file rather than an append: `portal-app.tf` already keeps this root's one adopted
application apart from the created ones, and a reader asking "what does this
change adopt" should not have to diff a 155-line file of unrelated resources.
`portal-mcp-apps.tf`'s header comment gets the cross-reference so the two files
are not discoverable only by grep.

All live ids — three applications, plus every policy id — go in one `locals`
block at the top of the new file:

```hcl
locals {
  # Read 2026-__-__ from GET /accounts/{account_id}/access/apps?type=mcp.
  # Not secrets: they identify objects in this account, the same way
  # portal-app.tf names fd76d449-… and projects-mcp.tf names the two IdPs.
  adopted_app_ids = { tg = "…", seerrsense = "…", api = "…" }
}
```

One block, because these ids are the only values in the change that cannot be
derived from the repository, and a reviewer should be able to check them against
the dashboard in one place. Literal UUIDs rather than a data source lookup is
this root's established position: `projects-mcp.tf:20-29` and the account
`README.md` record that a data source was tried for the identity provider and
removed, because the read-only plan identity returned an empty list instead of an
error — "a wrong answer that looks like an answer is worse than a pasted UUID".

### 2. Policies — one object, one resource, decided by what is live

The branch point is whether a policy the live applications reference is a
**reusable** account-level policy (returned by
`GET /accounts/{account_id}/access/policies`, importable as
`cloudflare_zero_trust_access_policy` with id `accounts/<account_id>/<policy_id>`)
or an **app-scoped** policy that exists only inside its application.

- **Reusable** → a new `infrastructure/cloudflare/account/portal-access-policies.tf`
  declaring one `cloudflare_zero_trust_access_policy` resource per distinct
  live policy object, each with its own `import` block. Every application that
  uses it references it as
  `policies = [{ id = cloudflare_zero_trust_access_policy.<name>.id, precedence = N }]`.
  If two of the three adopted applications share one policy object, they share
  the one resource — that is the issue's "never declare a second copy", and it
  is also a correctness requirement, since two resources importing the same id
  would fight on every plan.
- **App-scoped** → the policy is described inline inside the application's
  `policies` list at its live values, with a comment saying it has no standalone
  resource because it is not a reusable object. No extra `import` block: the
  policy arrives with its application.

`5f0102c7-…` on `mcp_portal` follows the same rule. If it is reusable, it gets a
resource and an `import` block in `portal-access-policies.tf`, and
`portal-app.tf:64-69` changes from a literal id to
`cloudflare_zero_trust_access_policy.portal_pilot_users.id` — a reference
swap that must plan `0 to change` on the application, which the plan proves. If
it is app-scoped, the literal-id reference stays exactly as it is and the comment
there is extended to say why, which still satisfies the issue's intent (the
object stops being untracked only if it is trackable as a resource at all; an
app-scoped policy is tracked by the application that owns it, and `mcp_portal` is
already in state).

Note the trap this ordering avoids: declaring a standalone policy resource for a
policy that is in fact app-scoped would plan a **create**, not an import — a
fourth "Phase 0 pilot users" policy object in the account, and a plan that fails
the `0 to add` rule. The live read decides, not the naming.

### 3. Bodies describe what is live, not what the siblings do

The three applications were created by the dashboard on 2026-09-10, so their
defaults are the dashboard's, not this repository's. The most likely difference
is `session_duration`: the managed siblings carry `8760h`, chosen deliberately by
the owner (`portal-app.tf:13-16`), while a dashboard-created application carries
24h. This change records whatever is live. Raising the trio to `8760h` is a
behaviour change and would show up as `3 to change`, failing the acceptance
criterion; it is a follow-up with its own plan and its own review. The same rule
covers `allowed_idps`, `auto_redirect_to_identity`, `app_launcher_visible`, the
three cookie flags (`portal-app.tf:53-58` is the precedent for pinning them) and
`cors_headers`.

`oauth_configuration` stays unset unless the live read shows it set — turning on
Access managed OAuth for a portal member would replace the authorization server
under connected clients, the same hazard `portal-app.tf:21-23` documents.

### 4. Comment and README maintenance

- `portal-mcp-apps.tf` lines 34-36 are rewritten: the three siblings are now
  managed, adopted in `portal-mcp-apps-adopted.tf` under this issue, with the
  import-apply run linked once it exists.
- The account `README.md` gets its "Holds one application" opener and its
  "Imports arrive with" list corrected to reflect six member applications, the
  portal application and the imported policies, so the root's own documentation
  does not keep describing a state two issues out of date.

### 5. Verification path

No credential is required to verify the *intent* of the change — the PR's
`cloudflare-plan` job does the reading, with `CF_ACCOUNT_READ_TOKEN`, and
publishes the full plan in the step summary. The loop is therefore: write
`import` blocks and bodies, push, read the published plan, reduce the diff,
push again, until the table reads `N to import, 0 to add, 0 to change, 0 to
destroy`. Where the implementer *does* hold an `Access: Apps and Policies Read`
token locally, the runbook procedure (`-generate-config-out`, reduce, re-plan)
is faster and is the documented path; the CI plan is the same instrument either
way, and it is the one the acceptance criterion names.

The live ids remain the one input that cannot come from this repository, and the
PR is not mergeable until they are real. That is stated in the PR body rather
than worked around, since every alternative (see below) either weakens the plan
token or lets the plan pass without describing the live objects.

## Alternatives

1. **Look the ids up with a data source** (`cloudflare_zero_trust_access_applications`,
   filtered by name, feeding the `import` block's `id`). Dropped on this root's
   own recorded experience: the read-only plan identity returned an *empty list*
   rather than an error for the identity-provider lookup
   (`projects-mcp.tf:20-29`), so a name-matching lookup that finds nothing would
   plan an import of nothing — or, worse, a name collision would import the
   wrong application. It also makes the adoption depend on a plan-time read that
   must be known before the import graph is built, which is fragile across
   provider and OpenTofu versions for a one-time change.

2. **Append the three applications to `portal-mcp-apps.tf`** instead of a new
   file. Genuinely defensible — one file per concern, and "portal member
   applications" is one concern. Dropped because the created-versus-adopted
   distinction is exactly what a reviewer of *this* PR is checking, and because
   the file's existing header comment is a long argument about why `projects`
   needed an application at all; an adoption note belongs next to the imports it
   explains. Reversible later at zero cost — moving a resource between files in
   the same root is not a state operation.

3. **Write one reusable policy resource and repoint all six member applications
   at it.** Attractive: the six inline `Phase 0 pilot users` policies are six
   objects saying the same thing, and one reusable policy would make "who may
   see the private aggregate" a single edit. Dropped as out of scope and unsafe
   here: repointing the three *created* applications would destroy their
   app-scoped policies and create a new object, which is `to add` plus
   `to destroy` in a plan that must be import-only, and it changes the authority
   path of live doors during an adoption. Worth its own issue.

4. **Import the applications and leave their policies alone.** Dropped: it does
   not satisfy #1092's acceptance criterion, and it is the weaker half of the
   protection. A policy is where "who" lives; an application in state whose
   policy is not means a dashboard edit that widens access still passes drift
   unnoticed.

## Platform impact

- **Migrations.** None in the cluster, and no data migration. State-only: three
  applications and `N-3` policies move from unmanaged to managed. No Cloudflare
  object is created, changed or destroyed if the acceptance criterion holds.
- **Backward compatibility.** Nothing reads these applications from Git; their
  consumers are Access itself and the portal. Because every field is recorded at
  its live value, `mcp.mctl.ai` behaviour for `tg`, `seerrsense` and `api` is
  unchanged by the import.
- **Resource impact.** Two new `.tf` files and a longer plan for one root. No
  runtime cost.
- **Risk: the plan is not actually import-only.** A missed field (a cookie flag,
  a `domain`, a `session_duration`) turns the adoption into a silent mutation of
  a live door on the first apply. Mitigation: the `0 to add/change/destroy` rule
  is the merge gate, the generated-then-reduced-then-re-planned procedure is
  mandated by the runbook precisely because a reduction got it wrong once, and
  `cloudflare-apply.yml` re-derives the plan digest before applying.
- **Risk: a duplicate policy object.** Declaring a standalone resource for an
  app-scoped policy plans a create, which would leave a second policy on the
  account. Mitigation: the live `GET /access/policies` read decides which branch
  applies, and any `create` in the plan blocks the merge.
- **Risk: `5f0102c7-…` is rewritten while being adopted.** The comment at
  `portal-app.tf:60-63` exists because that policy is the portal's own door.
  Mitigation: the policy resource body is generated from the live object, and the
  reference swap must plan `0 to change`; if it does not, the literal id stays
  and the policy is left for a dedicated change.
- **Risk: the wrong id is pasted.** An `import` of an id that does not exist
  fails the plan loudly — the safe direction. An id that exists but belongs to
  another application would import the wrong object and then plan changes against
  it, which the `0 to change` rule catches.
- **Expected red drift between merge and apply.** Per
  `docs/runbooks/cloudflare-operations.md` (path A, step 3, and the
  "`will be imported`" line in the drift-triage section), the scheduled
  `cloudflare-drift.yml` run reports `account` as `DRIFT` for pending imports
  until the owner-dispatched import-only apply lands. Expected, documented, and
  worth saying in the PR body so nobody triages it as a regression. It also means
  the apply should not be left sitting: an unapplied import masks real drift on
  that root for as long as it is pending.
- **Credential scope.** Unchanged. The plan token already carries
  `Access: Apps and Policies -> Read`; the apply token for this root already
  carries `Access: Apps and Policies Write` (account `README.md`). No new secret,
  no widened scope, no new root, so `cloudflare-plan.yml` and
  `cloudflare-drift.yml` need no edit.
