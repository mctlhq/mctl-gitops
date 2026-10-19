# Design: incident-42ea82c0

## Diagnosis
The admins-umami-retention CronJob runs a psql script in a single transaction. Eight DELETE statements
succeeded, then a statement beginning with `DO $` failed with a syntax error at the lone `$`. A PL/pgSQL
`DO $$ ... $$` block is almost certainly being written with `$$` inside a container command/args or a
templated value: Kubernetes treats `$$` in command/args as an escape and collapses it to a single `$`,
and Helm/YAML quoting can also alter it. The result is `DO $ ...`, which Postgres rejects. mctl-agent had
no skill for this alert, so it was escalated. The sibling KubeJobFailed incident is the same failing Job.

## Proposed Fix
Locate the Umami retention CronJob in the admins tenant (likely under platform-gitops/services/admins/umami/
or its chart templates; grep for "umami-retention" and "DO $"). Change the DO block so the dollar quotes
survive: either use a named tag (`DO $retention$ ... $retention$;`), which is not subject to the `$$` escape,
or mount the SQL via a ConfigMap and run `psql -f`, or write `$$$$` in command/args if inline. The
named-tag approach is preferred.

## Scope
Minimal. Only touch the retention SQL quoting in the CronJob; do not change retention periods or schedule.

## Confidence: LOW
The exact CronJob file was not inspected and only the tail of the log was available. The `$$` collapse
is an inference from the error text. Verify against the actual manifest before applying.
