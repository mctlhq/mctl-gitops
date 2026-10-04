# All arrive as TF_VAR_* from Secrets that ESO fills from Vault (see the
# pod in ../templates/_pod.tpl). None has a default: a run without them
# fails instead of planning against an empty input.

variable "tenant_users" {
  description = <<-EOT
    JSON object, one key per platform tenant. Each value is the tenant's
    Vault secret secret/platform/zitadel/users/<tenant> as JSON: one field
    per user name, each a JSON-encoded {email, first_name, last_name,
    preferred_language, argocd, vault, workflows}; argocd, vault and
    workflows (optional, default false) grant the tenant's Argo CD role
    (argocd.tf), Vault role (vault.tf) and Argo Workflows role
    (workflows.tf). This repository is public, so personal data never
    appears in it.
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
    personal platform admin account in the MCTL organization, each a
    JSON-encoded {email, first_name, last_name, preferred_language, username}
    (admins.tf). The field name is the stable key of the account; `username`,
    optional, is its login name when it differs from the key. This repository
    is public, so personal data never appears in it.
  EOT
  type        = string

  # An empty or malformed object is a failed read, not "no admins": planning
  # it would remove every personal admin and their grants. Retiring the last
  # personal admin is a reviewed change to this rule. A key and a user name
  # are plain handles: no "@", so they cannot collide with a break-glass
  # login name, and never mctl-admin, which already exists. `username`, when
  # present, must be such a handle too (a present but empty or non-string
  # value is malformed, not "unset"), and the resulting login names must be
  # unique: ZITADEL would refuse the second one mid-apply.
  validation {
    condition = try(
      length(keys(jsondecode(var.platform_admins))) > 0 && alltrue([
        for key, attrs in jsondecode(var.platform_admins) :
        can(regex("^[a-z0-9][a-z0-9._-]*$", key)) && key != "mctl-admin" &&
        length(trimspace(jsondecode(attrs).email)) > 0 &&
        length(trimspace(jsondecode(attrs).first_name)) > 0 &&
        length(trimspace(jsondecode(attrs).last_name)) > 0 &&
        (
          !contains(keys(jsondecode(attrs)), "username") ||
          (
            # A JSON number would pass the regex once converted; == is false
            # across types, so this admits strings only.
            jsondecode(attrs).username == tostring(jsondecode(attrs).username) &&
            can(regex("^[a-z0-9][a-z0-9._-]*$", jsondecode(attrs).username)) &&
            jsondecode(attrs).username != "mctl-admin"
          )
        )
      ]) &&
      length(distinct([
        for key, attrs in jsondecode(var.platform_admins) :
        contains(keys(jsondecode(attrs)), "username") ? jsondecode(attrs).username : key
      ])) == length(keys(jsondecode(var.platform_admins))),
      false,
    )
    error_message = "platform_admins must be a non-empty JSON object of key => JSON {email, first_name, last_name, optional username}, with lowercase [a-z0-9._-] keys and usernames that are unique and not mctl-admin; zitadel-iac-admins resolved none from Vault secret/platform/zitadel/admins, or an entry is malformed."
  }
}

variable "smtp_password" {
  description = "The Resend API key ZITADEL sends mail with (SMTP password)."
  type        = string
  sensitive   = true
}
