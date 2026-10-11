# mctl-api: read-only access to tenant erpact's site-deployer token
# (mctl-api#486, cmd/api/main.go's erpactDeployer construction), gating the
# three temporary /api/v1/tenants/erpact/sites* routes.
#
# A single-path policy on purpose: a wildcard such as teams/+/+ would let a
# future tenant's path match here too. Each grant stays exactly as wide as
# the one handler that uses it.
path "secret/data/teams/erpact/deployer" {
  capabilities = ["read"]
}
