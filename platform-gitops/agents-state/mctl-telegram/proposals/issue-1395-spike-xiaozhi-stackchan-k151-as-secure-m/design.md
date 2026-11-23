# Design: issue-1395-spike-xiaozhi-stackchan-k151-as-secure-m

Research spike. This document is the decision package. It changes no code and authorizes nothing.

## Current state

### mctl-telegram (clone at `8b369cd9fa4b9d5b1651acbfb0d31225ca17e547`)

- **PA identity is Telegram-only by construction.** `internal/pa/ingress.go`: `Filter(body)` produces a `VerifiedUpdate`, and `Principal{telegramID int64}` is unexported and set only there. `internal/pa/context.go`: `NewInteractive(u VerifiedUpdate, ...)` is the only constructor of `ExecutionContext`. It requires a principal, a conversation id, a `BudgetReservation` and `consentVersion == ConsentDataFlowV1`. `Trigger` is `interactive|scheduled|event`, and `Policy` deliberately has no trigger accessor. There is no "device" trigger or principal kind, and adding one is an ADR-level change to I2.
- **Threat model invariants** (`docs/agent-runtime/personal-assistant-threat-model.md`, lines 20-37): I1 credentials stay on the server; I2 identity only from Telegram; I3 confirmed connections; I4 re-check before dispatch; I5 writes need an out-of-model decision; I6 external content never removes a gate; I7 pin drift is denied; I8 pinned HTTPS egress; I9 failed read is an error; I10 lookups keyed by `(principal,id)`. T11 kill switches (`PA_ENABLED`, `PA_EXTERNAL_TOOLS_ENABLED`, `PA_WRITES_ENABLED`, `PA_SERVER_<NAME>_ENABLED`, `PA_ALLOWED_PRINCIPALS`, `set_pa_principal_disabled`) are re-checked at every dispatch. T13 consent `pa-data-flow/v1` names one recipient (the managed pool model on Nebius through Cloudflare AI Gateway). Any new recipient keeps v1 only if the data flow is unchanged.
- **ADR 0011** (`docs/adr/0011-personal-assistant.md`): the PA is a Bot API bot. It has a `disclosure` class (`alice_say_phrase`, `alice_send_command`) that is never lowerable, because speaking a private chat aloud must always be an explicit decision. The catalog pin is `internal/pa/catalog/pin.json`, schema `mctl-telegram.pa-catalog-pin/v1`. It holds per-tool tier, class, lowerable flag and schema/description hashes.
- **Pairing precedent.** `internal/oauth/local_bridge_activate.go` implements an RFC 8628-shaped device activation. The CLI submits a claim plus an Ed25519 `device_registration_key`. The user enters a non-URL-embedded `user_code` in a browser, then signs in through Telegram OIDC (`internal/auth/telegramoidc`) and approves on an explicit consent page; that consent is the only step that writes. The state machine is forward-only (`pending -> awaiting_consent -> resolving -> done`), with per-IP rate limits and TTL sweeps. ADR 0006 adds proof-of-possession renewal, so a copied token alone cannot impersonate the device. This is the closest existing pattern for K151 pairing.
- **Evidence-report precedent.** `internal/mcpprobe/doc.go`: the report type structurally cannot carry tokens, session ids or tool values, and the one tool call is allowed only if annotated read-only. The harness evidence format reuses this principle.
- **Fixtures rule.** `.claude/CLAUDE.md` requires synthetic personas (`Alice`, `Bob`, `Carol`, `Dana`) and no real identifiers.
- No existing code mentions XiaoZhi or StackChan. Voice mentions are limited to attachment handling in `internal/agent/listener`.

### Upstream evidence (X1 seed, gathered with `gh api` on 2026-11-22)

| Repo | Pinned SHA | License (GitHub SPDX) | Notes |
|---|---|---|---|
| `78/xiaozhi-esp32` | `92d400d6374bbe750e0a0188fa969fc4042820c2` | MIT | Board `main/boards/m5stack/stackchan/` exists (`stackchan.cc`, `feetech_scs.cc` with its own `feetech_scs_LICENSE.txt`) |
| `m5stack/StackChan` | `28b9f0c8bd6acd81cb3c70f1a93c3e373b39d400` | none at root | `firmware/LICENSE` is MIT (M5Stack 2026); `server/LICENSE` is MIT, and `server/` is a Go 1.26.3 module `stackChan`; `app/` and `remote/` licenses not checked |
| `m5stack/StackChan-BSP` | `e2f3b02dbe7f28e26a02adc72bef3aa2c545e4a0` | MIT | not read beyond metadata |
| `xinnan-tech/xiaozhi-esp32-server` | `3219a2803906d71e6613d1f9de6af2e41109ee14` | MIT | not read beyond metadata |

Verified from source at `92d400d6`:
- `main/protocols/websocket_protocol.cc` (`OpenAudioChannel`, about lines 79-106) reads `url`, `token` and `version` from NVS namespace `websocket`. It sets `Authorization: Bearer <token>`, `Protocol-Version`, `Device-Id = SystemInfo::GetMacAddress()` and `Client-Id = Board::GetUuid()`. It sends `hello` and waits for the server `hello`, failing if none arrives. Binary protocol versions 2 and 3 have explicit headers (lines 29-41).
- `main/ota.cc`: the default OTA URL comes from `CONFIG_OTA_URL`, which `main/Kconfig.projbuild` sets to `https://api.tenclass.net/xiaozhi/ota/` (vendor cloud), overridable through NVS `ota_url`. The OTA response's `websocket` object is copied key by key into NVS (lines 203-219). **Whoever answers OTA therefore controls the device's gateway URL and bearer token.** The response can also carry `mqtt`, `firmware.url` and `activation{message,code,challenge,timeout_ms}`.
- Activation v2 (`Ota::GetActivationPayload`, about lines 490-525) applies an HMAC-SHA256 over the server challenge with eFuse `HMAC_KEY0` and posts `{algorithm, serial_number, challenge, hmac}` to `<ota>/activate`. If no textual eFuse serial exists, it falls back to "activation v1" with no hardware proof. The key is provisioned out of band, so a self-hosted verifier does not hold it.
- `stackchan` board `config.json`: `esp32s3`, `CONFIG_USE_HOTSPOT_WIFI_PROVISIONING=y`, GC0308 camera, emote assets. The board README documents CoreS3, AW88298/ES7210 audio, two Feetech SCS0009 servos whose power is gated by PY32 pin 0, and flashing with `idf.py flash` after a 3 s reset hold.

Documentation-only (from `docs/websocket.md` and `docs/mcp-protocol.md` at main; X1 must re-verify at the SHA):
- Device hello `{type:"hello",version,transport:"websocket",features{mcp,aec?},audio_params{format:"opus",sample_rate:16000,channels:1,frame_duration:60}}`. The server hello must echo `transport`, may set `session_id`, and may set a downlink `audio_params` (for example 24000 Hz). Default hello timeout is 10 s.
- Messages: `listen{state:start|stop|detect, mode:auto|manual|realtime, text?}`, `abort{reason}`, `stt{text}`, `llm{emotion,text}`, `tts{state:start|stop|sentence_start,text?}`, `mcp{payload}`, `system{command:"reboot"}`, `alert`, `custom` (compile flag), and the deprecated `iot`.
- MCP: **the device is the MCP server and the gateway is the client.** The envelope is JSON-RPC 2.0. `tools/list` uses cursor pagination, and `withUserTools` is a visibility filter, not authorization. Tools include `self.audio_speaker.set_volume` and `self.camera.take_photo`. The doc references both `2024-11-05` initialize and a modern `2026-07-28` stateless form.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: image `0.142.0`; ingress hosts `tg.mctl.ai`, `labs-mctl-telegram.mctl.ai`; no `PA_*` or `AGENT_RUNNER` key present. With `PA_ENABLED` defaulting to false (`internal/config/config.go:646`), the PA is off.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: image `main-8b369cd`; host `tg-preview.mctl.ai`; no `PA_*` key present.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-alice/values.yaml`: image `2.16.0`, `replicaCount: 1`. This confirms mctl-alice is a separate labs service.
- No service named xiaozhi, voice or desk-agent exists under `services/`.
- mctl MCP tools were not called. The gitops checkout was sufficient for the read-only facts above, and live pod state is irrelevant to a research spike.

## Proposed solution

### Decision package

**Recommendation: `GO_FOR_HARNESS_ONLY` (Option A), everything else `DEFER`.**

| Gate | Severity | Blocks | Evidence |
|---|---|---|---|
| G-ID: no verifiable hardware identity for a self-hosted gateway; the bearer token is static in NVS and rewritten by whoever answers OTA | P1 | K151 purchase for PA use, any real principal | `ota.cc` lines 203-219 and 490-525; `websocket_protocol.cc` lines 79-106 |
| G-DISC: voice output is a broadcast channel; wake word and proximity do not establish the listener | P1 | any private data on device; any PA tool beyond the synthetic stub | threat model T6, ADR 0011 `disclosure` class |
| G-ADR: I2 and T13 must be amended (device principal kind, new data recipients for ASR/TTS) | P1 | any shared PA runtime use | `internal/pa/context.go` `NewInteractive`; T13 |
| G-VENDOR: default OTA is vendor cloud; factory firmware reconfiguration is unverified | P2 | hardware bring-up | `Kconfig.projbuild` `OTA_URL` |
| G-LIC: `m5stack/StackChan` has no root license; the `app/` and `remote/` parts are unchecked | P2 | forking StackChan code (Option C) | GitHub license API |
| G-TLS: `ws://` acceptance and cert pinning are unverified | P2 | any non-loopback gateway | X1 |
| G-MEASURE: latency and cost targets are proposed, not measured | P3 | productization | X4 |

A harness needs no device, no identity and no network credential, so none of the P1 gates blocks it. That is why `GO_FOR_HARNESS_ONLY` is the honest maximum.

### Target architecture (Option A, for the harness and any later pilot)

```
[K151 / simulator] --WSS (XiaoZhi v1/v3 framing)--> [Desk gateway]  -- trust boundary B1
    device = dumb terminal: mic Opus up, Opus down, emotion, no tools of its own used
[Desk gateway] --> ASR -> intent -> one pinned read-only tool -> TTS   -- boundary B2 (providers)
[Desk gateway] --(later, after G-ADR)--> PA executor via a new device trigger   -- boundary B3
```

- The **gateway is a separate service and repo** (for example `mctl-desk-gateway`), not a package in mctl-telegram. This repeats ADR 0011's blast-radius split, and it keeps the MTProto pool and the PA webhook out of reach of an internet-exposed audio socket. mctl-telegram gains nothing in the spike.
- **The gateway runs its own OTA endpoint.** The device's `ota_url` points at the gateway (set once at flash or by hotspot provisioning), so the vendor cloud is never contacted. The OTA response supplies `websocket.url` and a short-lived `websocket.token` (TTL of 15 minutes or less), re-minted on every boot check-in, and only after the device proves possession of its enrolled key.
- **Device MCP is used only as a control plane**, and only for allowlisted, non-sensitive device tools (for example `self.audio_speaker.set_volume` within a ceiling). The gateway never forwards device `tools/list` to a model as callable tools in the experiment. Device tool descriptions are untrusted (`withUserTools` is not authorization).

### Identity and pairing (threat-model delta, G-ID)

1. **Device key.** A software Ed25519 key generated on the device, or a gateway-assigned enrollment secret if the stock firmware cannot generate one (X1 decides; stock firmware only knows an opaque bearer string). Residual risk: there is no flash-encryption evidence, so physical extraction is possible. This is recorded, not accepted.
2. **Pairing**, modelled on `local_bridge_activate.go`. The device displays a short `user_code` on its 320x240 screen and speaks nothing. The user opens the pairing page, signs in with Telegram OIDC (an existing I2 source), sees the device label and fingerprint, and approves. Consent is the only write. TTL is 5 minutes, single use, rate-limited per IP, and the state machine is forward-only.
3. **Credentials.** The device holds only its key and a 15-minute-or-shorter gateway token with audience `desk-device`. It never holds an OAuth token, a PA job token or a downstream credential (keeps I1).
4. **Revocation.** Unpair revokes locally first, bumps a `device_authority_revision`, closes the socket and refuses the next OTA mint. Every tool dispatch re-checks the revision (mirrors I4 and T2 fencing). A lost or stolen device is unpaired from the Telegram side. A compromised device is treated as untrusted input forever (I6).
5. **Device authentication is not person authentication.** The paired principal is the *owner of the device*, never "the speaker". In the experiment the device may only reach data that is safe for anyone in the room to hear: public or synthetic. This is G-DISC. Any later private read needs a confirmation path through the paired owner's Telegram chat (verified `callback_query`) before the device speaks, plus a headset or "display-only" mode. That later step is a separate threat model.

### Invariant-by-invariant delta

| Control | Device path |
|---|---|
| I1 credentials on server | Kept: the device holds only a short device token |
| I2 Telegram identity | **Changed (ADR addendum).** A new principal source, "paired device of principal P", which is only ever derived from a Telegram-verified pairing; the device is never its own principal |
| I3 confirmed connections | Kept: pairing has an explicit consent step |
| I4 / I10 re-check, keyed lookups | Extended with `device_authority_revision` |
| I5 writes | No writes in scope; a future device write would be `never` until its own review |
| I6 provenance | **All ASR output is `external`**, so a voice run is tainted from the first turn: spoken text is not "text the principal typed" (T5) |
| I7 pin | One pinned synthetic tool in a gateway-side pin, same schema as `pin.json` |
| I8 egress | Gateway egress allowlist: ASR, TTS and LLM hosts only |
| I9 fail closed | Kept: unknown device state refuses |
| T11 switches | New independent `DESK_ENABLED` and `DESK_DEVICE_<id>` disable, plus the PA switches if B3 is ever used |
| T12 audit | Digest-only events per turn, in the ADR 0003 chain style; no audio or transcript stored |
| T13 consent | **New consent version** (for example `desk-voice-data-flow/v1`), because audio goes to ASR and TTS recipients that `pa-data-flow/v1` does not name |
| `ExecutionContext` | A new trigger or constructor (for example `NewDevice`) would be needed; no change in this spike |
| Budget | Per-device and per-principal ledger cap; ADR 0008 reservation pattern |

### Harness design (X3, specification only)

- **Location:** the future gateway repo, `test/xiaozhi-sim/`. It runs as Go tests: `go test ./test/xiaozhi-sim/... -run TestSim -count=1`. Loopback only, with no environment credentials, and the tests refuse to start if a variable named `*TOKEN*` or `*API_KEY*` is set to a non-fixture value.
- **Simulated device:** it speaks the XiaoZhi WebSocket protocol, v1 and v3 framing, with the headers above. Fixture values: MAC `02:00:00:00:00:01` (locally administered), `Client-Id` a fixed UUIDv4, persona `Dana` as the paired owner, and a synthetic Telegram id taken from the existing fixtures after a `git grep`.
- **Audio fixtures:** deterministic. Either pre-encoded Opus frames with SHA-256 recorded in `fixtures/manifest.json`, or a "codec stub" mode with tagged opaque frames, so the assertions do not depend on libopus.
- **Stub pipeline:** ASR stub maps a fixture hash to a transcript; the intent stub maps it to the single tool `desk_build_status` (synthetic, read-only, returns canned JSON); the TTS stub emits N tagged frames.
- **Assertions (minimum set):** S-H1 server hello within 10 s, with `transport` echoed and `session_id` set; S-H2 a hello with an unknown version or missing `audio_params` is refused with a safe error; S-A1 a missing, expired or revoked token is refused before hello; S-L1 the `listen start -> stt -> tts start -> sentence_start -> stop` ordering holds; S-I1 `abort{reason:"wake_word_detected"}` during TTS stops downlink within 200 ms of simulated time; S-R1 a reconnect gets a new `session_id` and the old session's late frames are discarded (fenced); S-M1 device `mcp` responses that are malformed, oversized (over 64 KiB) or carry an unknown id are dropped without a crash; S-M2 a device tool absent from the allowlist is never called; S-T1 a transport stall drives the idle timeout to a clean close; S-P1 no transcript, token or audio byte appears in logs or reports; S-X1 no outbound dial except loopback (checked with a dialer guard).
- **Evidence format:** `report.json` modelled on `internal/mcpprobe`. It holds labels, upstream SHAs, protocol versions, assertion ids, pass/fail, durations and counts, and it has no field that can hold a token or text. Verdict values are `protocol_compatible_sim` or `incompatible`. `k151_tested` is not a value the simulator can emit.

### Product validation (X4, proposed targets, not results)

- Use case U1: "summarize public MCTL build/release status" (synthetic release fixture in the harness; a public source only in a later pilot).
- Use case U2: "describe synthetic GitHub issue state" (canned fixture).
- Targets for the later pilot: wake-to-first-audio p50 of 1.5 s or less; end-to-end task p50 of 3 s or less and p95 of 6 s or less; task success of 90% or more over 50 scripted turns; barge-in stop of 300 ms or less; reconnect recovery of 5 s or less; false activations of 1 or fewer per 8 h of ambient audio; cost of $0.50 or less per 100 turns (ASR + LLM + TTS), Russian-first.
- Go criteria. Harness GO: this package is accepted. One-K151 purchase GO: the harness is green, G-VENDOR and G-TLS are resolved, and the G-ID residual is accepted by the owner. Productization: G-ADR merged, G-DISC threat model accepted, and pilot targets met.

## Alternatives

- **B: sandbox the community `xiaozhi-esp32-server` (MIT, `3219a280`) behind an adapter.** Pros: full feature set (ASR/TTS plugins, OTA, management UI) and an existing Russian-capable provider plugin ecosystem. Cons: a large foreign surface with its own auth, plugin model and outbound integrations (unread). That conflicts with I8-style egress pinning and would need a deep audit and continuous fork tracking. Not chosen for the harness. It is kept as a reference implementation that X1 reads.
- **C: purpose-built firmware or an alternate protocol on StackChan.** Pros: real hardware identity (a self-burned eFuse HMAC key, flash encryption, TLS pinning), and the only route that closes G-ID fully. Cons: firmware maintenance and an OTA and recovery burden, the G-LIC gap at the StackChan root, no compatibility with other XiaoZhi devices, and hardware needed from day one. Deferred. It is the likely answer if the owner refuses the G-ID software-key residual.
- **Reuse mctl-alice or the PA bot directly.** Rejected. mctl-alice is a Yandex Alice MCP server, and the PA is Telegram-identity-only by construction (`NewInteractive`). Grafting a device onto either would silently grant a device PA authority.
- **Use xiaozhi.me or StackChan World cloud.** Rejected under the issue's non-goals: it is a vendor cloud dependency, and audio leaves MCTL governance.

| Criterion | A minimal gateway | B community server | C custom firmware |
|---|---|---|---|
| Security surface | Small, ours | Large, foreign | Smallest device side, most work |
| Hardware identity | Software key (residual) | Same | Strong (eFuse, own key) |
| Maintenance | Medium | High (fork tracking) | High (firmware) |
| License | MIT upstream, own code | MIT | Unclear at StackChan root |
| Latency | Tunable | Tunable | Tunable |
| ASR/TTS choice and Russian | Pluggable, ours | Many plugins | Pluggable |
| PA compatibility | Via ADR addendum | Via adapter and addendum | Via addendum |
| Needs hardware for first evidence | No | No | Yes |

## Platform impact

- Migrations: none. Backward compatibility: no code or config changes in any repo. Resources: none; the harness is CI-only and loopback-only when later built.
- Risk: the spike is read as approval to build a gateway or link it to the PA. Mitigation: status `proposed`, a recommendation limited to the harness, and G-ADR as an explicit P1 barrier.
- Risk: upstream drift. `78/xiaozhi-esp32` was pushed 2026-11-21. Mitigation: every claim is pinned to a SHA, and the harness records the upstream SHA in `report.json`.
- Risk: fixtures leak real identifiers. Mitigation: the `.claude/CLAUDE.md` persona rule, locally administered MACs and the S-P1 assertion.
