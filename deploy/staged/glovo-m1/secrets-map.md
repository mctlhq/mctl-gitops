# Secrets map (names only, no values)

| Component | Vault path | ExternalSecret | Target Secret | Consumer |
| --- | --- | --- | --- | --- |
| provider-worker | `teams/mctl-assistants-provider-glovo/provider-worker/temporal` (`credential`) | `glovo-provider-temporal` | `glovo-provider-temporal` | provider worker, identity `mctl-assistants-provider-glovo:write` |
| control-worker | `teams/admins/assistants-control/temporal` (`credential`) | `glovo-control-temporal` | `glovo-control-temporal` | control worker, identity `mctl-assistants:write` |
| facade | none in P0 | none | none | JWT validation uses the public issuer keys |

The paths are proposals. They do not exist in Vault, and P0 creates none.
The Temporal client credential format depends on the #2469 spike outcome.
