# Secrets map (names only, no values)

| Component | Vault path | ExternalSecret | Target Secret | Consumer |
| --- | --- | --- | --- | --- |
| provider-worker | `teams/mctl-assistants-provider-glovo/provider-worker/temporal` (`credential`) | `glovo-provider-temporal` | `glovo-provider-temporal` | provider worker, identity `mctl-assistants-provider-glovo:write` |
| control-worker | `teams/admins/assistants-control/temporal` (`credential`) | `glovo-control-temporal` | `glovo-control-temporal` | control worker, identity `mctl-assistants:write` |
| facade | none in P0 | none | none | JWT validation uses the public issuer keys |

The paths are proposals. They do not exist in Vault, and P0 creates none.
The Temporal client credential format depends on the #2469 spike outcome.

## Database credentials (A15, #2563; proposals, nothing exists in Vault)

References only, no value. All three roles live on database `mctl-api` of
`shared-pg` (mctl-api#1004 amendment, D1).

| Vault path (proposed) | Role | Consumer |
| --- | --- | --- |
| `platform/mctl-api/glovo-runtime-database` | `glovo_runtime` | mctl-api pod (`GLOVO_DB_URL`) |
| `platform/mctl-api/glovo-migrator-database` | `glovo_migrator` | suspended migration Job only |
| `platform/mctl-api/workitems-database` | `mctl_api_workitems` | mctl-api pod (`WORK_ITEMS_DB_URL`), later switch only |
