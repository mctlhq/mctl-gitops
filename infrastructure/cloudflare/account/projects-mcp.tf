# projects.mctl.ai — the MCP connector customers use to ask about their product.
#
# Cloudflare Access is the OAuth authorization server for this application, and
# the origin is only a resource server. A customer adds https://projects.mctl.ai/mcp
# as a custom connector in their own Claude; Access runs the OAuth flow, registers
# the client itself through dynamic client registration, and forwards the request
# with `Cf-Access-Jwt-Assertion`. The server verifies that header against
# https://<team>.cloudflareaccess.com/cdn-cgi/access/certs with this application's
# `aud`, and holds no OAuth code of its own.
#
# This is deliberately not the other mechanism. Access for SaaS with OIDC would
# make the server its own authorization server and hand it a bearer token instead
# — a different trust path, and 2000 lines of code this one does not have.
#
# The MCP portal is not on a customer's path at all. An application reached by its
# own URL is reached by its own policy, so there is nothing to bypass.

variable "projects_mcp_grants_file" {
  description = <<-EOT
    grants.yaml — the single list of who may reach projects.mctl.ai and at what
    level. Moves to platform-gitops/services/labs/projects-mcp/grants.yaml when
    the service is deployed and the chart mounts it; this variable moves with it
    so both sides keep reading one file.
  EOT
  type        = string
  default     = "projects-mcp-grants.yaml"
}

variable "projects_mcp_idp_ids" {
  description = <<-EOT
    The identity providers Access offers on the login page. Left null, the Google
    provider and the one-time PIN provider configured in this account are
    discovered below, and a precondition requires exactly one of each. Set this
    to name them outright if that ever stops being true.
  EOT
  type        = list(string)
  default     = null
}

data "cloudflare_zero_trust_access_identity_providers" "all" {
  account_id = var.account_id
}

locals {
  projects_mcp_grants = yamldecode(file("${path.module}/${var.projects_mcp_grants_file}"))

  # Addresses are lowercased here because they are compared as strings on both
  # sides: Access matches the claim, and the server looks the caller up in this
  # same file. One capital letter in an address would otherwise let a person
  # through Cloudflare and leave them with no grant on the other side.
  projects_mcp_emails = sort(distinct([
    for grant in local.projects_mcp_grants.grants : lower(grant.email)
  ]))

  projects_mcp_google_idps = [
    for idp in data.cloudflare_zero_trust_access_identity_providers.all.result :
    idp.id if idp.type == "google" || idp.type == "google-apps"
  ]

  # The one-time PIN provider mails a code to the address being signed in with.
  # It is here because a customer's work address is not necessarily a Google
  # account: the university side signs in with uni.lu addresses, and without
  # this they would be admitted by the policy and unable to log in at all.
  projects_mcp_otp_idps = [
    for idp in data.cloudflare_zero_trust_access_identity_providers.all.result :
    idp.id if idp.type == "onetimepin"
  ]

  # The override wins when it is set; otherwise both providers come from the
  # lookups above. The "exactly one of each" rule is a precondition on the
  # resource rather than `one()` here: `one()` raises while the expression is
  # evaluated, which no override can prevent, so the escape hatch would not
  # work in the very case it exists for.
  projects_mcp_idp_ids = var.projects_mcp_idp_ids != null ? var.projects_mcp_idp_ids : concat(
    local.projects_mcp_google_idps,
    local.projects_mcp_otp_idps,
  )
}

resource "cloudflare_zero_trust_access_application" "projects_mcp" {
  account_id = var.account_id
  name       = "mctl Projects (projects.mctl.ai)"
  type       = "self_hosted"

  destinations = [
    {
      type = "public"
      uri  = "projects.mctl.ai"
    },
  ]

  # No DNS record is needed: `A *.mctl.ai` is proxied and already resolves this
  # host to the cluster origin (zones/mctl-ai/dns.tf). Access sits in front of it
  # because the record is proxied, which is what makes this application effective.

  allowed_idps = local.projects_mcp_idp_ids

  # Two providers means the person picks one, so the skip-the-picker setting is
  # off: Cloudflare only honours it when exactly one provider is allowed.
  auto_redirect_to_identity = false

  # An MCP client is not a browser and has nobody to show a launcher to.
  app_launcher_visible = false
  session_duration     = "24h"

  # Access as the OAuth authorization server for this application.
  oauth_configuration = {
    enabled = true

    dynamic_client_registration = {
      enabled = true

      # Claude registers itself through DCR, and these are the callbacks it
      # registers. A different client — another vendor's, or a second Claude
      # surface — adds its own URI here; nothing else about it is configured.
      allowed_uris = [
        "https://claude.ai/api/mcp/auth_callback",
        "https://claude.com/api/mcp/auth_callback",
      ]

      # Claude Desktop and Claude Code complete the flow on a loopback port that
      # is chosen per run and cannot be listed in advance.
      allow_any_on_loopback  = true
      allow_any_on_localhost = true
    }

    grant = {
      access_token_lifetime = "1h"
      session_duration      = "24h"
    }
  }

  # A missing or duplicated provider needs a person to decide: silently taking
  # the first would put the login page in front of the wrong directory. Setting
  # projects_mcp_idp_ids names the providers outright and skips the check.
  lifecycle {
    precondition {
      condition = var.projects_mcp_idp_ids != null || (
        length(local.projects_mcp_google_idps) == 1 &&
        length(local.projects_mcp_otp_idps) == 1
      )
      error_message = join(" ", [
        "Expected exactly one Google and one one-time-PIN identity provider in this account;",
        "found ${length(local.projects_mcp_google_idps)} and ${length(local.projects_mcp_otp_idps)}.",
        "Set projects_mcp_idp_ids to name them explicitly.",
      ])
    }
  }

  policies = [
    {
      name       = "projects-mcp-named-people"
      decision   = "allow"
      precedence = 1

      # Every address in grants.yaml, and nobody else. A person removed from
      # that file stops getting past Cloudflare on the next apply, whatever the
      # server would have said about them.
      include = [
        for email in local.projects_mcp_emails : { email = { email = email } }
      ]
    },
  ]
}

# The AUD tag the server verifies every assertion against. It is not a secret —
# it identifies the application — and the server reads it as ACCESS_AUD.
output "projects_mcp_aud" {
  description = "ACCESS_AUD for projects-mcp."
  value       = cloudflare_zero_trust_access_application.projects_mcp.aud
}

output "projects_mcp_emails" {
  description = "Addresses the Access policy admits, as read from grants.yaml."
  value       = local.projects_mcp_emails
}
