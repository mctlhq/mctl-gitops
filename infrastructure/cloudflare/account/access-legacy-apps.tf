# Access applications and reusable policies created by hand before this root
# existed, adopted so that cloudflare-drift sees them (#1089 decided their
# fate on 2026-09-09; this is the import). Every field is the live value, read
# on 2026-10-10 from GET /accounts/{account_id}/access/apps/{id} and
# /access/policies/{id}, with ONE deliberate change at import, called out
# below on `media`. Since then both applications moved from Google to ZITADEL
# (see "Applications" below).
#
# Out of scope here: the tunnel, DNS records and cache ruleset behind
# jellyfin.mctl.ai and media.mctl.ai belong to mashkovd/mac-mini-infra (see
# the ownership table in ../README.md). Only the Access objects in front of
# them live in this root, and nothing in that repository manages them.
#
# Ids are literal for the reason given in portal-mcp-apps-adopted.tf.

# --- Reusable policies -------------------------------------------------------

# Admits any identity the account's Google provider asserts
# (var.projects_mcp_google_idp_id, declared in projects-mcp.tf). Used by the
# App Launcher; the applications below no longer reference it. Who that is, is decided by the
# Google provider, not by this policy: the include names a login method,
# not a list of users.
import {
  to = cloudflare_zero_trust_access_policy.google
  id = "${var.account_id}/f4a14417-6d7e-44b8-8b6c-a957b3302e62"
}

resource "cloudflare_zero_trust_access_policy" "google" {
  account_id       = var.account_id
  name             = "google"
  decision         = "allow"
  session_duration = "24h"

  include = [
    { login_method = { id = var.projects_mcp_google_idp_id } },
  ]

  # Stored by the dashboard on creation; meaningless on these self_hosted
  # applications, kept so the import plans no change.
  connection_rules = {
    rdp = {
      allowed_clipboard_local_to_remote_formats = ["text"]
      allowed_clipboard_remote_to_local_formats = ["text"]
    }
  }
}

# Lets seerrsense (services/labs/seerrsense) reach Seerr at media.mctl.ai
# with the CF-Access-Client-* headers. The service token itself
# (82bfc58a-...) stays unmanaged: its secret exists only in Vault, and an
# imported token without one would plan a replacement.
import {
  to = cloudflare_zero_trust_access_policy.seerrsense_service_token
  id = "${var.account_id}/bb2e4dfd-1213-490d-81b7-37cbc869537b"
}

resource "cloudflare_zero_trust_access_policy" "seerrsense_service_token" {
  account_id = var.account_id
  name       = "seerrsense service token"
  decision   = "non_identity"

  include = [
    { service_token = { token_id = "82bfc58a-3c9f-496e-8c76-8ef744ede8d5" } },
  ]
}

# --- Applications --------------------------------------------------------------
#
# Both applications admit ZITADEL logins only, through the shared
# `zitadel_access_role` policy (portal-zitadel.tf): a user gets past ZITADEL
# only with the `access` role of the `Cloudflare Access` project, which the
# platform admins hold. They used to admit the `google` policy above, i.e. any
# Google account, which made both effectively public behind a login. Access
# request logs for the 90 days before the switch (2026-10-10) show no human
# sign-in to either application, only seerrsense's service token on `media`.
# There is no break-glass here, unlike the MCP portal: if ZITADEL is down,
# media and Jellyfin are unreachable from outside, which is acceptable.

# Seerr (Overseerr) at media.mctl.ai, #1089 decision 1.
#
# THE ONE CHANGE AT IMPORT: live, this application points at
# 1media.mctl.ai -- moved there on 2026-09-12 as a test and never moved back,
# which left media.mctl.ai itself without Access in front of it. The import
# plans an in-place update back to media.mctl.ai. seerrsense already sends
# the service-token headers (CF_ACCESS_CLIENT_ID/SECRET in its values.yaml),
# so it keeps working once the gate is back.
import {
  to = cloudflare_zero_trust_access_application.media
  id = "accounts/${var.account_id}/a7a99131-76f3-4527-a109-825e4dcb27a3"
}

resource "cloudflare_zero_trust_access_application" "media" {
  account_id = var.account_id
  name       = "media"
  type       = "self_hosted"
  domain     = "media.mctl.ai"

  destinations = [
    {
      type = "public"
      uri  = "media.mctl.ai"
    },
  ]

  # ZITADEL only (see the note above `media`): the Google door admitted any
  # Google account at all.
  allowed_idps               = [cloudflare_zero_trust_access_identity_provider.zitadel.id]
  app_launcher_visible       = true
  auto_redirect_to_identity  = false
  session_duration           = "24h"
  enable_binding_cookie      = false
  http_only_cookie_attribute = false
  options_preflight_bypass   = false

  policies = [
    { id = cloudflare_zero_trust_access_policy.zitadel_access_role.id, precedence = 1 },
    { id = cloudflare_zero_trust_access_policy.seerrsense_service_token.id, precedence = 2 },
  ]
}

import {
  to = cloudflare_zero_trust_access_application.jellyfin
  id = "accounts/${var.account_id}/72064444-3c34-4bff-adaf-eb5058a0bafc"
}

resource "cloudflare_zero_trust_access_application" "jellyfin" {
  account_id = var.account_id
  name       = "jellyfin"
  type       = "self_hosted"
  domain     = "jellyfin.mctl.ai"

  destinations = [
    {
      type = "public"
      uri  = "jellyfin.mctl.ai"
    },
  ]

  allowed_idps               = [cloudflare_zero_trust_access_identity_provider.zitadel.id]
  app_launcher_visible       = true
  auto_redirect_to_identity  = false
  session_duration           = "24h"
  enable_binding_cookie      = false
  http_only_cookie_attribute = false
  options_preflight_bypass   = false

  policies = [
    { id = cloudflare_zero_trust_access_policy.zitadel_access_role.id, precedence = 1 },
  ]
}
