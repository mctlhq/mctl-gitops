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

variable "monteexchange_bot_token" {
  type        = string
  sensitive   = true
  description = "Telegram Bot Token for monteexchange"
}

variable "monteexchange_wise_token" {
  type        = string
  sensitive   = true
  description = "Wise API Token for monteexchange"
}

variable "monteexchange_balance_id" {
  type        = string
  description = "Wise Balance ID for monteexchange"
}

variable "monteexchange_profile_id" {
  type        = string
  description = "Wise Profile ID for monteexchange"
}

variable "monteexchange_exchange_fee" {
  type        = string
  default     = "1.75"
  description = "Exchange fee percentage for monteexchange"
}

variable "monteexchange_withdrawal_fee" {
  type        = string
  default     = "0"
  description = "Withdrawal fee for monteexchange"
}

variable "monteexchange_wise_host" {
  type        = string
  default     = "https://api.transferwise.com"
  description = "Wise API host for monteexchange"
}
