# R2 buckets of the mctl platform.
#
# Every bucket below was created by hand (dashboard, wrangler or the API) and
# stayed unmanaged, so a deleted bucket or a changed lifecycle rule was
# invisible to cloudflare-drift. They are adopted here import-only: name,
# location and storage class are the live values, read on 2026-10-10 from
# GET /accounts/{account_id}/r2/buckets/{name}. Location is a creation-time
# hint and cannot be changed, so it is recorded to keep a re-create from
# landing the bucket elsewhere, not to move anything.
#
# Deliberately out of scope:
#   - pelican-catalog and the EU-jurisdiction livri-backups bucket belong to
#     other projects (pelican, Livri) that manage their own storage.
#
# Every bucket is prevent_destroy: most of them hold backups or OpenTofu
# state (mctl-cloudflare-state is this root's own backend), and losing one
# to a refactor of this file must take a deliberate edit, not a plan.
locals {
  r2_buckets = {
    "academy-source-snapshots" = "EEUR"
    "argo-workflows-logs"      = "ENAM"
    "erpact-backups"           = "WEUR"
    "forgejo-backup"           = "ENAM"
    "loki"                     = "ENAM"
    "mctl-ai-opentofu-state"   = "WEUR"
    "mctl-cloudflare-state"    = "ENAM"
    "mctl-etcd-snapshots"      = "ENAM"
    "mctl-rules-artifacts"     = "ENAM"
    "mctl-terraform-state"     = "EEUR"
    "tempo-traces"             = "EEUR"
    "vault-backup"             = "EEUR"
  }
}

import {
  for_each = local.r2_buckets
  to       = cloudflare_r2_bucket.this[each.key]
  id       = "${var.account_id}/${each.key}/default"
}

resource "cloudflare_r2_bucket" "this" {
  for_each = local.r2_buckets

  account_id    = var.account_id
  name          = each.key
  location      = each.value
  jurisdiction  = "default"
  storage_class = "Standard"

  lifecycle {
    prevent_destroy = true
  }
}

# Lifecycle configuration, only for the buckets whose rules carry intent
# beyond Cloudflare's default 7-day multipart abort. The provider cannot
# import this resource; creating it is a PUT of the whole configuration, so
# the first apply rewrites each bucket with exactly the rules it already has
# (live values, read on 2026-10-10). The default multipart rule is kept
# verbatim where it exists, because a PUT without it would remove it.
#
# Retention is a backstop, not the primary limit: Loki and Tempo enforce
# their own retention, this only catches objects they never clean up.
locals {
  default_multipart_abort_rule = {
    id         = "Default Multipart Abort Rule"
    enabled    = true
    conditions = { prefix = "" }
    abort_multipart_uploads_transition = {
      condition = { type = "Age", max_age = 604800 } # 7 days
    }
  }
}

resource "cloudflare_r2_bucket_lifecycle" "argo_workflows_logs" {
  account_id  = var.account_id
  bucket_name = cloudflare_r2_bucket.this["argo-workflows-logs"].name

  rules = [
    local.default_multipart_abort_rule,
    {
      id         = "expire-after-30-days"
      enabled    = true
      conditions = { prefix = "" }
      delete_objects_transition = {
        condition = { type = "Age", max_age = 2592000 } # 30 days
      }
    },
  ]
}

resource "cloudflare_r2_bucket_lifecycle" "loki" {
  account_id  = var.account_id
  bucket_name = cloudflare_r2_bucket.this["loki"].name

  rules = [
    local.default_multipart_abort_rule,
    {
      id         = "backstop-expire-after-60-days"
      enabled    = true
      conditions = { prefix = "" }
      delete_objects_transition = {
        condition = { type = "Age", max_age = 5184000 } # 60 days
      }
    },
  ]
}

resource "cloudflare_r2_bucket_lifecycle" "tempo_traces" {
  account_id  = var.account_id
  bucket_name = cloudflare_r2_bucket.this["tempo-traces"].name

  rules = [
    {
      id         = "backstop-expire-after-30-days"
      enabled    = true
      conditions = { prefix = "" }
      delete_objects_transition = {
        condition = { type = "Age", max_age = 2592000 } # 30 days
      }
      abort_multipart_uploads_transition = {
        condition = { type = "Age", max_age = 86400 } # 1 day
      }
    },
  ]
}
