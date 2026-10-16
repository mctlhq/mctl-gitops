# Workers KV namespaces of the mctl-web Worker (`mctl-landing-form`).
#
# Server-side sign-in sessions for mctl.ai (mctl-web site onboarding, stage
# C1a, mctlhq/mctl-web docs/plans/site-onboarding-review.md). The browser
# holds only an opaque session id in a `__Host-` cookie; the record behind it,
# including the ZITADEL ID token, lives here under `sess:<sha256(id)>` with an
# expiration of at most 8 hours, so every key expires by itself.
#
# The namespaces are created here and bound in the Worker's wrangler.toml by
# id, the same split as the Worker's routes (zones/mctl-ai/workers.tf): this
# root owns the object, the mctl-web repository owns the script and its
# bindings.
#
# Development gets a namespace of its own, so `wrangler dev --env dev` can
# never read or write a production session.
#
# Not prevent_destroy: the contents are sessions that expire within hours, and
# losing them costs every signed-in visitor one sign-in, not data. A destroy
# still needs allow_destroy on cloudflare-apply.
#
# Creating them needs `Account -> Workers KV Storage: Edit` on
# CF_APPLY_TOKEN_ACCOUNT, and refreshing them needs Read on the plan token.
resource "cloudflare_workers_kv_namespace" "mctl_web_sessions" {
  account_id = var.account_id
  title      = "mctl-web-sessions"
}

resource "cloudflare_workers_kv_namespace" "mctl_web_sessions_dev" {
  account_id = var.account_id
  title      = "mctl-web-sessions-dev"
}

# The ids go into mctl-web's wrangler.toml after the first apply; they are
# identifiers, not secrets.
output "mctl_web_sessions_kv_id" {
  value = cloudflare_workers_kv_namespace.mctl_web_sessions.id
}

output "mctl_web_sessions_dev_kv_id" {
  value = cloudflare_workers_kv_namespace.mctl_web_sessions_dev.id
}
