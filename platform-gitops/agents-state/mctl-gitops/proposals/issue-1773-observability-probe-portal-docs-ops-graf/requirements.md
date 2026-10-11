# Probe the platform consoles (portal, docs, ops, grafana, agent) and discover every ERPact site automatically

## Context

`platform-gitops/infra-components/observability/blackbox/vmprobes.yaml` holds the
VMProbes that check the platform from outside through Cloudflare and Traefik.
Today it covers `mctl.ai`, `secrets.mctl.ai`, `tg.mctl.ai`, `git.mctl.ai`,
`auth.mctl.ai`, `api.mctl.ai`, the two redirect zones and five hard-coded ERPact
sites. It does not cover the developer portal `app.mctl.ai` (Backstage), `docs.mctl.ai`,
`ops.mctl.ai` (Argo CD), `grafana.mctl.ai` or `agent.mctl.ai` (finding OBS-003 of
the 2026-10-10 platform audit). When the portal deploy at 09:51Z on 2026-10-10 made
its own readiness probes time out, nothing outside the cluster recorded the
outage.

The `erpact-sites` VMProbe uses a fixed list of five targets. Sites created
through `mctl_erpact_create_site` are written by the ERPact site deployer to the
private Forgejo repo `git.mctl.ai/erpact/mctl-apps`, which this repo does not
contain. As a result the list fell behind: three active sites have no probe
(OBS-012), and the `erpact.capacity` comment in `vm-rules/erpact-alerts.yaml`
mentions 8 sites. The full list of sites is only known in the cluster, as the
Ingress objects in namespace `erpact`. The admission policy
`mctl-external-manifests-ingress-hosts` limits those Ingresses to
`erpact-*.mctl.ai`. So the probe should discover its targets from those
Ingresses instead of reading a list in git.

## User stories

- AS a platform operator I WANT an external probe and a Telegram alert for
  app.mctl.ai, docs.mctl.ai, ops.mctl.ai, grafana.mctl.ai and agent.mctl.ai SO THAT an
  outage like the 2026-10-10 portal deploy is recorded and reported to a person.
- AS a platform operator I WANT every ERPact site to be probed as soon as its
  Ingress exists SO THAT a site created by `mctl_erpact_create_site` gets a probe
  without a separate edit to mctl-gitops.
- AS an on-call engineer I WANT an alert when an ERPact site Ingress exists but no
  probe covers it SO THAT a failure in target discovery is visible and not silent.

## Acceptance criteria (EARS)

- THE SYSTEM SHALL define one new VMProbe `platform-consoles` (jobName
  `platform-consoles`, module `http_2xx`, interval `60s`, prober
  `blackbox-exporter.monitoring.svc.cluster.local:9115`) in
  `blackbox/vmprobes.yaml`. It SHALL have exactly five static targets, one each for app,
  docs, ops, grafana and agent. Each target SHALL use a path that needs no login and
  returns 2xx when the service is healthy.
- WHEN `probe_success{job="platform-consoles"} == 0` holds for 5 minutes for an
  instance THE SYSTEM SHALL fire `PlatformConsoleDown` (severity `warning`,
  `service: platform`, the instance in the summary).
- IF no `probe_success{job="platform-consoles"}` series exists for 15 minutes THEN
  THE SYSTEM SHALL fire `PlatformConsoleProbeAbsent`.
- WHEN any `PlatformConsole.*` alert fires THE SYSTEM SHALL deliver it to the
  `telegram` Alertmanager receiver. A matching route goes in
  `bootstrap/templates/observability/monitoring.yaml`.
- THE SYSTEM SHALL build the `erpact-sites` VMProbe targets from the Ingress
  objects in namespace `erpact` (VMProbe `spec.targets.ingress`), not from
  `staticConfig`. It SHALL keep `jobName: erpact-sites`, module `http_2xx`, interval
  `60s`, and the target and instance form `https://<host>/api/method/ping`.
- WHEN a new Ingress with host `erpact-<name>.mctl.ai` appears in namespace
  `erpact` THE SYSTEM SHALL start probing `https://erpact-<name>.mctl.ai/api/method/ping`
  within one vmagent service-discovery cycle, with no change to mctl-gitops.
- WHILE one Ingress lists several paths or rules for the same host THE SYSTEM
  SHALL produce exactly one probe target for that host.
- IF an Ingress host in namespace `erpact` has had no matching
  `probe_success{job="erpact-sites"}` instance for 15 minutes THEN THE SYSTEM SHALL
  fire `ErpactSiteUnprobed` (warning) naming the host.
- WHEN `ErpactSiteDown`, `ErpactSiteProbeAbsent` or `ErpactSiteUnprobed` fires THE
  SYSTEM SHALL deliver it to Telegram and also keep delivering it to mctl-agent
  (`continue: true` plus an entry in the mctl-agent catch-all).
- THE SYSTEM SHALL include promtool unit tests in `vm-rules/tests/` for every new
  alert rule, and `scripts/check-vm-rules.sh` SHALL pass in `validate-manifests.yml`.
- WHEN the PR is opened THE PR description SHALL list every new probe target with
  the HTTP status code seen by one read-only `curl` (and, for the ERPact
  set, the full list of discovered sites).

## Out of scope

- OTel or metrics instrumentation of the portal or any other probed service.
- Changes to the Cloudflare zone, Access applications or WAF/SBFM rules (unless the
  hand check shows a probe target is challenged at the edge; see Open questions).
- Changes to the ERPact site deployer or to `git.mctl.ai/erpact/mctl-apps`.
- Probing preview environments or tenant services other than ERPact.
- Changing `PublicEndpointDown` severity or adding the consoles to `platform-public`.

## Open questions

- Exact probe path per console. Proposed: `https://app.mctl.ai/.backstage/health/v1/readiness`
  (the path the Backstage pod's own probes use, `mctl-platform/mctl-portal.yaml`),
  `https://docs.mctl.ai/` (static site; `/healthz` if `/` is ever put behind
  auth), `https://ops.mctl.ai/healthz` (argocd-server), `https://grafana.mctl.ai/api/health`,
  `https://agent.mctl.ai/healthz` (base-service liveness path, `mctl-platform/mctl-agent.yaml`).
  The implementer must confirm each with `curl` before merging and change it if the
  answer is not a stable 2xx.
- Cloudflare Super Bot Fight Mode is skipped for Hetzner (AS24940) only on the
  hosts listed in `infrastructure/cloudflare/zones/mctl-ai/firewall.tf`.
  `grafana.mctl.ai`, `docs.mctl.ai` and `agent.mctl.ai` are not in that list. Existing
  probes of `git.`/`auth.` hosts outside the list work, so a challenge is not
  expected. If one appears in the hand check, a firewall change is a separate PR.
- Routing ErpactSite* to Telegram is a reasonable reading of "ErpactSiteDown is
  a warning routed to mctl-agent only" in the issue, but the Expected list does
  not ask for it. If the reviewer disagrees, drop tasks.md task 7 / design.md section 6 (it is independent).
- Severity of `PlatformConsoleDown`: `warning` with a 5m `for`, matching the
  forgejo and zitadel pattern for hosts that are not front doors. A reviewer may
  want `critical` for `app.mctl.ai`.
