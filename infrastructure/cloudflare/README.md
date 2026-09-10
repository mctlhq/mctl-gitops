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
classified as bot traffic on its server-to-server calls. The bypass itself is
legitimate; its breadth was not. Narrowed to the hostnames that actually need
it:

```
(ip.src.asnum eq 24940 and http.host in
  {"secrets.mctl.ai" "ops.mctl.ai" "app.mctl.ai" "api.mctl.ai"
   "media.mctl.ai" "tg.mctl.ai" "workflows.mctl.ai"})
```

The list is not a guess. Cloudflare analytics cannot produce it on this plan —
`clientAsn` is not an accessible dimension, the firewall-events datasets are
either unavailable or empty, and a `skip` emits no firewall event in any case —
so it was derived from the platform side: the hostnames that in-cluster
workloads actually fetch server-side, as opposed to the many `*.mctl.ai` URLs
that are only displayed to users or received as inbound webhooks.

What each one is for, because the reason is what makes the entry safe to remove
later:

| host | caller |
| --- | --- |
| `app.mctl.ai` | Traefik `ForwardAuth`, on **every** request to openclaw, claude-remote and temporal-web; also `mctl-api` creating tenants |
| `secrets.mctl.ai` | `mctl-api` and `mctl-portal` Vault logins, and every service's Vault-cleanup PreDelete job |
| `ops.mctl.ai` | `mctl-api` (ArgoCD API and Dex OIDC discovery) and Grafana's OAuth token/userinfo calls |
| `api.mctl.ai` | openclaw's MCP proxy, `mctl-agents` (`MCTL_MCP_URL`, hardcoded) and its Temporal workers |
| `media.mctl.ai` | `seerrsense` → Overseerr, with the Access service token |
| `tg.mctl.ai` | the `mctl-telegram` canary CronJob, deliberately probing from outside |
| `workflows.mctl.ai` | Backstage's backend submitting Argo workflows (`argoWorkflows.baseUrl`) |

**The failure mode is worth knowing before editing this rule**, and it has
already caught us once. `workflows.mctl.ai` was first classified as
display-only — it appears in `cwft-mctl-agents-*.yaml` as a `UI_URL` pasted
into pull-request comments, which is exactly what a display-only entry looks
like. It is also `argoWorkflows.baseUrl` in
`platform-gitops/bootstrap/templates/mctl-platform/mctl-portal.yaml`, which
Backstage's backend fetches server-side on every workflow submission. Same
hostname, two roles, and the harmless one is the one you find first.

A host that belongs on the list and is missing does not fail loudly at the
edge: Super Bot Fight Mode challenges or blocks the call, and it surfaces as an
unexplained `403` inside whichever service made it. Reverting is one API call — put the
expression back to `(ip.src.asnum eq 24940)` — so widening first and diagnosing
afterwards is the right order if something breaks.

Several of these calls leave the cluster only to come straight back in through
the edge. Moving them to in-cluster DNS, which is what most of the codebase
already does, would shrink this list rather than manage it.

**Worker ownership (9).** `cloudflare_workers_route` is owned here; the script
and its eight runtime secrets stay in Wrangler — the seven original
bindings plus `TURNSTILE_SECRET_KEY`, added 2026-08-31. OpenTofu does not deploy Worker
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

## Zone settings

Zone settings were outside the #1089 import programme entirely — not considered
and deferred, simply never on the list — so all four zones ran on Cloudflare's
defaults until #1154. Two are now declared: `min_tls_version = "1.2"` and
`always_use_https = "on"`, in `modules/zone-baseline` for mctl.me and mctl.ru
and in `zones/mctl-ai/tls.tf` for mctl.ai.

Unlike DNS records and rulesets, a zone setting always exists. Cloudflare has
no notion of an unset setting, only of its default, so these import rather than
create, and the change shows as an update on the ones whose live value differs.
Each root's README records what its plan should print.

Two settings are deliberately left out:

- **`ssl`** stays `full` on every zone. It cannot be raised to `strict` while
  the origin presents `TRAEFIK DEFAULT CERT` for every name except the mctl.ai
  and mctl.ru apexes; strict would answer 526 for `platform.mctl.me` and every
  wildcard subdomain. Tracked in #1153, which continues the Origin CA and
  Authenticated Origin Pull thread from the origin section below.
- **`security_level`** is `medium` on mctl.ai and dmitriimashkov.com and `high`
  on mctl.me and mctl.ru. That difference looks accidental too, but unlike a
  TLS floor it changes how visitors are challenged, and nothing measured here
  says which value is right. Left alone rather than normalised on a guess.

`dmitriimashkov.com` has no root (decision 10) and so is not covered. Its
settings were set through the API instead. That is a standing exception rather
than drift: while the zone is intentionally unmanaged, anything applied to it
is applied by hand.

## The origin address in Git (#1119)

`91.98.10.188` stays in `zones/*/dns.tf`. It is `cloudflare_dns_record.content`
for the apex and wildcard of all three zones — the address *is* the record, and
OpenTofu has to know it. Sourcing it from a variable at plan time was considered
and rejected: it has been in the git history of a public repository since the
pilot, so hiding it now changes nothing an attacker can do. Decision taken
2026-09-09. The prose copy in `zones/mctl-ru/README.md` was removed, because a
value repeated for narration earns nothing.

**What makes the disclosure acceptable.** Publishing the address was only
dangerous because the origin answered for platform hostnames. It no longer
does: `infrastructure/k3s-preview/extra-manifests/cloudflare-origin-allowlist.yaml.tpl`
is a Traefik `Middleware` on the `websecure` entrypoint that refuses any request
whose source is outside Cloudflare's published ranges. A direct request with a
platform `Host` header gets `403`. Measured before the change: `app.mctl.ai` and
`ops.mctl.ai` both answered `200` to a `--resolve` straight at the origin.

**Why the control is in Traefik and not on the cloud firewall**, which is what
#1119 asked for. `91.98.10.188` is the Hetzner Cloud **Load Balancer** for
`svc/traefik`, not a node — only 80 and 443 answer on it; 22 and 6443 do not.
Hetzner cloud firewalls attach to servers, and hcloud-cloud-controller-manager
ignores `spec.loadBalancerSourceRanges`, so there is no firewall object in front
of this address to write a rule on. There is nothing to close on the nodes
either: kube-hetzner opens 80/443 there only when `using_klipper_lb` is true,
and it is false. The remediation as written was not implementable.

Traefik is also the stronger place for it. A pod dialling a public IP does not
traverse the cloud firewall — `kube.tf` says so, and `nodePublicCIDRs` in
`platform-gitops/helm-charts/tenant/values.yaml` is the compensating control —
but the load balancer's address is not in that list, because it is not a node.
Until this landed, a tenant pod could reach the origin's public address with an
arbitrary `Host` header and skip the edge. It now gets `403`: the pod egresses
through a node's public IP, so the load balancer hands Traefik a PROXY header
naming that address, which is not Cloudflare. A cloud-firewall allowlist could
not have closed that path. Nor could it have covered the load balancer's public
IPv6, which no `AAAA` record advertises and no firewall rule would reach.

**What it does not close.** Two things, both deliberate and both recorded rather
than implied.

*Another Cloudflare customer.* The allowlist trusts *all* of Cloudflare, so
someone can point their own zone at this origin and arrive from a legitimate
Cloudflare address, skipping this zone's WAF rules — the same breadth problem as
the `asnum eq 24940` bypass in decision 8, one layer down. Authenticated Origin
Pull (an mTLS client certificate the edge presents, which also survives
Cloudflare adding a range) or a secret header injected by this zone alone is
what closes it; a Cloudflare Tunnel removes the inbound listener altogether.
Both are strictly better and both are larger changes.

*A pod talking to Traefik directly.* The `websecure` entrypoint trusts the PROXY
protocol from `10.0.0.0/8`, which contains the pod CIDR `10.42.0.0/16` and the
service CIDR `10.43.0.0/16`. A pod connecting to Traefik's ClusterIP on `:8443`
can therefore supply its own PROXY header naming a Cloudflare source, and this
allowlist would honour it. That predates this change and applies to every
`ipAllowList` in the cluster, the `metrics-deny` middlewares included; narrowing
`trustedIPs` is dangerous enough to need its own rollout and is tracked in
gitops#1138. Raised by agy while reviewing #1135.

**The list of ranges goes stale.**
`.github/workflows/cloudflare-origin-allowlist.yml` re-fetches
`https://api.cloudflare.com/client/v4/ips` daily and fails, with a Telegram
notification, when the committed list differs. It does not reconcile: the fix
needs a `terraform.yml` apply against the cluster, which is manual.

## Credentials

Nothing is committed. CI reads:

- `R2_PLAN_ACCESS_KEY_ID` / `R2_PLAN_SECRET_ACCESS_KEY` — state access for plan
  and drift. **Object Read only, scoped to `mctl-cloudflare-state` alone.**
  Verified: `PutObject`, `DeleteObject`, and any other bucket — including
  `mctl-terraform-state` — all return `AccessDenied`. Both jobs pass
  `-lock=false`, because taking the state lock is itself a write.
- `R2_CF_STATE_ACCESS_KEY_ID` / `R2_CF_STATE_SECRET_ACCESS_KEY` — Object Read &
  Write on `mctl-cloudflare-state` alone, used by the backup workflow.
- `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` — writable on
  `mctl-terraform-state` **and** `mctl-etcd-snapshots`. Not a backup-only
  credential: `.github/workflows/terraform.yml` uses it as the state backend
  for `infrastructure/k3s-preview` and passes it into the cluster as
  `TF_VAR_etcd_s3_*`, so it has consumers outside this directory entirely.
  Never exposed to a job that plans unreviewed pull-request code.
- `CLOUDFLARE_API_TOKEN` — plan identity, **read-only across all zones**
  (`Cache Rules`, `DNS`, `Zone`, `Zone Settings`, `Zone WAF`, `Single Redirect`,
  `Page Rules`, `Access: Apps and Policies`, `Email Routing Rules`,
  `Workers Routes`, all `Read`). Verified read-only: a `POST` to create a DNS
  record is rejected. It is never given to `cloudflare-apply.yml`.

Everything above is a **repository** secret. `R2_CF_STATE_*` should not be:
it has exactly one consumer, `opentofu-state-backup.yml`, whose `state-backup`
environment currently protects the workflow file rather than the credential —
because a repository secret is readable by any workflow in the repository.
#1118 tracks moving it.

`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY` is **not** part of that move, however
similar it looks. `terraform.yml` reads the same pair with no `environment:` at
all, so scoping it to `state-backup` and dropping it from repository scope —
which is what the paragraph below prescribes for the apply credentials — would
leave that workflow with an empty `AWS_ACCESS_KEY_ID`, break `terraform init`
against R2, and fail every push touching `infrastructure/k3s-preview/**`.
Loudly rather than dangerously, but it is a different subsystem's deploy path,
broken by following this page. Moving it means giving `terraform.yml` an
environment first.

The apply credentials below are **environment secrets on `cloudflare-apply`,
not repository secrets**, for exactly that reason — storing them at repository
scope would let a branch carrying a new workflow read them while omitting
`environment:` entirely. Verify with
`gh api repos/mctlhq/mctl-gitops/environments/cloudflare-apply/secrets`; they
must not appear in `gh secret list`.

- `CF_APPLY_TOKEN_ACCOUNT`, `CF_APPLY_TOKEN_MCTL_RU`, `CF_APPLY_TOKEN_MCTL_ME`,
  `CF_APPLY_TOKEN_MCTL_AI` — apply identities, **one per root**, each scoped to
  that root's zone (or to Access for the account root) and to nothing else, so
  an apply against one zone cannot touch another. A root with no token here
  cannot be applied: the mapping in `cloudflare-apply.yml` is the allowlist.
- `R2_APPLY_ACCESS_KEY_ID` / `R2_APPLY_SECRET_ACCESS_KEY` — Object Read & Write
  on `mctl-cloudflare-state` alone, used by apply and by nothing else.
  Deliberately not the backup workflow's `R2_CF_STATE_*`: rotating or revoking
  one must not disturb the other.

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
| `cloudflare-apply.yml` | `workflow_dispatch` | the only workflow here that writes to Cloudflare. Two jobs. `plan` runs unprivileged with the read-only credentials and publishes the import/create/update/destroy table plus the full plan; `apply` waits on the `cloudflare-apply` environment's required reviewer, who is therefore approving a plan they can read rather than an intention. What crosses between them is a **digest** of the change set, not the plan — persisting `tfplan` as an artifact would leave a full description of the account downloadable afterwards, so `apply` re-plans and refuses if the digest no longer matches, which is what out-of-band drift between the two jobs looks like. Both jobs refuse a root that is not discovered, is listed in `.local-state-roots` (no remote state here, so its plan proposes creating everything it describes), or whose backend did not resolve to `s3`; `apply` additionally refuses a root with no write token mapped, since that mapping is the allowlist. A destroying plan is refused unless the run was dispatched with `allow_destroy` — asked for before its contents were known — checked once before the approval is spent and again on the plan actually being applied. Unlike plan and drift, `apply` never passes `-lock=false`: taking the state lock is itself a write, which is precisely why the other two cannot. Restricted to `main` by the environment's branch policy and by an `if` on the job, for the same reason as the backup workflow: `workflow_dispatch` accepts a ref. |
| `opentofu-state-backup.yml` | schedule | copies every state object in both state buckets to a dated prefix under `_backups/` in the same bucket — see the limitation noted above. Restricted to `main` by the `state-backup` environment's branch policy, since `workflow_dispatch` would otherwise run a rewritten copy of this file from any branch with the writable credential. |

Apply is manual on purpose. Merging a pull request does not change Cloudflare —
someone dispatches `cloudflare-apply.yml` against one named root, the same way a
production release is a Redeploy click rather than a merge. Drift stays
fail-closed: it reports, and a human decides whether the out-of-band change
should be imported or reverted. Neither workflow reconciles.

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
