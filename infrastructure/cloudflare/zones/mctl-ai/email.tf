# Email Routing for mctl.ai. Seven addresses forward to one mailbox, and the
# catch-all drops everything else — enabled deliberately as #1089 item 7, so
# that the declared state and the intent are the same thing.
#
# Not managed: Email Routing verification status, which is runtime state per
# mctlhq/.github#47.

# The mailbox all seven rules forward to is a personal address, and this
# repository is public, so it is not written here. It arrives at plan and
# apply time from the repository secret CF_MCTL_AI_EMAIL_DESTINATION, passed
# as TF_VAR_email_routing_destination by cloudflare-plan.yml,
# cloudflare-apply.yml and cloudflare-drift.yml for this root only.
#
# Fail closed: no default, so an unset or unreadable secret fails the plan
# instead of planning a forward to nowhere; a malformed value fails the
# validation. Sensitive, so plans print "(sensitive value)" in a public
# repository's Actions logs. The address was written inline until
# 2026-10-04 and remains in git history, which is not rewritten.
variable "email_routing_destination" {
  description = "The verified mailbox every mctl.ai Email Routing rule forwards to."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.email_routing_destination))
    error_message = "email_routing_destination must be one well-formed e-mail address (CF_MCTL_AI_EMAIL_DESTINATION)."
  }
}

resource "cloudflare_email_routing_rule" "security" {
  actions = [
    {
      type  = "forward"
      value = [var.email_routing_destination]
    },
  ]
  enabled = true
  matchers = [
    {
      field = "to"
      type  = "literal"
      value = "security@mctl.ai"
    },
  ]
  name     = "Rule created at 2026-03-15T09:01:11.737Z"
  priority = 0
  source   = "api"
  zone_id  = local.zone_id
}

resource "cloudflare_email_routing_rule" "privacy" {
  actions = [
    {
      type  = "forward"
      value = [var.email_routing_destination]
    },
  ]
  enabled = true
  matchers = [
    {
      field = "to"
      type  = "literal"
      value = "privacy@mctl.ai"
    },
  ]
  name     = "Rule created at 2026-03-15T09:09:19.520Z"
  priority = 0
  source   = "api"
  zone_id  = local.zone_id
}

resource "cloudflare_email_routing_catch_all" "default" {
  actions = [
    {
      type = "drop"
    },
  ]
  enabled = true
  matchers = [
    {
      type = "all"
    },
  ]
  name    = ""
  source  = "api"
  zone_id = local.zone_id
}

resource "cloudflare_email_routing_rule" "agent" {
  actions = [
    {
      type  = "forward"
      value = [var.email_routing_destination]
    },
  ]
  enabled = true
  matchers = [
    {
      field = "to"
      type  = "literal"
      value = "agent@mctl.ai"
    },
  ]
  name     = "Rule created at 2026-03-15T09:10:48.792Z"
  priority = 0
  source   = "api"
  zone_id  = local.zone_id
}

resource "cloudflare_email_routing_rule" "support" {
  actions = [
    {
      type  = "forward"
      value = [var.email_routing_destination]
    },
  ]
  enabled = true
  matchers = [
    {
      field = "to"
      type  = "literal"
      value = "support@mctl.ai"
    },
  ]
  name     = "Rule created at 2026-03-15T09:05:20.410Z"
  priority = 0
  source   = "api"
  zone_id  = local.zone_id
}

resource "cloudflare_email_routing_rule" "noreply" {
  actions = [
    {
      type  = "forward"
      value = [var.email_routing_destination]
    },
  ]
  enabled = true
  matchers = [
    {
      field = "to"
      type  = "literal"
      value = "noreply@mctl.ai"
    },
  ]
  name     = "Rule created at 2026-03-15T09:06:13.287Z"
  priority = 0
  source   = "api"
  zone_id  = local.zone_id
}

resource "cloudflare_email_routing_rule" "dmitrii" {
  actions = [
    {
      type  = "forward"
      value = [var.email_routing_destination]
    },
  ]
  enabled = true
  matchers = [
    {
      field = "to"
      type  = "literal"
      value = "dmitrii.mashkov@mctl.ai"
    },
  ]
  name     = "Rule created at 2026-03-31T19:05:01.535Z"
  priority = 0
  source   = "api"
  zone_id  = local.zone_id
}

resource "cloudflare_email_routing_rule" "ci" {
  actions = [
    {
      type  = "forward"
      value = [var.email_routing_destination]
    },
  ]
  enabled = true
  matchers = [
    {
      field = "to"
      type  = "literal"
      value = "ci@mctl.ai"
    },
  ]
  name     = "Rule created at 2026-03-15T09:10:15.590Z"
  priority = 0
  source   = "api"
  zone_id  = local.zone_id
}
