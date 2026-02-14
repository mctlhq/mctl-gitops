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

variable "github_repo_pat" {
  type        = string
  sensitive   = true
  description = "GitHub PAT for ArgoCD to access private repos"
}

variable "backstage_github_client_id" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub OAuth Client ID for Backstage auth"
}

variable "backstage_github_client_secret" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GitHub OAuth Client Secret for Backstage auth"
}
