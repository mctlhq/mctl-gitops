# Tasks: incident-a436160e

1. [ ] Confirm current state: check whether the `telegram_accounts` row for
       `telegram_login_id = '8745115872'` (tenant labs, mctl-telegram DB) is
       still `mode = 'local'` and `revoked_at IS NULL`. If it is already
       `'hosted'` or the row is revoked, close this proposal as a no-op
       instead of applying the edit below.
2. [ ] Edit `platform-gitops/services/labs/mctl-telegram/values.yaml`: add a
       new Job named `labs-mctl-telegram-local-mode-restore-1` to the
       `extraObjects` list (alongside the existing
       `labs-mctl-telegram-local-mode-flip-1` Job), setting
       `telegram_accounts.mode = 'hosted'` (instead of `'local'`) for the
       same user/account resolution logic the flip Job uses, with the same
       `RETURNING id` / empty-result-fails pattern and the same
       securityContext / postgres:17-alpine image / env wiring
       (PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD from
       `labs-mctl-telegram-db-creds`).
3. [ ] Verify the new Job's SQL is a minimal diff of the flip Job (same
       WHERE clauses, only the SET mode value and Job name/log text differ)
       so the change is easy to review against its counterpart.
4. [ ] No image tag bump needed — this only adds a Job manifest, no
       application code or image change.
5. [ ] After ArgoCD syncs, confirm the Job completes successfully (not
       failed on the empty-result guard) and that the
       `bridge: authentication failed` / `JWT expired` log line stops
       recurring on the `labs-mctl-telegram` base-service pod.
