# The organization of tenant erpact (#1601 step 4). Metrics only for now; the
# tenant's logs follow with Loki multi-tenancy (step 3).
#
# Nobody can reach it until step 5: membership comes only from the ZITADEL
# sign-in (org_mapping), never from this root. Its only datasource goes
# through VMAuth (infra-components/observability/grafana-tenants), which adds
# namespace="erpact" to every query, so whatever a member types, Grafana
# returns erpact series only. Members get Editor, which in OSS cannot add or
# change a datasource, so they cannot point a query anywhere else.

# The provider reads every member of the org back into admins / editors /
# viewers / users_without_access. Left in the plan, an unset list would remove
# the members the ZITADEL sign-in adds, and print their email addresses in the
# Job log. Membership is the sign-in's job, so the lists are ignored here.
# `admin` (the server admin this root signs in as) is added by Grafana on
# creation and kept by the provider's admin_user default.
resource "grafana_organization" "erpact" {
  name = "erpact"

  lifecycle {
    ignore_changes = [admins, editors, viewers, users_without_access]
  }
}

# The tenant's metrics, through VMAuth as user erpact. GET, as tested in
# step 2 (#1657); VictoriaMetrics would apply the proxy's extra_label to a
# POST body as well. The password reaches this root only as a sensitive
# variable (../templates/_pod.tpl), so it is in no plan or log.
resource "grafana_data_source" "erpact_metrics" {
  org_id     = grafana_organization.erpact.org_id
  type       = "prometheus"
  name       = "VictoriaMetrics"
  uid        = "erpact-metrics"
  url        = "http://vmauth-grafana-tenants.monitoring.svc:8427"
  is_default = true

  basic_auth_enabled  = true
  basic_auth_username = "erpact"

  json_data_encoded = jsonencode({
    httpMethod   = "GET"
    timeInterval = "30s"
  })
  secure_json_data_encoded = jsonencode({
    basicAuthPassword = var.erpact_metrics_password
  })
}

resource "grafana_folder" "erpact" {
  org_id = grafana_organization.erpact.org_id
  title  = "ERPact"
  uid    = "erpact"
}

# Members can open these dashboards but not change them: a member's own
# dashboards go to General, and the next run would revert an edit here anyway.
resource "grafana_folder_permission" "erpact" {
  org_id     = grafana_organization.erpact.org_id
  folder_uid = grafana_folder.erpact.uid

  permissions {
    role       = "Admin"
    permission = "Admin"
  }
  permissions {
    role       = "Editor"
    permission = "View"
  }
  permissions {
    role       = "Viewer"
    permission = "View"
  }
}

# The same dashboard Main Org gets from the sidecar
# (infra-components/observability/grafana-dashboards/erpact-tenant-dashboard-configmap.yaml);
# a change there belongs here too. Its datasource variable picks the org's only
# Prometheus datasource, named VictoriaMetrics like Main Org's.
resource "grafana_dashboard" "erpact_overview" {
  org_id      = grafana_organization.erpact.org_id
  folder      = grafana_folder.erpact.uid
  config_json = file("${path.module}/erpact-overview.json")
  overwrite   = true
}

resource "grafana_dashboard" "erpact_workloads" {
  org_id      = grafana_organization.erpact.org_id
  folder      = grafana_folder.erpact.uid
  config_json = file("${path.module}/erpact-workloads.json")
  overwrite   = true
}
