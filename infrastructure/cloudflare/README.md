# Cloudflare — declarative control plane

Git is the desired state for Cloudflare configuration; OpenTofu applies it; the
state lives in an mctl-owned R2 bucket and never in this repository.

Roadmap: `mctlhq/.github#47`. Inventory and the zero-diff proof: `mctl-gitops#1083`.

## Engine

**OpenTofu** (`tofu`, `>= 1.9`) with `cloudflare/cloudflare ~> 5`.

The neighbouring `infrastructure/k3s-preview` root runs on HashiCorp Terraform
1.14 and is deliberately left alone — two engines coexist in this repository.
That is a decision, not drift: migrating a working cluster root for the sake of
uniformity would risk live infrastructure for no benefit. CI keeps them apart by
path, and the Cloudflare workflows install OpenTofu explicitly.

## Layout

Each directory containing a `versions.tf` is an independent root with its own
state key and its own lock. Roots are discovered automatically by the workflows,
so adding one requires no CI change.

```
infrastructure/cloudflare/
  account/      account-scoped resources (R2, Access, Zero Trust, MCP)
  zones/<zone>/ one root per zone — independent blast radius
```

One root per zone rather than one shared root: `mctl.me` and `mctl.ru` only
serve redirects while `mctl.ai` carries live tenant traffic, so a mistake in one
should not be able to lock or damage another.

## Ownership boundary — read this before importing anything

Some Cloudflare objects in this account are **already managed by another
OpenTofu state** and must not be imported here until #1090 transfers them:

| Object | Owner |
| --- | --- |
| Tunnel `mac-mini-mctl` (`2e60e134-…`) and its config | `mashkovd/mac-mini-infra` |
| DNS `jellyfin.mctl.ai`, `media.mctl.ai` | `mashkovd/mac-mini-infra` |
| Zone ruleset `mac-mini media cache policy` (`mctl.ai`) | `mashkovd/mac-mini-infra` |

The DNS records carry the comment `Managed by mac-mini-infra OpenTofu`. **The
ruleset carries no such marker** — it is identifiable only by its name, so it is
the easiest of the three to import by accident.

Managing the same object from two states is what #47 explicitly forbids: both
sides would fight over it, and a plan in one would propose undoing the other.

## Pre-import decisions (#1089)

The account carried objects that were stale, duplicated, or broader than
intended. Importing them would have made each one look deliberate the moment it
landed in Git, so every one was decided first. Decisions taken 2026-09-09;
evidence and reasoning in #1089.

| # | Object | Decision |
| --- | --- | --- |
| 1 | Access app `media` | **keep** — repointed to `media.mctl.ai`; the live gate in front of Overseerr |
| 2 | Access apps `Temporal`, `News AI` (`*.mbank.space`) | **delete** |
| 3 | Access app `vault` → `mashkoffdmitry-openclaw.mctl.ai` | **keep, rename** to match the host it protects |
| 4 | Access org `auth_domain: mbank.cloudflareaccess.com` | **keep** |
| 5 | Page rules `*.mctl.me/*`, `*.mctl.ru/*` | **delete** — unreachable, see below |
| 6 | In-zone `NS launch1/launch2.spaceship.net` in `mctl.me` | **delete** |
| 7 | Disabled catch-all `drop` in `mctl.ai` Email Routing | **enable** |
| 8 | Rule `seerr` in `mctl.ai/http_request_firewall_custom` | **keep, narrowed** by hostname |
| 9 | `mctl-landing-form` and its 5 worker routes | **split** — routes here, script and secrets in Wrangler |
| 10 | Zone `dmitriimashkov.com` | **intentionally unmanaged** |

Four of these are kept rather than removed, and each is kept for a reason that
is not obvious from the object itself.

**`auth_domain` (4).** It reads like leftover naming from a previous project,
and it is — but it is a single per-account Zero Trust value that appears in
every application's login redirect regardless of zone. Renaming it invalidates
every live Access session at once. Kept deliberately, not overlooked.

**`allowed_idps` (part of 1 and 3).** Every application now pins
`allowed_idps: [Google]`. An empty list does not mean "no restriction beyond the
policy" — it means *all* providers, which made the account-level `onetimepin`
reachable next to Google on `media` and `jellyfin`. The policies required
`login_method == Google`, so there was no authorization hole, but the OTP flow
was reachable far enough to mail a code to an arbitrary address before refusing.
Pinned 2026-09-09. **Import the pinned state as-is** — it is hardening, not
drift, and reconciling back to the empty list would undo it.

**The `seerr` bypass (8).** `(ip.src.asnum eq 24940)` skips Super Bot Fight Mode
for the whole of Hetzner — every Hetzner customer, on every `mctl.ai` hostname
including the `*.mctl.ai` wildcard that serves every tenant. It exists because
the platform's own cluster — which is hosted in `AS24940` — was being
classified as bot traffic on its server-to-server calls. Narrowed to the
hostnames that actually need it rather than removed; the bypass itself is
legitimate, its breadth was not.

**Worker ownership (9).** `cloudflare_workers_route` is owned here; the script
and its seven runtime secrets stay in Wrangler. OpenTofu does not deploy Worker
code, so owning the script here would split one deployable across two owners.
The route patterns are part of the worker's contract — change them in one place.

### Redirects: what actually serves them

Worth stating because the wrong answer is the intuitive one. `mctl.me` and
`mctl.ru` redirect to `mctl.ai` through **two** mechanisms, and the page rules
are neither:

- **apex** — the `http_request_dynamic_redirect` ruleset, one rule per zone
  (`http.host eq "mctl.me"` → 301 `concat("https://mctl.ai", http.request.uri)`);
- **subdomains** — the worker `mctl-landing-form`, in code
  (`REDIRECT_SUFFIXES = [".mctl.me", ".mctl.ru"]`).

The page rules match the same subdomains but never fire: the worker runs first
and returns. The proof is that the same URL answers differently on User-Agent
alone — the worker's bot filter returns `410` for `curl/`, while a browser gets
`301` — which no page rule can do. Hence decision 5.

So a change to worker routes moves the subdomain redirect. Whatever PR touches
them has to re-check subdomain redirects; no zone-level configuration here will
catch that regression.

## Credentials

Nothing is committed. CI reads:

- `R2_PLAN_ACCESS_KEY_ID` / `R2_PLAN_SECRET_ACCESS_KEY` — state access for plan
  and drift. **Object Read only, scoped to `mctl-cloudflare-state` alone.**
  Verified: `PutObject`, `DeleteObject`, and any other bucket — including
  `mctl-terraform-state` — all return `AccessDenied`. Both jobs pass
  `-lock=false`, because taking the state lock is itself a write.
- `R2_CF_STATE_ACCESS_KEY_ID` / `R2_CF_STATE_SECRET_ACCESS_KEY` — Object Read &
  Write on `mctl-cloudflare-state` alone, used by the backup workflow.
- `CLOUDFLARE_API_TOKEN` — plan identity, **read-only across all zones**
  (`Cache Rules`, `DNS`, `Zone`, `Zone Settings`, `Zone WAF`, `Single Redirect`,
  `Page Rules`, `Access: Apps and Policies`, `Email Routing Rules`,
  `Workers Routes`, all `Read`). Verified read-only: a `POST` to create a DNS
  record is rejected. Apply will need a separate, narrower write identity —
  it does not exist yet, and no workflow here performs an apply.
- `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` — writable on
  `mctl-terraform-state`, used only to back that bucket up. Never exposed to a
  job that plans unreviewed pull-request code.

Mirror copies live in Vault under `secret/platform/cloudflare/`.

## State

Bucket **`mctl-cloudflare-state`** on R2, one key per root, `use_lockfile = true`
(native S3 conditional-write locking — no DynamoDB equivalent needed).

**R2 has no object versioning.** `GET /accounts/{id}/r2/buckets/{b}/versioning`
returns `10015: No route matches this url`, and the feature does not exist. The
usual "turn on bucket versioning" answer is unavailable here, so state durability
depends entirely on `opentofu-state-backup.yml`, which snapshots every state
object daily into `_backups/<UTC timestamp>/` and keeps 30 days. Restore
procedure: `docs/runbooks/opentofu-state-restore.md`.

Snapshots live in the **same bucket** as the state they protect, under
`_backups/`. That is a limitation, not a design preference: each backup
credential is scoped to a single bucket, so a genuine off-bucket copy is still
not possible. The snapshots do protect against the failure that actually occurs
— state corrupted by a bad apply, an accidental `state rm`, a botched import —
but not against loss of a bucket itself or compromise of the credential that
writes to it. Closing that would need a third bucket and a write-only token
for it.

## Workflows

| Workflow | Trigger | Behaviour |
| --- | --- | --- |
| `cloudflare-plan.yml` | `pull_request` | fmt, validate, plan per root. A failure fails the check — there is no `continue-on-error`. Destructive changes are called out in the summary. The `cloudflare-plan` job is the stable context to mark required: it runs on every pull request, including ones that touch nothing here. Losing root coverage is blocked, in all three shapes that reach it: a root that stops being discovered; a root with no `s3` backend, which silently plans against empty local state; and configuration that sits in no root's own directory — a subdirectory of a root included, since OpenTofu loads only the files directly in the working directory. `versions.tf.json` counts as a root marker exactly as `versions.tf` does, and `modules/` is exempt on both sides: a shared module is not a root and its files are not orphans. Which backend a root actually uses is not decided by reading `backend.tf` — a comment mentioning `backend "s3"` next to a live `backend "local"` would satisfy any text match — but by what `tofu init` resolved: the plan job reads `backend.type` out of the data directory it wrote. Roots knowingly off the shared backend are listed in `infrastructure/cloudflare/.local-state-roots`, which both checks read; today that is `zones/mctl-ru`, left on local state by the import pilot, whose migration belongs to #1103. In each case the resources stay live in Cloudflare while leaving both plan and drift. Fix the root, or label the pull request `cloudflare-root-removal` to hand ownership over deliberately — labelling re-runs the check, which is why the trigger lists `labeled`/`unlabeled`. |
| `cloudflare-drift.yml` | schedule | plan per root; any difference from Git fails the run and notifies. It never applies. Roots listed in `.local-state-roots` are skipped: with no remote state to compare against, such a root reports its whole content as pending every night — a false alarm that would train everyone to ignore the real one. Skipping it is not coverage; it is the absence of coverage, stated out loud. |
| `opentofu-state-backup.yml` | schedule | copies every state object in both state buckets to a dated prefix under `_backups/` in the same bucket — see the limitation noted above. Restricted to `main` by the `state-backup` environment's branch policy, since `workflow_dispatch` would otherwise run a rewritten copy of this file from any branch with the writable credential. |

Apply is deliberately not automated. Drift fails closed and requires a reviewed
decision rather than a blind reconcile.

### What CI trusts, and what a reviewer still has to check

A pull request that adds or edits a root is code that CI runs with the plan
credentials in its environment — roots are discovered from the pull request's
own tree, and OpenTofu configures providers and evaluates data sources during
plan. Forks get no secrets; branches in this repository do, including the ones
opened by automation.

Provider installation is therefore restricted to `cloudflare/cloudflare`
(`TF_CLI_CONFIG_FILE` in both workflows). That removes the usual code-execution
vectors — `hashicorp/external` with a shell `program`, the `http` data source
and friends — at init, before plan runs.

**Why Cloudflare state lives in its own bucket.** `mctl-terraform-state` holds
`k3s-preview/terraform.tfstate`, which contains an OpenSSH private key and
kubeconfig `client-key-data` for the preprod cluster — confirmed by reading it.
R2 tokens scope to a bucket, not a prefix, so any credential able to read
Cloudflare state in that bucket could also read the cluster's. Splitting the
buckets is what makes the plan credential genuinely low-value; without it,
"read-only" would still have meant "can fetch the cluster's SSH key".

What the allowlist does not remove, worth a glance in any PR touching a root:

- **`provider "cloudflare" { base_url = … }`** — `base_url` is an optional,
  non-sensitive provider attribute, so a root can point the provider at an
  arbitrary host and the API token follows. That token is read-only across the
  four zones, so the loss is disclosure of configuration rather than control.
- **a `backend "s3"` block with its own `endpoints`** — the R2 access key id and
  a SigV4 signature would be sent there. Since the plan credential is
  Object-Read-only on a single bucket, what leaks is the identity of a key that
  cannot write anything.

Both are failures of confidentiality at worst, and only of Cloudflare
configuration: what leaks is a read-only zone token and the identity of a key
that can read one bucket of Cloudflare state and write nothing.

Note also that a root can produce output from arbitrary OpenTofu expressions —
`base64encode(file("/proc/self/environ"))` defeats exact-value secret masking.
The allowlist does not stop that, which is precisely why the credentials in the
job are chosen to be worth stealing as little as possible.

## Break-glass

A dashboard change is permitted only to recover from an outage. It must be
followed by a PR that either imports the change or reverts it — an unreconciled
dashboard edit will surface as a drift failure and stay failing until someone
resolves it.
