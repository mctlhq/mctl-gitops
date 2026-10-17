# Email Routing destination addresses. They belong to the account, not to a
# zone: a rule in zones/mctl-ai (email.tf) forwards only to an address that
# exists here and has been verified. Verification is runtime state
# (mctlhq/.github#47): Cloudflare mails a link to a new address, and nothing
# is forwarded to it until its owner follows that link. So an apply that
# adds an address comes first, the owner verifies, and only then is the
# zones/mctl-ai rule that forwards to it applied.
#
# Both addresses are personal and this repository is public, so they arrive
# from repository secrets, as in zones/mctl-ai: CF_MCTL_AI_EMAIL_DESTINATION
# and CF_MCTL_AI_EMAIL_OBUKHOV, passed as TF_VAR_* by cloudflare-plan.yml,
# cloudflare-apply.yml and cloudflare-drift.yml. No defaults: an unset secret
# fails the plan instead of planning an address nobody owns.

variable "email_routing_destination" {
  description = "The shared mailbox the mctl.ai Email Routing rules forward to."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.email_routing_destination))
    error_message = "email_routing_destination must be one well-formed e-mail address (CF_MCTL_AI_EMAIL_DESTINATION)."
  }
}

variable "email_routing_destination_obukhov" {
  description = "The personal mailbox obukhov@mctl.ai forwards to."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.email_routing_destination_obukhov))
    error_message = "email_routing_destination_obukhov must be one well-formed e-mail address (CF_MCTL_AI_EMAIL_OBUKHOV)."
  }
}

# Verified 2026-03-15; every mctl.ai rule but obukhov@ forwards here.
import {
  to = cloudflare_email_routing_address.shared
  id = "${var.account_id}/d8f33db7a1d94afcbca7fd4076539611"
}

resource "cloudflare_email_routing_address" "shared" {
  account_id = var.account_id
  email      = var.email_routing_destination

  # Every forward rule of the zone depends on it; a replacement would leave
  # them pointing at an unverified address until someone clicks a new link.
  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_email_routing_address" "obukhov" {
  account_id = var.account_id
  email      = var.email_routing_destination_obukhov
}
