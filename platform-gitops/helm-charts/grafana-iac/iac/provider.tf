# Signs in as Grafana's built-in server admin with HTTP basic auth, through
# the in-cluster Service only. Creating organizations (the tenant orgs of
# #1601) needs a server admin, which a service account can never be in OSS,
# so a service-account token could not bootstrap this root.
#
# The credential is GRAFANA_AUTH ("user:password"), which the pod builds from
# the Secret grafana-iac-admin (../templates/_pod.tpl). The public ingress
# strips Authorization (infra-components/observability/grafana-access), and
# Grafana's NetworkPolicy admits port 3000 from traefik, this namespace and
# vmagent only, so basic auth works from this Job and from nowhere else.
provider "grafana" {
  url = "http://monitoring-grafana.monitoring.svc.cluster.local"
}
