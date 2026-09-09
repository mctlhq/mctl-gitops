# Runbook — restore OpenTofu/Terraform state from backup

## Why this exists

State for the IaC roots in this repository lives in two R2 buckets:
`mctl-cloudflare-state` (the Cloudflare roots) and `mctl-terraform-state`
(`k3s-preview`). They are separate because R2 tokens scope to a bucket rather
than a prefix, and the k3s state contains an OpenSSH private key and kubeconfig
credentials that Cloudflare CI has no business being able to read. **R2 does not support object versioning** — the API
returns `10015: No route matches this url` for
`/accounts/{id}/r2/buckets/{bucket}/versioning`, and the feature is absent from
the product. The usual S3 safety net does not apply, so a deleted or corrupted
state file is unrecoverable unless a copy exists elsewhere.

`.github/workflows/opentofu-state-backup.yml` makes that copy daily into
`<bucket>/_backups/<UTC timestamp>/` for both buckets, keeping 30 days.

Note the snapshots sit in the same bucket as their originals — each backup
credential is scoped to one bucket and cannot write anywhere else. So this
protects against a bad apply or an accidental `state rm`, but not against
losing a bucket. Treat "the bucket is gone" as a different, harder incident
than the one this runbook covers.

Losing state does not destroy infrastructure, but it does mean OpenTofu no
longer knows the infrastructure exists. What the next plan proposes depends on
the root: one without `import` blocks proposes **creating everything from
scratch**, which would duplicate or collide with what is already live. A root
that still carries its `import` blocks proposes re-importing instead, which
looks reassuringly harmless — do not read that as "state loss is fine".
**Never apply a plan you reached by losing state.** Restore first.

## Prerequisites

```sh
export AWS_ACCESS_KEY_ID=…        # see below for which credential
export AWS_SECRET_ACCESS_KEY=…
export AWS_DEFAULT_REGION=auto
export R2=https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com

# Required, not optional. R2 rejects the checksum headers recent AWS CLI
# versions send by default; without these, the cp/ls commands below fail with
# an opaque error at the worst possible moment. The backup workflow sets the
# same two variables for the same reason.
export AWS_REQUEST_CHECKSUM_CALCULATION=when_required
export AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
```

Credentials are in Vault: `secret/platform/terraform/r2-state` for
`mctl-terraform-state`, `secret/platform/terraform/r2-cloudflare-state-rw` for
`mctl-cloudflare-state`. The `-readonly` entries cannot restore — they are what
CI uses to plan.

## 1. Find the snapshot

```sh
aws s3 ls s3://mctl-cloudflare-state/_backups/ --endpoint-url "$R2"   # or mctl-terraform-state
```

Directories are named by UTC timestamp, newest last. Pick the most recent one
from *before* the incident — not simply the newest, which may already contain
the damage.

## 2. Inspect before overwriting

```sh
SNAP=2026-09-09T03-30-00Z
KEY=cloudflare/account/terraform.tfstate   # a key that actually exists

aws s3 cp "s3://mctl-cloudflare-state/_backups/$SNAP/$KEY" ./restore.tfstate \
  --endpoint-url "$R2"

jq '{serial, lineage, resources: [.resources[].type] | unique}' restore.tfstate
```

Check `serial` and `lineage`. A lineage that differs from the live state means
the two files describe different histories — stop and work out why before going
further.

## 3. Restore

```sh
aws s3 cp ./restore.tfstate "s3://mctl-cloudflare-state/$KEY" --endpoint-url "$R2"
```

If a stale lock blocks the next operation, remove it only after confirming no
apply is running:

```sh
aws s3 rm "s3://mctl-cloudflare-state/$KEY.tflock" --endpoint-url "$R2"
```

## 4. Verify — this step is the whole point

Derive the directory from the key you just restored, rather than pasting a path
— the point is to verify *what was restored*, not a root that happens to be
mentioned in an example:

```sh
cd "infrastructure/${KEY%/terraform.tfstate}"   # e.g. infrastructure/cloudflare/account
tofu init -reconfigure
tofu plan
```

Expected: **`No changes.`**

A plan proposing to create resources that already exist means the restore did
not take, or the wrong snapshot was chosen. Go back to step 1. Do not apply.

## Drill

Run this against a non-production root at least once so the procedure is known
to work rather than merely written down. `.github#47` treats an untested restore
as no restore: until the drill has happened, Git-only operation is not
authoritative.

Record the drill date and outcome here:

| Date | Root | Outcome |
| --- | --- | --- |
| 2026-09-09 | snapshot side | 2 objects copied to `_backups/2026-09-09T01-32-51Z/`; `k3s-preview/cluster-bootstrap/terraform.tfstate` parsed back cleanly (`serial=1`, lineage intact). |
| 2026-09-09 | full restore, `mctl.ru` config on a scratch key | **Passed.** Ran end to end against a `_drill/mctl-ru/terraform.tfstate` key rather than live state, so a failed drill could not have damaged anything: imported 2 records (`serial=1`, `lineage=9cdd58de…`), snapshotted, **deleted the live key**, confirmed the loss was real (`head_object` gone, plan no longer clean), restored from the snapshot, and got `No changes.` Scratch keys deleted afterwards; the bucket is empty again. Cloudflare itself was never mutated — every step was import or plan. |
