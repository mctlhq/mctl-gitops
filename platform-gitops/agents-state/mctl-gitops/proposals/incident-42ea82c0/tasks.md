# Tasks: incident-42ea82c0

1. [ ] Find the admins-umami-retention CronJob manifest or chart template (grep "umami-retention" and "DO $").
2. [ ] Replace `DO $$ ... $$;` with a named tag (`DO $retention$ ... $retention$;`) or move the SQL to a ConfigMap run with `psql -f`.
3. [ ] Verify the rendered manifest contains the full dollar-quote delimiters (helm template) and no lone `$`.
