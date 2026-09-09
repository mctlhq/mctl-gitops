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
`mctl-terraform-state/_backups/<UTC timestamp>/`, keeping 30 days.

Note the snapshots sit in the same bucket as the originals. The R2 credential
available to CI is scoped to `mctl-terraform-state` and cannot write anywhere
else, so this protects against a bad apply or an accidental `state rm` but not
against losing the bucket. Treat "the bucket is gone" as a different, harder
incident than the one this runbook covers.

Losing state does not destroy infrastructure, but it does mean OpenTofu no
longer knows the infrastructure exists — the next plan proposes creating
everything from scratch. **Never apply such a plan.** Restore first.

## Prerequisites

```sh
export AWS_ACCESS_KEY_ID=…        # R2_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY=…    # R2_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION=auto
export R2=https://6a09f637d20e1f66a8e9d45ebe778058.r2.cloudflarestorage.com
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
KEY=cloudflare/zones/mctl-ru/terraform.tfstate

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

```sh
cd infrastructure/cloudflare/zones/mctl-ru
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
| 2026-09-09 | — (snapshot side only) | First snapshot taken manually while writing this workflow: 2 objects copied to `_backups/2026-09-09T01-32-51Z/`, and `k3s-preview/cluster-bootstrap/terraform.tfstate` parsed back cleanly (`serial=1`, lineage intact, 1 resource). The **restore** half — steps 3 and 4 — has not been drilled yet. |
