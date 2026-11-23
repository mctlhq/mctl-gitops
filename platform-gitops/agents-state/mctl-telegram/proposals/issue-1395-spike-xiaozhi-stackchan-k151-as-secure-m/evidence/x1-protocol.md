# X1 source-pinned XiaoZhi protocol evidence (partial, revision 2)

Evidence collected from upstream repositories at immutable refs. Facts not observed in the source are marked unknown, never silently accepted.

| Source | Pinned SHA | Evidence | Confidence |
|---|---|---|---|
| `78/xiaozhi-esp32` | `92d400d6374bbe750e0a0188fa969fc4042820c2` | `main/protocols/websocket_protocol.cc:79-106`: reads NVS `websocket.url/token/version`, adds authorization and `Protocol-Version` / MAC / UUID headers | source verified |
| same | same | `main/protocols/websocket_protocol.cc:187-200`: sends client hello and waits 10s for server hello | source verified |
| same | same | `main/protocols/websocket_protocol.cc:210-259`: client hello `opus`, 16kHz mono; server `session_id` and `audio_params` are optional | source verified |
| same | same | `main/protocols/websocket_protocol.cc:29-52,110-135`: v1 raw, v2/v3 framed; binary receive uses advertised size without visible `len` check | source verified; hardware P1 |
| same | same | `main/ota.cc:60-68,203-219`: OTA URL from settings/default; OTA response WebSocket settings copied into NVS | source verified |
| same | same | `main/ota.cc:490-525`: activation v2 HMAC with vendor-provisioned eFuse key; v1 fallback exists | source verified |
| same | same | `main/mcp_server.cc:443-595`: device implements MCP server-side tools/list/call and modern capability validation | source verified |
| same | same | `docs/mcp-protocol.md:1-100,105-258`: gateway is MCP **client**, device MCP **server**; modern `2026-07-28` discovery, legacy `2024-11-05` initialization and paginated list | source documentation verified |
| same | same | `main/boards/m5stack/stackchan/README.md:1-51`: CoreS3, Feetech servos, build/flashing, servo-power gate | source documentation verified |
| same | same | `main/protocols/mqtt_protocol.cc:83-150`: MQTT settings, control connection and reconnect code exist | source verified (full security not audited) |
| `m5stack/StackChan` | `28b9f0c8bd6acd81cb3c70f1a93c3e373b39d400` | `README.md:5-19` lists CoreS3 and factory firmware; `firmware/LICENSE` MIT; `remote/code/LICENSE` MIT; `app/README.md` displays MIT badge but no `app/LICENSE` was found at directory root (cannot establish unambiguous app redistribution scope) | partial |
| `m5stack/StackChan-BSP` | `e2f3b02dbe7f28e26a02adc72bef3aa2c545e4a0` | `README.md:7-32` lists hardware and license MIT | source documentation verified |
| `xinnan-tech/xiaozhi-esp32-server` | `3219a2803906d71e6613d1f9de6af2e41109ee14` | `README.md:9,173-185,201-238,281-303` documents WebSocket/MQTT, plugin ASR/TTS and self-hosting | documentation verified; auth and egress **unreviewed** |

Important upstream URLs:
- https://github.com/78/xiaozhi-esp32/blob/92d400d6374bbe750e0a0188fa969fc4042820c2/main/protocols/websocket_protocol.cc
- https://github.com/78/xiaozhi-esp32/blob/92d400d6374bbe750e0a0188fa969fc4042820c2/main/ota.cc
- https://github.com/78/xiaozhi-esp32/blob/92d400d6374bbe750e0a0188fa969fc4042820c2/docs/mcp-protocol.md
- https://github.com/m5stack/StackChan/tree/28b9f0c8bd6acd81cb3c70f1a93c3e373b39d400
- https://github.com/xinnan-tech/xiaozhi-esp32-server/tree/3219a2803906d71e6613d1f9de6af2e41109ee14

### Explicit unknowns (do not claim resolved)

1. K151 **factory firmware** URL override and cloud-free initial activation without reflashing: `m5stack/StackChan/firmware/main/Kconfig.projbuild:1-20` confirms the StackChan source build's default OTA endpoint is the vendor URL and is build-configurable, **not** proof that a retail preloaded device exposes reconfiguration without a flash.
2. TLS verification / certificate pinning on every K151 network transport, and whether plaintext `ws://` is accepted.
3. Self-hosting community server's detailed auth, egress and plugin isolation.
4. `remote/code/LICENSE` at pinned SHA is MIT. App README *claims* MIT via badge but `app/LICENSE` and root LICENSE are absent; the application licensing scope and any third-party assets still need formal verification.
5. A secure stock device key/rotation path, post-OTA token expiry handling, physical extraction protection.
6. Actual Russian voice provider behavior/cost and verified end-to-end latency on K151.

These are B2/B3 gates. The isolated #1409 simulator deliberately does not require resolving them to run.
