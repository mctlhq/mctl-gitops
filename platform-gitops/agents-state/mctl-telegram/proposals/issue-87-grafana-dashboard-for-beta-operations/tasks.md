# Tasks: issue-87-grafana-dashboard-for-beta-operations

- [ ] 1. Create `deploy/grafana/` directory and author `deploy/grafana/mctl-telegram-beta.json`
  — DoD: the file exists at that path; `jq . deploy/grafana/mctl-telegram-beta.json`
  exits 0 (valid JSON); the JSON contains `"uid": "mctl-telegram-beta"`,
  `__inputs__` with a `DS_PROMETHEUS` entry, `templating.list` with three
  variables (`namespace`, `pod`, `instance`), and six row panels named Traffic,
  Session pool, Telegram pressure, Sessions lifecycle, OAuth, Rate limiting;
  every non-row panel has a non-empty `description` string; all thirteen metric
  families from `internal/metrics/metrics.go` are referenced at least once.

- [ ] 2. Validate the dashboard JSON against the Grafana schema (depends on 1)
  — DoD: `jq -e '(.schemaVersion >= 39) and (.panels | length > 0) and (.__inputs__ | length > 0)' deploy/grafana/mctl-telegram-beta.json`
  exits 0; all PromQL expressions in the file are syntactically valid (verified
  with `promtool` or `mimirtool rules check` against the expressions extracted
  from the JSON, or by manual review against the Prometheus documentation).

- [ ] 3. Add `## Grafana dashboard` section to `docs/hpa.md` (depends on 1)
  — DoD: `docs/hpa.md` contains a prose reference to
  `deploy/grafana/mctl-telegram-beta.json` and instructions for the import
  step (map `DS_PROMETHEUS` to the environment's Prometheus data source); the
  link text is accurate and the section is placed at the end of the file so
  existing HPA content is undisturbed.

- [ ] 4. Add CI lint step for Grafana JSON validity (depends on 1, optional)
  — DoD: `.github/workflows/ci.yml` (or equivalent) runs
  `jq . deploy/grafana/mctl-telegram-beta.json > /dev/null` on pull requests
  that touch `deploy/grafana/**`; the step is named `lint-grafana-json`; it
  fails the build on malformed JSON; existing CI steps are unaffected.

## Tests

- [ ] T1. Manual import smoke test — import
  `deploy/grafana/mctl-telegram-beta.json` into a local or staging Grafana
  instance; confirm no "Panel plugin not found" or "Data source not found"
  errors appear; confirm all six rows are visible; confirm the `namespace`,
  `pod`, and `instance` variable dropdowns are populated when a Prometheus
  data source with mctl-telegram scrape data is selected.

- [ ] T2. Pool utilization guard — in a Prometheus query console, run
  `1 / clamp_min(-1, 1)` and confirm the result is 1 (not an error); this
  validates that the `clamp_min` guard in the utilization panel expression
  handles the -1 uncapped sentinel without a Grafana divide-by-zero panel
  error.

- [ ] T3. Template variable chaining — with the dashboard open, select a
  specific `namespace`; confirm the `pod` dropdown updates to show only pods
  in that namespace; select a pod; confirm the `instance` dropdown narrows to
  instances for that pod; confirm all panel queries visually update.

- [ ] T4. JSON schema check in CI — open a PR that introduces a syntax error
  into `deploy/grafana/mctl-telegram-beta.json`; confirm the CI `lint-grafana-json`
  step fails; revert the error; confirm CI passes. (Only applies if task 4 is
  implemented.)

## Rollback

The dashboard JSON and the `docs/hpa.md` edit are purely additive. To roll back:

1. Delete `deploy/grafana/mctl-telegram-beta.json` (or the entire
   `deploy/grafana/` directory if it was newly created).
2. Revert the `## Grafana dashboard` section added to `docs/hpa.md`.
3. If task 4 was implemented, revert the CI workflow change.

There are no database migrations, no Kubernetes manifest changes, and no Go
source changes, so no service restart or re-deploy is required. Any Grafana
instance that had already imported the dashboard continues to function; Grafana
does not lose the imported copy when the source file is deleted from Git. If
operators want to remove the dashboard from Grafana itself they must delete it
via the Grafana UI.
