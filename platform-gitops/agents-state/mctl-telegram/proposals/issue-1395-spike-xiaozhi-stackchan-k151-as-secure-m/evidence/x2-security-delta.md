# X2 security delta — candidate only

No accepted ADR change. B3 ADR/design tracker: https://github.com/mctlhq/mctl-telegram/issues/1412. Reference: mctl-telegram `docs/adr/0011-personal-assistant.md` and `docs/agent-runtime/personal-assistant-threat-model.md`.

| Boundary | Synthetic simulator | Real device future (blocked) |
|---|---|---|
| Device to gateway identity | literal fixture header token on 127.0.0.1, no user identity | owner pairing via verified Telegram OIDC/Mini App with short-lived device-scoped proof-of-possession tokens and revocation fencing |
| Owner vs voice speaker | none, never a real principal | distinguish enrolled owner from person physically speaking; wake word and proximity **not** proof of owner |
| MCP tools | fabricated single read-only local response | only pinned/read-only tools after new role and consent review; physical actions never implied by 'read-only' annotation |
| Voice disclosure | synthetic text only | never speak private Telegram text without fresh out-of-band user confirmation and safe output route |
| PA principal invariant I2 | no PA used, invariant unchanged | requires reviewed new principal source/constructor; not a software-device claim or MAC address |
| Credentials | no OAuth/user secrets; synthetic literal fixture | secrets kept server-side; device-scoped revocable key only, not user token |
| T13 consent | no user data processing | new `desk-voice-data-flow/v1` with explicit ASR/TTS recipients, retention and region |
| Logs | count-only report | audit digests and no raw audio/transcripts by default, strict redaction and opt-in rules |

P1-GOV addressed **only** by separating #1409 from #1395 Temporal. P1-AUTH and P1-DEVICE remain unresolved B2/B3 gates. No device write, servo command or actual firmware fix is authorized.
