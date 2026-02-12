variable "github_oauth_client_id" {
  type        = string
  sensitive   = true
  description = "GitHub OAuth App Client ID for ArgoCD Dex"
}

variable "github_oauth_client_secret" {
  type        = string
  sensitive   = true
  description = "GitHub OAuth App Client Secret for ArgoCD Dex"
}
