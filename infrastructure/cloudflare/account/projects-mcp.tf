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

variable "projects_mcp_service_values" {
  description = <<-EOT
    The service's Helm values, which carry the grants list. Resolved relative to
    this root, not to the repository.

    The list lives there rather than here because the chart mounts it into the
    pod from a ConfigMap, and base-service renders ConfigMap content inline from
    values. Reading it back out is a little awkward and buys the thing that
    matters: one list. An address Cloudflare admits is an address the server
    knows, because both sides read the same lines.
  EOT
  type        = string
  default     = "../../../platform-gitops/services/labs/projects-mcp/values.yaml"
}

# The identity provider Access offers on the login page, named outright.
#
# A data source would have been nicer to read, and was tried: the plan identity
# for this root is read-only and deliberately does not carry
# `Access: Organizations, Identity Providers, and Groups Read`, so the lookup
# came back with an empty list rather than an error and the plan proposed an
# application with no providers at all. A wrong answer that looks like an answer
# is worse than a pasted UUID, and widening a read-only plan token to see the
# account's identity configuration is the wrong way to avoid one.
#
# The value is not a secret; it identifies an object in this account. Confirm
# with `GET /accounts/{account_id}/access/identity_providers`.

variable "projects_mcp_google_idp_id" {
  description = "The Google identity provider in this account."
  type        = string
  default     = "bb581a63-79d5-477b-af43-dd5cd07ff12b"
}

locals {
  projects_mcp_values = yamldecode(file("${path.module}/${var.projects_mcp_service_values}"))

  # The ConfigMap entry is a string of YAML inside YAML, so it is decoded twice.
  projects_mcp_grants = yamldecode(
    local.projects_mcp_values.configMaps["projects-mcp-grants"]["grants.yaml"]
  )

  # Addresses are lowercased here because they are compared as strings on both
  # sides: Access matches the claim, and the server looks the caller up in this
  # same file. One capital letter in an address would otherwise let a person
  # through Cloudflare and leave them with no grant on the other side.
  projects_mcp_emails = sort(distinct([
    for grant in local.projects_mcp_grants.grants : lower(grant.email)
  ]))
}

resource "cloudflare_zero_trust_access_application" "projects_mcp" {
  account_id = var.account_id
  name       = "mctl Projects (projects.mctl.ai)"
  type       = "self_hosted"

  # Both, deliberately. `destinations` is the current field and is what Access
  # matches on; `domain` is the primary hostname the API and the dashboard show
  # for the application, and leaving it to be inferred is not something to find
  # out during an apply.
  domain = "projects.mctl.ai"

  destinations = [
    {
      type = "public"
      uri  = "projects.mctl.ai"
    },
  ]

  # No DNS record is needed: `A *.mctl.ai` is proxied and already resolves this
  # host to the cluster origin (zones/mctl-ai/dns.tf). Access sits in front of it
  # because the record is proxied, which is what makes this application effective.

  # Google alone. The one-time PIN provider (e3a75cb3-c81f-43db-acf2-579db7949595)
  # was allowed here at first, on the argument that a customer's work address is
  # not necessarily a Google account, and removed on 2026-09-18: a code mailed to
  # whoever controls an inbox is a weaker thing to hold this behind than an
  # account, and the addresses actually being admitted are Google-backed.
  #
  # The cost is real and belongs next to the decision: an address in the grants
  # list that is not a Google account is now admitted by the policy and still
  # unable to log in, which looks to that person like a broken product rather
  # than a missing provider. Restoring it is putting the UUID above back in this
  # list; nothing else here depends on the count.
  allowed_idps = [
    var.projects_mcp_google_idp_id,
  ]

  # One provider, so there is nothing to pick — but the picker page is also
  # where Access says "That account does not have access", and skipping it
  # sends a refused person straight back to Google instead of telling them
  # why. Left off deliberately.
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
