# Spike: XiaoZhi / StackChan K151 as a secure MCTL Desk Agent voice client (research only)

## Revision 2 review gate (2026-11-23)

Independent review: https://github.com/mctlhq/mctl-telegram/issues/1395#issuecomment-7087951153. The first implementation of a **separately owner-authorized B1 software-only harness** lives in https://github.com/mctlhq/mctl-telegram/issues/1409 and draft https://github.com/mctlhq/mctl-telegram/pull/1410. The old #1395 Temporal approval path must **not** be used: it activates the broad Tier 2 implementer. Research acceptance, a test-only harness branch, hardware bring-up, PA integration and production are **five distinct decisions**. This proposal remains `proposed` and authorizes no extra activity.

The P1 real-device blockers G-ID (device identity), G-DISC (spoken disclosure) and G-ADR (PA principal and consent model) remain hard **DEFER**. Upstream binary downlink parsing additionally requires firmware bounds review before any physical device is permitted. Green internal simulation is **not** third-party interoperability, hardware safety or PA approval.

## Context

Issue #1395 asks for a research-only spike. The question is whether XiaoZhi-compatible ESP32 devices could become a self-hosted, secure "MCTL Desk Agent" voice surface for the MCTL Personal Assistant (PA) ecosystem. The first reference device is the M5Stack StackChan K151. The deliverable is an evidence-backed decision package: a protocol and licensing evidence pack, an architecture comparison, an identity and threat-model delta, a no-hardware protocol harness design and product validation criteria. It ends with a recommendation of `GO_FOR_HARNESS_ONLY`, `DEFER` or `NO_GO`. The spike implements nothing, deploys nothing, enrolls no device and buys no hardware.

This matters because the PA (epic #1312, `docs/adr/0011-personal-assistant.md`, `docs/agent-runtime/personal-assistant-threat-model.md`) was designed with a single identity source. Invariant I2 says the principal is the Telegram user id from a filtered Bot API update, a verified `callback_query` or verified Mini App `initData`. In code, `pa.NewInteractive` in `internal/pa/context.go` accepts a principal only from a `VerifiedUpdate` (`internal/pa/ingress.go`). A voice device has none of these, and the evidence gathered for this proposal shows the XiaoZhi firmware's own identity signals are not identity. `Device-Id` is the MAC address. `Client-Id` is a UUID that is reset on reflash. The WebSocket bearer token is an opaque string the OTA endpoint writes into NVS. A device path therefore needs its own ADR and threat-model addendum before it may touch any PA runtime. In XiaoZhi, "MCP" also runs in the opposite direction from MCTL's catalog: the device is the MCP server and the backend is the client (`docs/mcp-protocol.md` at the pinned revision). So the device cannot "call MCTL tools" directly.

**Research recommendation: Option A is a candidate; conditional `GO_FOR_HARNESS_ONLY` applies solely to the standalone B1 scope in #1409, with no broad implementer signal.** Three P1 gates block anything beyond the harness: G-ID, G-DISC and G-ADR (see design.md, "Decision package").

## User stories

- AS the platform owner I WANT an evidence-backed GO / NO-GO / DEFER package SO THAT I can decide whether to fund a protocol harness, buy a K151, or stop, without any code or credentials reaching production.
- AS a security reviewer I WANT the identity, authority and disclosure delta against PA invariants I1-I10 written down explicitly SO THAT no device inherits the PA's permissions silently.
- AS a future implementer I WANT a reproducible, credential-free protocol simulator specification (commands, fixtures, assertions, evidence format) SO THAT "protocol compatible" can be proven in CI before any physical device exists.
- AS a product owner I WANT two concrete read-only use cases with proposed latency, success and cost targets SO THAT a later pilot has objective go/no-go criteria.

## Acceptance criteria (EARS)

Evidence (X1)
- WHEN the evidence pack is produced THE SYSTEM SHALL pin each upstream by full commit SHA and SPDX license: `78/xiaozhi-esp32`, `m5stack/StackChan`, `m5stack/StackChan-BSP`, `xinnan-tech/xiaozhi-esp32-server`. It SHALL cite file paths at those SHAs for every protocol claim.
- WHEN a protocol property is stated (hello fields, headers, binary framing v1/v2/v3, listen/abort/tts/stt/llm/mcp/system message types, Opus parameters, OTA/activation, MQTT+UDP) THE SYSTEM SHALL mark it either as verified from source at the pinned SHA or as documentation-only and unverified.
- IF an upstream repository has no root license (as GitHub reports for `m5stack/StackChan` at `28b9f0c8`) THEN THE SYSTEM SHALL record the per-directory licenses it found and SHALL list the unlicensed parts as a P2 blocker for any fork or redistribution.
- THE SYSTEM SHALL state explicitly that XiaoZhi MCP is device-as-MCP-server, JSON-RPC 2.0 inside `{"type":"mcp","payload":...}`, and is not MCTL MCP tool execution.

Architecture and security (X2)
- WHEN the architecture comparison is written THE SYSTEM SHALL compare at least Options A, B and C on security, maintenance, licenses, fork surface, latency, running cost, local and remote ASR/LLM/TTS, Russian-first multilingual support, interruption, privacy, fleet management and PA compatibility, with no option preselected without stated evidence.
- THE SYSTEM SHALL NOT treat the MAC (`Device-Id`), `Client-Id`, a device-supplied serial number, wake-word detection, proximity or voice audio as the identity of a person or of a device.
- WHEN device pairing is proposed THE SYSTEM SHALL bind the device to a principal verified by an existing I2 source (Telegram OIDC or Mini App `initData`), through a one-time, short-TTL, consent-gated pairing modelled on the Local Bridge activation flow (`internal/oauth/local_bridge_activate.go`). It SHALL define rotation, revocation, lost or stolen device handling and revocation fencing.
- WHILE a device is paired THE SYSTEM SHALL hold no user OAuth token, PA job token or downstream credential in firmware or NVS. Only a device-scoped, short-lived, revocable gateway credential is allowed.
- WHILE the experiment is in scope THE SYSTEM SHALL allow only one synthetic read-only tool, served by a stub with no external credentials. It SHALL allow no write tool, no device-side MCP tool call that actuates the speaker, servos or camera on the user's behalf, and no spoken disclosure of private Telegram content.
- THE SYSTEM SHALL list, for each PA invariant I1-I10 and each control (consent `pa-data-flow/v1`, provenance and taint, ADR 0003 audit, budget, `ExecutionContext`, catalog pin, kill switches), whether a device path keeps it, changes it or needs an addendum.

Harness (X3)
- WHEN the simulator design is produced THE SYSTEM SHALL specify: commands; deterministic fixtures (synthetic Opus frames or a deterministic codec stub); assertions for hello and handshake (including the 10 s hello timeout), the session lifecycle, listen start/stop/detect, abort and interrupt, reconnect, MCP control messages, malformed and oversized payloads and transport timeouts; and a redaction-safe evidence report format.
- THE SYSTEM SHALL keep the result "protocol compatible (simulator)" separate from "actual K151 tested". It SHALL NOT report the second without a physical-device run under a separate GO.
- IF a harness run needs a network credential, a vendor endpoint (for example the firmware default OTA URL `https://api.tenclass.net/xiaozhi/ota/`) or a real Telegram identifier THEN the design SHALL be considered non-compliant.

Product validation (X4)
- WHEN the validation plan is written THE SYSTEM SHALL define two read-only use cases over synthetic or public data, and proposed (not measured) targets for wake-to-first-audio, end-to-end latency p50/p95, task success, interruption handling, reconnect recovery, false activation and cost per 100 turns.
- THE SYSTEM SHALL define explicit go/no-go criteria for (a) building the harness, (b) buying one K151 and (c) productizing.

Governance
- THE SYSTEM SHALL leave this research proposal at status `proposed`. The separately approved #1409 test-only branch does not authorize the #1395 Temporal implementer, deployment, preview exposure, device enrollment, firmware flash, credential issue or procurement.

## Out of scope

- Any gateway implementation, deployment, preview, Helm or gitops change, and any `PA_*` flag change. The PA is off in both deployed instances: no `PA_*` variable is set in `services/labs/mctl-telegram/values.yaml` or `services/labs/mctl-telegram-preview/values.yaml`, and `PA_ENABLED` defaults to false in `internal/config/config.go`.
- Firmware flashing, device purchase, enrollment against xiaozhi.me or StackChan World, and accepting any vendor cloud dependency.
- Private chat content in any form: read, summarised or spoken. Telegram writes, Alice actions, speaker or servo writes on the user's behalf.
- PA Phase 2 activation, approvals for voice, and any change to `internal/pa/*` code.
- Changing mctl-alice. It is a Yandex Alice MCP server (`services/labs/mctl-alice`), not a generic voice backend, and is not reused as the gateway.
- Owner GO itself. This proposal only prepares the evidence for one.

## Open questions

- Gateway home: inside mctl-telegram (next to `internal/pa`) or a separate service? The proposal recommends a separate repo or service for the harness and any later gateway, to keep the PA blast radius separate (ADR 0011 already isolated the PA bot from the login bot for this reason). The owner must confirm.
- Device-identity root: firmware activation v2 uses an eFuse `HMAC_KEY0` challenge (`main/ota.cc`, `Ota::GetActivationPayload`), but that key is provisioned by the vendor and a self-hosted gateway cannot verify it. Is a software Ed25519 key in NVS acceptable, given that StackChan's firmware does not demonstrate flash encryption? Or does the pilot require custom firmware with a self-burned key (Option C)? The proposal records this as P1 blocker G-ID and proceeds with "software key plus pairing plus short-lived credential, residual risk documented".
- Does the K151 factory firmware (StackChan World) allow a custom OTA or WebSocket URL without reflashing, or does only the `78/xiaozhi-esp32` `m5stack/stackchan` board build allow it? Not verified. M5Stack's documentation page was not read for this proposal.
- `xinnan-tech/xiaozhi-esp32-server` internals (auth, plugin isolation, outbound endpoints) were pinned (`3219a280`, MIT) but not read. Option B's security rating is provisional until X1 reads them.
- Can the firmware use a `ws://` (plaintext) URL, and does it pin TLS certificates? Not verified at the pinned SHA. It must be answered in X1.
- Russian ASR/TTS provider choice, and whether audio may leave the managed AI gateway path. Any new recipient breaks the `pa-data-flow/v1` consent scope (threat model T13), so it would need a new consent version.
