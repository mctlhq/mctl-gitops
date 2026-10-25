# Every account-owned API token on the account, declared: name, permission
# groups and resources. check.tf compares this list with the live one on every
# plan and every nightly drift run, in both directions, so a token created,
# widened, narrowed, expired or revoked outside Git turns the run red.
#
# Only names and scopes are here. Token values never are: Cloudflare returns
# them once, at creation, and this root cannot read them.
#
# Tokens owned by a user rather than the account (My Profile -> API Tokens)
# are invisible to `GET /accounts/{id}/tokens` and so to this check. CI tokens
# must therefore be account-owned; see the README in this directory.
#
# To change a token: change it in the dashboard (Manage account -> Account API
# tokens), then update its entry here in the same pull request. The plan of
# this root is the proof that the two agree.

locals {
  account   = "com.cloudflare.api.account.${var.account_id}"
  r2_bucket = "com.cloudflare.edge.r2.bucket.${var.account_id}_default_"

  # The zone roots under ../zones; zone IDs are not secret.
  zone = {
    mctl_ai = "com.cloudflare.api.account.zone.86a90fe2fdfe87b9702842218b607f60"
    mctl_me = "com.cloudflare.api.account.zone.b0a1f8992b5d4221faf4541a9f75a329"
    mctl_ru = "com.cloudflare.api.account.zone.a7ec983a32a4b15097fbb80b1f5f6924"
    # A zone on this account that is not managed under ../zones. Only its ID
    # is recorded here; cert-manager issues one certificate in it.
    non_iac_1 = "com.cloudflare.api.account.zone.dec531554eb221a97e97c29ecf49f891"
  }

  # Permission group IDs, named as the dashboard names them. The check compares
  # IDs only: Cloudflare renames groups from time to time, and a rename does not
  # change what a token can do.
  pg = {
    account_api_tokens_read       = "eb56a6953c034b9d97dd838155666f06"
    account_settings_read         = "c1fde68c7bcc44588cbb6ddbc16d6480"
    access_apps_policies_read     = "7ea222f6d5064cfa89ea366d7c1fee89"
    access_apps_policies_write    = "1e13c5124ca64b72b1969a67e8829049"
    access_idps_read              = "9c35051ed89842839a637f81448d8c7c"
    access_orgs_idps_groups_write = "bfe0d8686a584fa680f4c53b5eb0de6d"
    access_service_tokens_write   = "a1c0fec57cf94af79479a6d827fa518c"
    access_zone_read              = "eb258a38ea634c86a0c89da6b27cb6b6"
    cache_settings_read           = "3245da1cf36c45c3847bb9b483c62f97"
    cache_settings_write          = "9ff81cbbe65c400b97d92c3c1033cab6"
    cf_agents_write               = "cb142f7fbc3540f0bade0cbe75f606dc"
    dns_read                      = "82e64a83756745bbbb1c9c2701bf816b"
    dns_write                     = "4755a26eedb94da69e1066d98aa820be"
    dynamic_url_redirects_read    = "d8e12db741544d1586ec1d6f5d3c7786"
    dynamic_url_redirects_write   = "74e1036f577a48528b78d2413b40538d"
    email_routing_addresses_read  = "5272e56105d04b5897466995b9bd4643"
    email_routing_addresses_write = "e4589eb09e63436686cd64252a3aebeb"
    email_routing_rules_read      = "1b600d9d8062443e986a973f097e728a"
    email_routing_rules_write     = "79b3ec0d10ce4148a8f8bdc0cc5f97f2"
    mcp_portals_read              = "b84a912ebb4a418888fec65f65c8ff3b"
    mcp_portals_write             = "db3d398df73946acb755c05b69edfc30"
    pages_write                   = "8d28297797f24fb8a0c332fe0866ec89"
    page_rules_read               = "b415b70a4fd1412886f164451f20405c"
    page_rules_write              = "ed07f6c337da4195b4e72a1fb2c6bcae"
    r2_bucket_item_read           = "6a018a9f2fc74eb6b293b0c548f38b39"
    r2_bucket_item_write          = "2efd5506f9c8494dacb1fa10a3e7d5b6"
    r2_data_catalog_write         = "d229766a2f7f4d299f20eaa8c9b1fde9"
    r2_sql_read                   = "f45430d92e2b4a6cb9f94f2594c141b8"
    r2_storage_read               = "b4992e1108244f5d8bfbd5744320c2e1"
    r2_storage_write              = "bf7481a1826f439697cb59a20b22293e"
    tunnel_read                   = "efea2ab8357b47888938f101ae5e053f"
    tunnel_write                  = "c07321b023e944ff818fec44d8203567"
    workers_ci_write              = "2e095cf436e2455fa62c9a9c2e18c478"
    workers_containers_write      = "bdbcd690c763475a985e8641dddc09f7"
    workers_kv_read               = "8b47d2786a534c08a1f94ee8f9f599ef"
    workers_kv_write              = "f7f0eda5697f475c90846e879bab8666"
    workers_observability_write   = "82c075da3f4647a2a03becd0fe240f8a"
    workers_routes_read           = "2072033d694d415a936eaeb94e6405b8"
    workers_routes_write          = "28f4b596e7d643029c524985477ae49a"
    workers_scripts_write         = "e086da7e2179491d91ee5f35b3ca210a"
    workers_tail_read             = "05880cd1bdc24d8bae0be2136972816b"
    zero_trust_write              = "b33f02c6f7284e05a6f20741c0bb0567"
    zone_read                     = "c8fed203ed3043cba015a93ad1616f1f"
    zone_settings_read            = "517b21aee92c4d89936c976ba6e4be55"
    zone_settings_write           = "3030687196b94b638145a3953da2b699"
    zone_waf_read                 = "dbc512b354774852af2b5a5f4ba3d470"
    zone_waf_write                = "fb6778dc191143babbfaa57993f1d275"
  }

  # The apply identity of one zone root (#1111): everything that root manages,
  # on that zone alone.
  zone_apply_groups = [
    local.pg.cache_settings_write,
    local.pg.dns_write,
    local.pg.dynamic_url_redirects_write,
    local.pg.email_routing_rules_write,
    local.pg.page_rules_write,
    local.pg.workers_routes_write,
    local.pg.zone_read,
    local.pg.zone_settings_write,
    local.pg.zone_waf_write,
  ]

  # One entry per token. Names are not unique on Cloudflare (the dashboard's
  # R2 "Create API token" names every token "R2 Account Token"), so entries are
  # compared as a multiset: two identical live tokens need two entries here.
  tokens = [
    # --- CI identities of this repository -----------------------------------

    # CF_ACCOUNT_READ_TOKEN: plan and drift of ../account and of this root.
    {
      name = "mctl-gitops-plan-account (CF_ACCOUNT_READ_TOKEN)"
      policies = [{
        permission_groups = [
          local.pg.access_apps_policies_read,
          local.pg.access_idps_read,
          local.pg.account_api_tokens_read,
          local.pg.email_routing_addresses_read,
          local.pg.r2_storage_read,
          local.pg.tunnel_read,
          local.pg.workers_kv_read,
        ]
        resources = { (local.account) = "*" }
      }]
    },
    # CLOUDFLARE_API_TOKEN: plan and drift of ../zones/*. Read-only, on the
    # three IaC zones listed flat (the user-owned token it replaced had every
    # zone on the account).
    {
      name = "mctl-gitops-plan-zones (CLOUDFLARE_API_TOKEN)"
      policies = [{
        permission_groups = [
          local.pg.access_zone_read,
          local.pg.cache_settings_read,
          local.pg.dns_read,
          local.pg.dynamic_url_redirects_read,
          local.pg.email_routing_rules_read,
          local.pg.page_rules_read,
          local.pg.workers_routes_read,
          local.pg.zone_read,
          local.pg.zone_settings_read,
          local.pg.zone_waf_read,
        ]
        resources = {
          (local.zone.mctl_ai) = "*"
          (local.zone.mctl_me) = "*"
          (local.zone.mctl_ru) = "*"
        }
      }]
    },
    # CF_PORTAL_READ_TOKEN: plan and drift of ../portal, and the hourly
    # cloudflare-portal-health read.
    {
      name     = "mctl-gitops-portal-read (CF_PORTAL_READ_TOKEN)"
      policies = [{ permission_groups = [local.pg.mcp_portals_read], resources = { (local.account) = "*" } }]
    },
    # CF_APPLY_TOKEN_PORTAL (environment cloudflare-apply): apply of ../portal
    # and cloudflare-portal-health's re-snapshot job.
    {
      name     = "mctl-gitops-portal-apply (CF_APPLY_TOKEN_PORTAL)"
      policies = [{ permission_groups = [local.pg.mcp_portals_write], resources = { (local.account) = "*" } }]
    },
    # CF_APPLY_TOKEN_ACCOUNT: apply of ../account.
    {
      name = "mctl-gitops-apply-account (cloudflare-iac #1111)"
      policies = [{
        permission_groups = [
          local.pg.access_apps_policies_write,
          local.pg.access_orgs_idps_groups_write,
          local.pg.access_service_tokens_write,
          local.pg.email_routing_addresses_write,
          local.pg.r2_storage_write,
          local.pg.tunnel_write,
          local.pg.workers_kv_write,
          local.pg.zero_trust_write,
        ]
        resources = { (local.account) = "*" }
      }]
    },
    # CF_APPLY_TOKEN_MCTL_AI / _MCTL_ME / _MCTL_RU: apply of ../zones/*.
    {
      name     = "mctl-gitops-apply-mctl-ai (cloudflare-iac #1111)"
      policies = [{ permission_groups = local.zone_apply_groups, resources = { (local.zone.mctl_ai) = "*" } }]
    },
    {
      name     = "mctl-gitops-apply-mctl-me (cloudflare-iac #1111)"
      policies = [{ permission_groups = local.zone_apply_groups, resources = { (local.zone.mctl_me) = "*" } }]
    },
    {
      name     = "mctl-gitops-apply-mctl-ru (cloudflare-iac #1111)"
      policies = [{ permission_groups = local.zone_apply_groups, resources = { (local.zone.mctl_ru) = "*" } }]
    },
    # State of these roots in R2 (S3 credentials derived from the token):
    # R2_APPLY_* (apply), R2_PLAN_* (plan and drift), R2_CF_STATE_* (backup).
    # The two "ctl-cloudflare-state-*" names below are spelled as they are on
    # Cloudflare, without the leading "m". Renaming the live tokens fixes that;
    # the entries must change in the same pull request.
    {
      name     = "mctl-cloudflare-state-apply-rw (cloudflare-iac #1111)"
      policies = [{ permission_groups = [local.pg.r2_storage_write], resources = { "${local.r2_bucket}mctl-cloudflare-state" = "*" } }]
    },
    {
      name     = "ctl-cloudflare-state-plan-readonly (gitops #1093)"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_read], resources = { "${local.r2_bucket}mctl-cloudflare-state" = "*" } }]
    },
    {
      name     = "ctl-cloudflare-state-backup-rw (gitops #1093)"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}mctl-cloudflare-state" = "*" } }]
    },

    # --- Other R2 state and backup buckets -----------------------------------

    {
      name     = "mctl-terraform-state"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}mctl-terraform-state" = "*" } }]
    },
    {
      name     = "mctl-terraform-state-local"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}mctl-terraform-state" = "*" } }]
    },
    {
      name     = "mctl-terraform-state-vault"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}mctl-terraform-state" = "*" } }]
    },
    {
      name     = "mctl-terraform-state-plan-readonly (gitops #1093)"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_read], resources = { "${local.r2_bucket}mctl-terraform-state" = "*" } }]
    },
    {
      name     = "mctl-etcd-snapshots-k3s"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}mctl-etcd-snapshots" = "*" } }]
    },
    {
      name     = "mctl-ai-opentofu-state-r2-token"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}mctl-ai-opentofu-state" = "*" } }]
    },
    {
      name     = "forgejo-backup (mctl-gitops forgejo-backup CronJob)"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}forgejo-backup" = "*" } }]
    },
    {
      name     = "erpact-backup (erpact backup CronJob)"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}erpact-backups" = "*" } }]
    },
    {
      name     = "claude-remote-state (labs claude-remote)"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}claude-remote-state" = "*" } }]
    },
    {
      name     = "tempo-traces (observability-eval Tempo, bucket-scoped)"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}tempo-traces" = "*" } }]
    },
    {
      # Created 2026-10-24 with the rules.mctl.ai launch (gitops#2131); keys
      # live in Vault teams/labs/mctl-rules.
      name     = "mctl-rules-artifacts (labs mctl-rules app)"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}mctl-rules-artifacts" = "*" } }]
    },

    # --- Created from the dashboard's R2 page, all named "R2 Account Token" ---
    # Inventoried as found on 2026-10-16. Three of them can write every bucket
    # on the account; which consumer holds each is not recorded anywhere yet.

    {
      name     = "R2 Account Token"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}academy-source-snapshots" = "*" } }]
    },
    {
      name     = "R2 Account Token"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}vault-backup" = "*" } }]
    },
    {
      name     = "R2 Account Token"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { "${local.r2_bucket}vault-backup" = "*" } }]
    },
    {
      name     = "R2 Account Token"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { (local.account) = "*" } }]
    },
    {
      name     = "R2 Account Token"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { (local.account) = "*" } }]
    },
    {
      name     = "R2 Account Token"
      policies = [{ permission_groups = [local.pg.r2_bucket_item_write], resources = { (local.account) = "*" } }]
    },
    {
      name = "R2 Account Token"
      policies = [{
        permission_groups = [local.pg.r2_data_catalog_write, local.pg.r2_sql_read, local.pg.r2_storage_write]
        resources         = { (local.account) = "*" }
      }]
    },

    # --- Other ---------------------------------------------------------------

    {
      name = "pelican-catalog-worker CI deploy"
      policies = [{
        permission_groups = [
          local.pg.account_settings_read,
          local.pg.cf_agents_write,
          local.pg.pages_write,
          local.pg.r2_storage_write,
          local.pg.workers_ci_write,
          local.pg.workers_containers_write,
          local.pg.workers_kv_write,
          local.pg.workers_observability_write,
          local.pg.workers_scripts_write,
          local.pg.workers_tail_read,
        ]
        resources = { (local.account) = "*" }
      }]
    },
    # cert-manager's DNS-01 token on k3s-preview (Secret
    # cert-manager/cloudflare-api-token, from Vault
    # platform/cloudflare/cert-manager-dns01 via ExternalSecret). The zones
    # are listed flat so that check.tf verifies the scope; these four are the
    # ones the ClusterIssuers' certificates name. It replaces "Edit zone DNS"
    # below.
    {
      name = "cert-manager-dns01 (k3s-preview)"
      policies = [{
        permission_groups = [local.pg.dns_write]
        resources = {
          (local.zone.mctl_ai)   = "*"
          (local.zone.mctl_me)   = "*"
          (local.zone.mctl_ru)   = "*"
          (local.zone.non_iac_1) = "*"
        }
      }]
    },
    # The token cert-manager used until the one above: DNS Write on every
    # zone of the account (the API nests `com.cloudflare.api.account.zone.* =
    # *` under the account). The provider cannot represent a nested resource
    # map and returns `resources = null` for it, so this entry declares null
    # and the token's zone scope is NOT verified: only its name, status and
    # permission groups are. check.tf reports that on every run rather than
    # letting it pass as a match. It is deleted, and this entry with it, once
    # cert-manager has issued a certificate with the replacement.
    {
      name = "Edit zone DNS"
      policies = [{
        permission_groups = [local.pg.dns_write]
        resources         = null
      }]
    },
  ]
}
