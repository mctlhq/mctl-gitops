# X3 synthetic harness check — implementation and limits

## Reproducible command

```bash
python -m pip install -r test/xiaozhi-sim/requirements.txt
python test/xiaozhi-sim/run.py
```

Location: draft https://github.com/mctlhq/mctl-telegram/pull/1410 (branch `spike/xiaozhi-protocol-sim-1409`); dedicated workflow `.github/workflows/xiaozhi-sim.yml`, Python 3.13, `websockets==16.0`. No real account or vendor endpoint; software fixture binds `127.0.0.1` on an ephemeral port.

Observed local on 2026-11-23: **17/17 unittest green**, exit 0. Observed original GitHub workflow `45090802713`: **SUCCESS** at `22e271e3fcf5617897f73ed7dd485b4c5fddd114` (14 tests). Revised local **17/17** on branch HEAD `7269b8fc498ae5326941b955f63153809785ea45`; GitHub Actions for this new HEAD must be separately verified.\n\nNew tests: `test_live_mcp_modern_discovery_and_pagination`, `test_live_mcp_legacy_initialize`, `test_live_mcp_modern_method_not_found_legacy_fallback`. Unsolicited MCP messages are always dropped, and invalid JSON-RPC does not trigger legacy fallback.

## Coverage mapping

- Hello contract: `test_server_hello_optional_fields`, `test_correct_hello_and_session_rotation`, `test_invalid_hello_is_rejected`.
- Binary Opus **envelope**, not codec: `test_binary_roundtrip_v1_v2_v3`, `test_binary_truncation_and_forged_length`, `test_malformed_binary_refused`.
- Control plane basic shape: `test_modern_and_legacy_mcp_messages`, `test_mcp_ids_payload_and_fail_closed`, `test_mcp_untrusted_unknown_id_dropped`.
- Authentication / network isolation: `test_invalid_token_denied_before_hello`, `test_loopback_guard`.
- Synthetic conversation, interruption and reconnect: `test_stream_to_synthetic_read_only_stub`, `test_interrupt_stops_future_audio`, `test_correct_hello_and_session_rotation`.
- Invalid JSON / unrecognized calls: `test_malformed_json_and_unexpected_command_closed`.

Output schema is a structural allowlist: `{schema,upstream_sha,tests,failures,errors,verdict}`; no transcript, audio, token or user identifier fields. Valid verdicts: `protocol_compatible_sim` or `incompatible`.

## Deliberate limits / follow-up tests

A green synthetic fixture is *not* an interoperability proof against stock XiaoZhi firmware. The binary payload is a tagged codec stub, not actual Opus. The simulator's accelerated handshake and abort timeouts are not device latency measures. Pending before B2: real reference-client protocol trace comparison, modern discovery/fallback and paginated tool list over live socket, Fuzz testing of v2/v3 both directions, idle timeout/reconnect race stress, credential-refresh proof, TLS and OTA inspection, hardware verification.

No tools are executed against MCTL; the fabricated status response is emitted locally. No real user principal may be inferred from the fixture MAC or token.
