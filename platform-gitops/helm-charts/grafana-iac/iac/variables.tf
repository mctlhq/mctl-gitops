# VMAuth user erpact's password, for the erpact org's datasource (erpact.tf).
# Read by the pod from the Secret grafana-iac-tenant-erpact, which ESO fills
# from Vault platform/grafana-tenants/erpact (the same value VMAuth checks).
variable "erpact_metrics_password" {
  type      = string
  sensitive = true
  nullable  = false

  validation {
    condition     = length(var.erpact_metrics_password) > 0
    error_message = "The erpact metrics password is empty."
  }
}
