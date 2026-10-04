# All arrive as TF_VAR_* from Secrets that ESO fills from Vault (see the
# pod in ../templates/_pod.tpl). None has a default: a run without them
# fails instead of planning against an empty input.

variable "tenant_users" {
  description = <<-EOT
    JSON object, one key per platform tenant. Each value is the tenant's
    Vault secret secret/platform/zitadel/users/<tenant> as JSON: one field
    per user name, each a JSON-encoded {email, first_name, last_name,
    preferred_language, argocd, vault}; argocd and vault (optional, default
    false) grant the tenant's Argo CD role (argocd.tf) and Vault role
    (vault.tf). This repository is public, so personal data never appears in
    it.
  EOT
  type        = string

  # An empty object is a failed read, not "no tenants": a mistyped Vault path
  # or a find that matched nothing must stop the run, not plan zero users
  # (and later, deletions). Retiring the last tenant is a reviewed change to
  # this rule.
  validation {
    condition     = can(jsondecode(var.tenant_users)) && length(keys(jsondecode(var.tenant_users))) > 0
    error_message = "tenant_users must be a non-empty JSON object; zitadel-iac-users resolved no tenants from Vault secret/platform/zitadel/users/*."
  }
}

variable "platform_admins" {
  description = <<-EOT
    The Vault secret secret/platform/zitadel/admins as JSON: one field per
    user name of a personal platform admin account in the MCTL organization,
    each a JSON-encoded {email, first_name, last_name, preferred_language}
    (admins.tf). This repository is public, so personal data never appears in
    it.
  EOT
  type        = string

  # An empty or malformed object is a failed read, not "no admins": planning
  # it would remove every personal admin and their grants. Retiring the last
  # personal admin is a reviewed change to this rule. A user name is a plain
  # handle: no "@", so it cannot collide with a break-glass login name, and
  # never mctl-admin, which already exists.
  validation {
    condition = try(
      length(keys(jsondecode(var.platform_admins))) > 0 && alltrue([
        for user_name, attrs in jsondecode(var.platform_admins) :
        can(regex("^[a-z0-9][a-z0-9._-]*$", user_name)) && user_name != "mctl-admin" &&
        length(trimspace(jsondecode(attrs).email)) > 0 &&
        length(trimspace(jsondecode(attrs).first_name)) > 0 &&
        length(trimspace(jsondecode(attrs).last_name)) > 0
      ]),
      false,
    )
    error_message = "platform_admins must be a non-empty JSON object of user name => JSON {email, first_name, last_name}; zitadel-iac-admins resolved none from Vault secret/platform/zitadel/admins, or an entry is malformed."
  }
}

variable "smtp_password" {
  description = "The Resend API key ZITADEL sends mail with (SMTP password)."
  type        = string
  sensitive   = true
}
