# Tasks: incident-e22f370d

1. [ ] In `mctlhq/mctl-telegram`, find the MTProto client-pool code that logs
       `"idle telegram client, closing"` and determine the current idle-close
       timeout value (hardcoded or already configurable).
2. [ ] If hardcoded, expose it as a new environment variable (e.g.
       `TELEGRAM_CLIENT_IDLE_TIMEOUT`), defaulting to the existing hardcoded
       value so this change alone does not alter behavior.
3. [ ] Add the new env var to `env:` in
       `platform-gitops/services/labs/mctl-telegram/values.yaml`, set to a
       longer idle timeout than the default, to reduce client-recreation churn
       causing slow session borrows. Confirm the choice is reasonable given
       real traffic spacing (do not guess wildly larger).
4. [ ] Verify the change compiles/builds and the new env var is read at
       startup (fails closed or falls back to default if unset/invalid).
5. [ ] Confirm no other values.yaml entries need updating (no image tag bump
       required — this is a config/behavior change, not a breaking API change).
