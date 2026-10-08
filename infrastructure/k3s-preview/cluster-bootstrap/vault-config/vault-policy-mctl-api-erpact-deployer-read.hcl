# mctl-api: read-only access to tenant erpact's site-deployer token
# (mctl-api#486, cmd/api/main.go's erpactDeployer construction), gating the
# three temporary /api/v1/tenants/erpact/sites* routes.
#
# Its own policy, not folded into mctl-api-openclaw-read: that one is scoped
# to secret/data/teams/+/+/telegram across every tenant, and widening it to
# also cover this single erpact path would let a future tenant's "+/+"
# match land here too. A second, single-path policy keeps each grant exactly
# as wide as the one handler that uses it.
path "secret/data/teams/erpact/deployer" {
  capabilities = ["read"]
}
