# mctl-api: read-only check for a saved Telegram bot token during OpenClaw
# onboarding preflight (handlers_openclaw.go's resume-deploy handler).
#
# Scoped to exactly the one path it reads — secret/teams/{team}/{component}/telegram
# — not the full secret/teams/+/+ tree backstage-teams-rw grants, since
# mctl-api has no write path and reads nothing else in Vault today.
path "secret/data/teams/+/+/telegram" {
  capabilities = ["read"]
}
