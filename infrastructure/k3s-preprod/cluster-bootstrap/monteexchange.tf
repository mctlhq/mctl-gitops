resource "kubernetes_secret" "monteexchange_secrets" {
  metadata {
    name      = "monteexchange-secrets"
    namespace = "bots"
  }

  data = {
    BOT_TOKEN               = var.monteexchange_bot_token
    WISE_TOKEN              = var.monteexchange_wise_token
    BALANCE_ID              = var.monteexchange_balance_id
    PROFILE_ID              = var.monteexchange_profile_id
    EXCHANGE_FEE_IN_PERCENT = var.monteexchange_exchange_fee
    WITHDRAWAL_FEE          = var.monteexchange_withdrawal_fee
    WISE_HOST               = var.monteexchange_wise_host
  }

  depends_on = [
    # Namespace created by ArgoCD ApplicationSet with CreateNamespace=true
    # Wait a bit to ensure it exists before creating secret
  ]
}
