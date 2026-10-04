# Both arrive as TF_VAR_* from Secrets that ESO fills from Vault (see the
# pod in ../templates/_pod.tpl). Neither has a default: a run without them
# fails instead of planning against an empty input.

variable "tenant_users" {
  description = <<-EOT
    JSON object, one key per platform tenant. Each value is the tenant's
    Vault secret secret/platform/zitadel/users/<tenant> as JSON: one field
    per user name, each a JSON-encoded {email, first_name, last_name,
    preferred_language, argocd}; argocd (optional, default false) grants the
    tenant's Argo CD role (argocd.tf). This repository is public, so personal data never
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

variable "smtp_password" {
  description = "The Resend API key ZITADEL sends mail with (SMTP password)."
  type        = string
  sensitive   = true
}
