# All three arrive as TF_VAR_* from the Secret vault-oidc-zitadel in this
# namespace, which the zitadel-iac Job fills (helm-charts/zitadel-iac/iac/
# vault.tf). None has a default: a run without them fails instead of
# planning against an empty input.

variable "oidc_client_id" {
  description = "Client id of the `vault` application in ZITADEL."
  type        = string

  validation {
    condition     = length(trimspace(var.oidc_client_id)) > 0
    error_message = "oidc_client_id is empty; zitadel-iac has not written vault-oidc-zitadel yet."
  }
}

variable "oidc_client_secret" {
  description = "Client secret of the `vault` application in ZITADEL."
  type        = string
  sensitive   = true

  validation {
    condition     = length(trimspace(var.oidc_client_secret)) > 0
    error_message = "oidc_client_secret is empty; zitadel-iac has not written vault-oidc-zitadel yet."
  }
}

variable "tenants" {
  description = <<-EOT
    JSON array of the platform tenants that have ZITADEL users, as zitadel-iac
    derives them from Vault secret/platform/zitadel/users/<tenant>: the same
    list its Vault project roles and the groups claim come from. Each becomes
    an external group whose alias is the tenant's role key.
  EOT
  type        = string

  # An empty list is a failed read, not "no tenants": planning zero tenants
  # would destroy every tenant group and policy. Retiring the last tenant is
  # a reviewed change to this rule.
  validation {
    condition     = can(tolist(jsondecode(var.tenants))) && length(jsondecode(var.tenants)) > 0
    error_message = "tenants must be a non-empty JSON array; vault-oidc-zitadel carries no tenant list."
  }

  # The name goes into a policy path and a policy name, and `admins` is the
  # admin group's claim value: a tenant by that name would hand every opted-in
  # user of it the admin policy. zitadel-iac refuses it too.
  validation {
    condition = alltrue([
      for t in try(jsondecode(var.tenants), []) :
      can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", t)) && t != "admins"
    ])
    error_message = "Every tenant must be a DNS label and none may be named \"admins\"."
  }
}
