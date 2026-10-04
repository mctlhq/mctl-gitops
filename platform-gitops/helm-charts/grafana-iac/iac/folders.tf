# The Main Org "Internal" folder is for platform admins only. The dashboards
# sidecar creates it from the grafana_folder annotation
# (infra-components/observability/grafana-dashboards/mctl-academy-usage-dashboard-configmap.yaml),
# with Grafana's default permissions: Viewer can view, Editor can edit. This
# replaces them with Admin only, before any tenant user can sign in (#1601).
#
# Looked up by title, so a missing folder fails the plan rather than letting
# the run report success with nothing protected.
data "grafana_folder" "internal" {
  title = "Internal"
}

# Authoritative: every role, team and user item on the folder is replaced by
# this list, so a permission added in the UI is reverted by the next run.
resource "grafana_folder_permission" "internal" {
  folder_uid = data.grafana_folder.internal.uid

  permissions {
    role       = "Admin"
    permission = "Admin"
  }
}
