# Design: incident-43d9e608

## Confidence: LOW

(Confidence is LOW because vmagent pod logs were unavailable via Loki and the incident labels did not include the specific scrape_pool name. The diagnosis below is based on the alert type and standard VictoriaMetrics behavior. The implementer should verify which scrape pool is empty before applying the fix.)

## Diagnosis

The AlertManager alert "Vmagent has scrape_pool with 0 configured/discovered targets" fires from the vmagent instance in the `monitoring` tenant. Vmagent tracks each configured `job_name` as a scrape pool; when kubernetes service discovery or static_configs in that job resolves to zero endpoints, this alert fires. The root cause is one of:

1. A `VMScrapeConfig` or `VMServiceMonitor` CRD in the `monitoring` namespace has a `namespaceSelector` or `selector.matchLabels` that no longer matches any running pod or service (e.g., a service was removed, renamed, or its labels changed).
2. A `static_configs` entry in the vmagent ConfigMap references a hostname or IP that no longer exists.
3. A scrape job was added for a service that was never actually deployed or has since been retired.

No skill in the current incident-responder pattern library matched this incident (type remained `generic`), meaning it arrived as a raw AlertManager webhook with no enrichment.

## Proposed Fix

Step 1 — Identify the empty pool name:

  Access the vmagent web UI at its service endpoint:
    http://vmagent.monitoring.svc.cluster.local:8429/targets
  Look for any scrape pool listed as "0 / 0 targets" (configured=0 or up=0).
  Note the job_name value.

Step 2a — If the empty pool is a VMScrapeConfig or VMServiceMonitor CRD:

  File: platform-gitops/tenants/monitoring/scrapeconfigs/ (or equivalent path)
  Action: Either delete the CRD manifest for the orphaned job, or update its
  `spec.selector.matchLabels` / `spec.namespaceSelector` to correctly target the
  intended service.

  Example — remove an orphaned VMScrapeConfig:
    Current: file platform-gitops/tenants/monitoring/scrapeconfigs/orphaned-job.yaml exists
    Fix: delete the file and remove it from kustomization.yaml resources list.

Step 2b — If the empty pool is defined in the vmagent ConfigMap:

  File: platform-gitops/tenants/monitoring/vmagent-config.yaml (or equivalent)
  Field: data.scrape_configs[]
  Action: Remove the stale job block whose job_name matches the empty pool.

## Scope

Minimal. Remove or correct only the single scrape job that has 0 targets. Do not modify any other scrape configurations or AlertManager rules.
