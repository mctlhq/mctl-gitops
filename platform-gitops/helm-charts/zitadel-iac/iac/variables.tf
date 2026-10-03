# Both arrive as TF_VAR_* from Secrets that ESO fills from Vault (see the
# pod in ../templates/_pod.tpl). Neither has a default: a run without them
# fails instead of planning against an empty input.

variable "tenant_users" {
  description = <<-EOT
    JSON object, one key per platform tenant. Each value is the tenant's
    Vault secret secret/platform/zitadel/users/<tenant> as JSON: one field
    per user name, each a JSON-encoded {email, first_name, last_name,
    preferred_language}. This repository is public, so personal data never
    appears in it.
  EOT
  type        = string
}

variable "smtp_password" {
  description = "The Resend API key ZITADEL sends mail with (SMTP password)."
  type        = string
  sensitive   = true
}
