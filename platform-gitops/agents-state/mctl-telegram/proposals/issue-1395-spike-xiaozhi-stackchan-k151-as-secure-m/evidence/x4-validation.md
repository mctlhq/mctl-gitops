# X4 product validation — proposed, unmeasured

## Synthetic use cases

1. U1: ask for a synthetic build/release summary; expected mocked `desk_build_status` read-only response.
2. U2: ask for a synthetic GitHub issue summary; expected fixed local issue fixture.

The first 14-test harness executes a minimal U1-shaped synthetic path only. Full 50-turn U1/U2 scripts, wake-word ambient audio, Russian ASR/TTS and live provider benchmark remain to be prepared under a separate gate.

## Metrics and proposed targets (NOT measured)

| Metric | Future target | Measurement method |
|---|---|---|
| Wake-to-first-audio | p50 <= 1.5s | timestamp device wake to first decoded TTS packet, >=50 scripted turns |
| Full task latency | p50 <= 3s, p95 <= 6s | device wake to completion of correct answer |
| Correct tool task | >=90% | 50 independent tasks, scripted oracle & negative controls |
| Barge-in stop | <=300ms | microphone interruption to last emitted downlink packet |
| Reconnect | <=5s | controlled socket drop to successful new authenticated conversation |
| False wake | <=1/8h | labeled ambient audio playback, no private contents |
| ASR+LLM+TTS running cost | <=$0.50/100 turns | sum separately quoted minute/token/character billing per selected provider with measured use |

Provider price sources and the Russian ASR/TTS A/B comparison have **not** been verified in this revision. No numeric cost conclusion is drawn. Pre-B2 requirement: choose two currently supported Russian-capable provider stacks, pin date/tariff and calculate cost sensitivity for 10/30/60-second turns.

## Stop/go gates

- Internal simulator: recorded green at #1410 HEAD, only synthetic compatibility.
- K151: deferred until TLS, vendor OTA, device identity and firmware framing P1 are resolved and the owner gives B2 GO.
- Productization: deferred until a new PA ADR/consent, real-user disclosure model, cost/latency evidence, pilot success and explicit owner GO.
