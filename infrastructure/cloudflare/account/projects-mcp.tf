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

variable "projects_mcp_otp_idp_id" {
  description = "The one-time PIN (email code) identity provider in this account."
  type        = string
  default     = "e3a75cb3-c81f-43db-acf2-579db7949595"
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

  # Google alone at first; the one-time PIN provider was removed on 2026-09-18
  # on the argument that a code mailed to whoever controls an inbox is a
  # weaker thing to hold this behind than an account, and the addresses being
  # admitted at the time were Google-backed.
  #
  # Restored on 2026-09-19: grants were added (in Vault, not this repo) for
  # non-Google customer domains this org does not control and cannot confirm
  # are Google-backed — without this, the policy admits them and they still
  # cannot sign in, which reads as a broken product rather than a missing
  # provider. The cost above is accepted knowingly: for any address, whoever
  # can read that inbox authenticates as it. Nothing else here depends on the
  # count if this needs removing again.
  allowed_idps = [
    var.projects_mcp_google_idp_id,
    var.projects_mcp_otp_idp_id,
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

        # The Cloudflare dashboard's own callback, registered out of band on
        # 2026-09-19 when an admin completed the upstream OAuth login that turns
        # this server from `waiting` into the portal's fourth upstream. That
        # login is what produces the admin credential every later capability
        # sync runs with (infrastructure/cloudflare/portal/mcp-servers.tf says
        # so, and says the credential expires with nobody being told).
        #
        # It is listed here because the plan that added
        # portal-mcp-apps.tf showed this URI being REMOVED: it exists only
        # because the dashboard wrote it, so the first apply of this root after
        # that login would have taken it back out. Nothing breaks the moment it
        # goes — the credential already obtained keeps working — which is
        # exactly why it is worth writing down: the failure would surface much
        # later, as a re-authorization that cannot complete, on the day
        # `authentication_status` has already gone stale and the server has
        # stopped appearing for end users.
        "https://dash.cloudflare.com/${var.account_id}/one/access-controls/ai-controls/mcp-server/oauth-callback/projects",

        # The MCP portal's own callback. The dashboard URI above is the ADMIN's
        # one-time login, which is what produces the credential the capability
        # sync runs with; this one is every END USER's authorization, and it is
        # a separate flow that was never going to work without being listed.
        #
        # Measured on 2026-09-19, after the portal member application landed and
        # `mctl Projects (projects.mctl.ai)` finally appeared in a client's
        # server list: it came up "Authorization failed: invalid request", and
        # no login event for this application reached the Access log at all,
        # because the request never got as far as a policy. Asking Access
        # directly, with a registered client whose redirect is this URI:
        #
        #   GET /cdn-cgi/access/oauth/authorization?...
        #       &redirect_uri=https://mcp.mctl.ai/servers-callback
        #       &resource=https://projects.mctl.ai/mcp
        #   302 -> ...?error=invalid_request
        #          &error_description=Redirect+URI+not+allowed+by+application+configuration
        #
        # The other three upstreams never hit this: they run their own OAuth
        # servers, which accept whatever redirect the portal was configured
        # with by hand (infrastructure/cloudflare/portal/mcp-servers.tf). Here
        # Access IS the authorization server, so the portal is just another
        # client and this list is what it is checked against.
        "https://mcp.mctl.ai/servers-callback",
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

  # Access authenticates; this server authorizes.
  #
  # The policy admitted one address per person until 2026-09-19, built from the
  # grants list. Two things were wrong with that. The list carries customers'
  # sign-in addresses, and building the policy from it meant the list had to be
  # readable by a job that plans on every pull request in a PUBLIC repository —
  # and a pull request that adds a root is code this repository runs with that
  # job's credentials, so the credential that reads the list is reachable by
  # any branch. And it was a second place where access lived: handing somebody
  # a project meant an edit AND an apply here, which is how a person ends up
  # granted in one place and refused in the other.
  #
  # So the list is in Vault, read only by the pod, and this policy admits any
  # account from either identity provider above. What that buys a stranger is
  # an authenticated conversation with a server that tells them nothing: a
  # caller with no grant sees an empty project list, and every project answers
  # exactly as it answers for a project that does not exist. That is not a
  # weaker check than the one removed — it is the same check, in the one place
  # that was always doing it, and tests/leak.test.ts in mctlhq/projects-mcp
  # sweeps every tool for a caller with no grant at all.
  #
  # What is genuinely given up: reaching the origin no longer requires being
  # known in advance, so the pod is exposed to anyone who can sign in with
  # Google or receive a one-time PIN, rather than to a named few. The server
  # holds no credential for anybody's documentation and serves it from a copy
  # baked into its image, so what is behind the door is the filtering code and
  # the corpus it filters.
  policies = [
    {
      name       = "projects-mcp-any-google-or-otp-account"
      decision   = "allow"
      precedence = 1

      include = [
        { login_method = { id = var.projects_mcp_google_idp_id } },
        { login_method = { id = var.projects_mcp_otp_idp_id } },
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
