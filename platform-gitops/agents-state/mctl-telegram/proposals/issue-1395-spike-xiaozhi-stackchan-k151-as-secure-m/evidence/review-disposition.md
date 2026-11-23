# Independent review disposition — revision 2 (2026-11-23)

Original review: https://github.com/mctlhq/mctl-telegram/issues/1395#issuecomment-7087951153

This document records honest dispositions, **not** a blanket clearance of P1 gates. A green synthetic harness is not a safe real-world device or a reviewed PA integration.

| Finding | Status | Disposition / evidence |
|---|---|---|
| P1-GOV | **Addressed for B1 only** | Separate owner-limited issue mctlhq/mctl-telegram#1409 and draft PR #1410. Old #1395 Temporal is **not** approved: its approve starts the broad implementer. No merge. |
| P1-AUTH (real PA/device) | **OPEN hard blocker** | Principal source remains verified Telegram event. XiaoZhi MAC, UUID and bearer are not a person identity. Needs ADR 0011 I2/T13 addendum and explicit user authorization. |
| P1-DEVICE (hardware) | **OPEN hard blocker** | Pinned upstream `websocket_protocol.cc` lines 110–135 cast binary framing without visible `len` bounds check. Requires firmware-side hardening review + actual K151 tests; a safe gateway alone is insufficient. |
| P2-HELLO | **Fixed in spec & synthetic tests** | Upstream `ParseServerHello` lines 230–259 permits missing `session_id` and `audio_params`. Corrected design and added `test_server_hello_optional_fields`. Client hello still has required negotiation. |
| P2-EVIDENCE | **PARTIAL** | Four repo SHAs pinned; source evidence indexed in `x1-protocol.md`. Community server internals, factory cloud override, TLS pinning and M5Stack app/remote redistribution scope remain open. |
| P2-PROTOCOL | **PARTIAL** | #1410 provides synthetic WebSocket framing tests and basic MCP legacy/modern shape checks. An actual upstream device/firmware integration suite, modern discover fallback/pagination, and adversarial firmware fuzzing remain additional acceptance tests. |
| P2-TOKEN | **OPEN hardware blocker** | OTA response writes gateway URL and token to NVS. Token ≤15m is a **proposed gateway policy**, not proven stock-firmware renewal. Require proof-of-possession, expiry/reconnect and replay tests before real pairing. |
| P2-GATES | **Addressed** | Harness verdict `protocol_compatible_sim` expressly means a synthetic fixture pass, not `k151_tested` or `pa_compatible`. #1410 README and docs enforce distinction. |
| P3-MEASURE | **OPEN** | $0.50/100 turns, latency, false wake and Russian provider budgets are unmeasured targets. Source-pinned prices/provider choices required before a product gate. |
| P3-REPRO | **Addressed for current CI** | Draft PR #1410 new HEAD `7269b8fc498ae5326941b955f63153809785ea45` (17 local tests). Initial CI `45090802713` SUCCESS at older HEAD `22e271e3fcf5617897f73ed7dd485b4c5fddd114`; new-HEAD CI pending separate verification; pinned upstream SHA `92d400d6374bbe750e0a0188fa969fc4042820c2`. Re-review must use a **new exact HEAD** if either PR changes. |

## Gates and decisions

- **B1 (CI-only synthetic harness):** owner-limited in #1409; Python 3.13, websockets 16.0. Simulator's local 17/17 is green. The original 14-test HEAD has green GitHub CI; revised HEAD requires its own CI result before declaring gate green. Draft PR remains unmerged, and independent PR review is outstanding.
- **B2 (hardware procurement/flashing):** DEFER pending G-ID, G-VENDOR, G-TLS and P1-DEVICE.
- **B3 (PA identity/consent runtime):** NO-GO pending an accepted ADR and security review.
- **B4 (private/physical writes):** NO-GO pending separate approval and threat model.
- **#1395 Temporal decide:** do **not** send approve; that approval is not a research-completion signal.

## Required next review

Recheck X1 pending evidence against pinned commit sources, inspect security tests in #1410, require independent Claude/Agy or equivalent review **on exact HEAD**, and only then consider merging the isolated harness. This document leaves `.status.yaml` = `proposed`.
