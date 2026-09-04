# Security amendments for issue #483

These amendments were found during pre-approval review against the merged #482/#490 code and are **authoritative** for implementation. Where they conflict with `requirements.md`, `design.md`, or `tasks.md`, these amendments win until those files are consolidated.

## A1 — Device credentials must never use legacy worker-token renew

The existing `POST /api/mcp/worker-token/renew` path accepts `mcp-worker-bridge`, copies scopes from the presented JWT, uses the legacy worker-token TTL policy, and currently does not preserve `Claims.DeviceID`. A #483 device credential must therefore be distinguishable from a legacy admin-minted Local Bridge worker token.

Required contract:

- A device-bound credential minted by `MintForDevice` MUST NOT be renewable through `POST /api/mcp/worker-token/renew`.
- Prefer a dedicated device credential audience/marker (for example `mcp-device-bridge`) that the legacy renew handler never accepts. If the implementation keeps an existing audience for compatibility, `NewRenewHandler` MUST explicitly reject any presented token with non-empty `Claims.DeviceID` before minting.
- The PoP `/refresh` endpoint is the only renewal path for device-bound credentials.
- Legacy admin-minted Local Bridge worker tokens without `DeviceID` MUST keep their existing `/renew` behavior unchanged.

Required regression:

1. Mint a device credential.
2. Present it to `/api/mcp/worker-token/renew`.
3. Assert rejection and no token minted.
4. Present an existing legacy Local Bridge worker token without `DeviceID` and assert legacy renew still succeeds.

## A2 — One stable revocable credential lineage per device

`current_jti` with last-write-wins is insufficient if each PoP refresh creates a fresh JTI: older still-live credentials would survive device revocation.

Required contract:

- The first successful self-service issuance creates a stable device credential lineage identifier/JTI.
- Every PoP refresh for that device MUST carry the same lineage JTI forward rather than generate a new JTI.
- Device revocation deny-lists that stable lineage once, invalidating every still-live worker/device credential and every derived token that carries the lineage.
- Concurrent refreshes MUST NOT create independently revocable lineages for the same device.
- The DB column should reflect the stable lineage semantics (rename from `current_jti` to `credential_jti` or equivalent if useful); it must not mean "latest token only".

Required regression:

1. Issue credential A.
2. PoP-refresh to B, then C.
3. Revoke the device.
4. Assert A, B, and C are all rejected wherever worker/device credentials are accepted.
5. Assert bridge tokens derived from any of A/B/C are also rejected by revocation checks.

## A3 — DeviceID must survive bridge-token derivation

The current `POST /api/bridge/token` implementation carries parent `Jti` and `OriginalIssuedAt` into the child `aud=bridge` JWT, but not `DeviceID`. Without the copy, websocket authentication produces an identity with an empty device id and `Hub.EvictDevice(userID, deviceID)` cannot match the live connection.

Required contract:

- `auth.Identity` MUST carry `DeviceID` from a verified device credential.
- `NewBridgeTokenHandler` MUST copy `DeviceID: id.DeviceID` into the derived `aud=bridge` token.
- The bridge-token verifier MUST restore that claim into `auth.Identity`.
- `/bridge` MUST register the live daemon as `(userID, deviceID)`.
- Device revocation MUST actively evict the matching live websocket while leaving another device for the same user untouched.

Required integration regression:

`device credential -> /api/bridge/token -> /bridge websocket -> revoke_local_bridge_device -> matching socket closed`, with the asserted `DeviceID` preserved in the derived bridge token and authenticated identity.

## Approval gate

Do not approve #483 until A1-A3 are represented in the implementation task list and tests. These are not follow-up hardening items: each one otherwise creates a direct bypass of #483's stated PoP/device-revocation guarantees.
