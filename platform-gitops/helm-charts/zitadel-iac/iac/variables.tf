# Both arrive as TF_VAR_* from Secrets that ESO fills from Vault (see the
# pod in ../templates/_pod.tpl). Neither has a default: a run without them
# fails instead of planning against an empty input.

variable "tenant_users" {
  description = <<-EOT
    JSON object, one key per platform tenant, each value a JSON-encoded list
    of {user_name, email, first_name, last_name}. Read from Vault
    secret/platform/zitadel/users, one field per tenant. This repository is
    public, so personal data never appears in it.
  EOT
  type        = string
}

variable "smtp_password" {
  description = "The Resend API key ZITADEL sends mail with (SMTP password)."
  type        = string
  sensitive   = true
}
