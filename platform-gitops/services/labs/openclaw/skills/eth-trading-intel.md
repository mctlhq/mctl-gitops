---
name: eth-trading-intel
description: Read-only crypto trading intelligence for ETH/BTC/SOL via the CoinGlass MCP server. Use when the user types /eth /btc /sol /scan /risk /why /watch /unwatch /settings /set_threshold /help /last /funding /oi /etf /pulse, or asks for an open-interest, funding, long/short, liquidation, RSI/MACD, max-pain, ETF-flow, or whale-positions snapshot. Observation-only. Never executes trades. Output is a directional snapshot (long_score, short_score, regime, conviction) plus reasons, risks, and explicit missing_data.
---

# eth-trading-intel

## Purpose

Превратить данные CoinGlass MCP в structured trading snapshot для ETH/BTC/SOL. Только observation. Никогда не торговать. Цель — отфильтровать шум: возвращать "no edge detected" честно, когда сигнала нет, вместо натягивания нарратива.

## When to use

Сработать на любую из команд:

- `/eth`, `/btc`, `/sol` — full snapshot
- `/scan` — параллельные snapshots по watchlist, фильтр по per-symbol threshold + direction
- `/risk SYMBOL` — детальный risk-разбор без scoring
- `/why` — объяснение последнего сигнала (читает `state.last_signal`)
- `/watch SYMBOL [N] [long|short|both]` — добавить в watchlist (см. Watchlist commands ниже)
- `/unwatch SYMBOL` — убрать из watchlist
- `/settings` — показать текущий watchlist + threshold
- `/set_threshold N` — задать global threshold (50–95)
- `/help` — список всех команд (static, no CoinGlass calls)
- `/last` — recall `state.last_signal` без re-running pipeline
- `/funding SYMBOL` — single-dimension snapshot: funding rate
- `/oi SYMBOL` — single-dimension snapshot: open interest
- `/etf SYMBOL` — ETF flow deep-dive (только BTC и ETH; SOL/прочие → reject)
- `/pulse SYMBOL` — компакт: price + funding direction + OI delta + RSI bucket

Также активироваться на свободные формулировки: "разбор по ETH", "что там с фандингом", "open interest snapshot", "посмотри ликвидации", "max pain", "rsi на coinglass", "etf flows".

## CoinGlass tier — HOBBYIST (confirmed 2026-05-05, renewal 2026-06-05)

Текущий API plan ключа — `HOBBYIST`. Доступные интервалы для history-эндпоинтов: `4h, 6h, 8h, 12h, 1d`. Интервалы `<4h` (1m/5m/15m/30m/1h) возвращают **HTTP 403** с `current_plan: HOBBYIST, upgrade_required: STANDARD`.

`DEFAULT_INTERVAL = "4h"` — использовать везде в snapshot pipeline и single-dimension queries. Никаких `1h` calls.

### Available на HOBBYIST (используем)

**Discovery:**
- `get_futures_supported_coins`, `get_futures_supported_exchanges`, `get_futures_supported_exchange_pairs`

**Open Interest:**
- `get_futures_aggregated_open_interest_history` — agg OHLC, params: `symbol`, `interval` (≥4h), `limit`
- `get_futures_open_interest_history` — single pair single exchange

**Funding:**
- `get_futures_funding_rate_oi_weight_history` — OI-weighted средняя funding (preferred)
- `get_futures_funding_rate_history` — single pair OHLC funding
- `get_futures_funding_rate_exchange_list` — current funding spot
- `get_futures_funding_rate_rank` — top/bottom 20 funding

**Long/Short:**
- `get_futures_global_long_short_account_ratio_history` — global retail (params: `exchange`+`symbol` pair)
- `get_futures_top_long_short_account_ratio_history` — top traders accounts
- `get_futures_top_long_short_position_ratio_history` — top traders position size

**Liquidations:**
- `get_futures_aggregated_liquidation_history` — agg liq bars (interval ≥4h)
- `get_futures_liquidation_exchange_list` — breakdown spot

**Indicators:**
- `get_futures_rsi_list` — sort_by `rsi_4h`/`rsi_12h`/`rsi_24h`. **Не использовать `rsi_1h`/`rsi_30m`/`rsi_15m`** — за HOBBYIST plan.
- `get_futures_macd_list` — sort_by `macd_4h`. Аналогично, не `macd_1h`.

**Price:**
- `get_futures_price_history` — OHLCV time series
- `get_futures_coins_price_change` — % change

**Volume:**
- `get_futures_aggregated_cvd_history` — taker imbalance (interval ≥4h)

**ETF flows (BTC и ETH only):**
- `get_bitcoin_etf_flow_history`, `get_ethereum_etf_flow_history` — daily net flows

### НЕ доступны на HOBBYIST — НЕ вызывать

- `get_futures_coins_markets` — `current_plan: HOBBYIST → 401 Upgrade plan`
- `get_futures_liquidation_max_pain` — same 401
- `get_hyperliquid_whale_positions` — same 401
- Liquidation Heatmap, Liquidation Map, Liquidation Order events — same
- Любой interval `<4h`

Если эти tools появятся в `tools/list` после tier upgrade — это сигнал что план поднят; bumpить `DEFAULT_INTERVAL` обратно в `1h` (опционально) и расширять scoring. Сейчас вызов любого из них = `missing_data: ["<tool>_tier_locked"]` без penalty (bonus components теряют, base components получают `-10`).

## State file

Persistent state в `/home/node/.openclaw/workspace/state/eth-trading-intel.json`. Schema v2:

```json
{
  "schema": 2,
  "watchlist": [
    { "symbol": "BTC", "threshold": 75, "direction": "both", "added_at": "2026-05-05T12:34:56Z" },
    { "symbol": "ETH", "threshold": 70, "direction": "long", "added_at": "2026-05-05T12:35:01Z" }
  ],
  "threshold": 70,
  "last_signal": {
    "symbol": "BTC",
    "snapshot": {},
    "rendered": "Long Watch · conviction medium · 78/22 ...",
    "at": "2026-05-05T12:34:56Z"
  }
}
```

- `threshold` (top-level, integer) — **global default** для new entries и для `/scan` если у entry нет своего; диапазон [50, 95].
- `watchlist[]` — массив объектов. Поля:
  - `symbol`: uppercase futures coin (validate via cached `get_futures_supported_coins`)
  - `threshold`: integer [50, 95] — per-symbol override
  - `direction`: `"long" | "short" | "both"` — какая сторона score должна cross-нуть для signal
  - `added_at`: ISO-8601
- `last_signal` — full normalized snapshot + rendered text (для `/last` и `/why` без re-running pipeline). Ключ `snapshot` без `raw_sources` (strip перед persist; raw_sources только в памяти агента в течение запроса).

Read: `cat /home/node/.openclaw/workspace/state/eth-trading-intel.json 2>/dev/null || echo '{}'`.

Write: `mkdir -p /home/node/.openclaw/workspace/state && echo '<json>' > /home/node/.openclaw/workspace/state/eth-trading-intel.json`.

s3-sync sidecar мирорит `/home/node/.openclaw/` в S3 каждые 10s — состояние переживает pod restart.

### Watchlist migration shim (schema 1 → 2)

При **первом** read state файл может быть в schema 1 (legacy):

```json
{ "watchlist": ["BTC", "ETH"], "threshold": 70, ... }
```

Procedure:
1. Если `state.schema` отсутствует ИЛИ `state.watchlist[0]` is string → migrate.
2. Для каждой string-entry promote в `{ symbol: <string>, threshold: state.threshold, direction: "both", added_at: <now> }`.
3. На любой malformed entry (lowercase symbol, non-string, missing fields) — НЕ throw; reset эту entry в default `{ symbol: "<best-guess upper>", threshold: state.threshold, direction: "both", added_at: <now> }`. Если symbol invalid — drop entry, добавить лог в `missing_data: ["malformed_watchlist_entry: <raw>"]`. Никогда не убивать весь watchlist.
4. Set `state.schema = 2`. Persist обновлённый state.

Validation для new entries (`/watch SYMBOL [N] [direction]`):
- symbol: upper-case, в supported list (cached via `get_futures_supported_coins`)
- threshold: integer [50, 95], default = `state.threshold`
- direction: ∈ {long, short, both}, default = `both`
- dedup: если symbol уже в watchlist — replace entry (не add duplicate)

## Snapshot pipeline (`/eth`, `/btc`, `/sol`)

Параллельные tool calls (1 round trip). Все интервалы — `4h` (HOBBYIST). Все вызовы через `coinglass__<tool>`:

1. `get_futures_price_history({exchange: "Binance", symbol: "ETHUSDT", interval: "4h", limit: 24})` — OHLCV для current price + 24h-equivalent volatility window. Заменяет `coins_markets` (locked на HOBBYIST). Note: `symbol` here = pair (`ETHUSDT`), not coin (`ETH`).
2. `get_futures_aggregated_open_interest_history({symbol: "ETH", interval: "4h", limit: 12})` — OI delta 4h/12h/24h (12 bars × 4h = 48h окно)
3. `get_futures_funding_rate_oi_weight_history({symbol: "ETH", interval: "4h", limit: 12})` — funding trajectory
4. `get_futures_global_long_short_account_ratio_history({exchange: "Binance", symbol: "ETHUSDT", interval: "4h", limit: 6})` — retail bias
5. `get_futures_top_long_short_position_ratio_history({exchange: "Binance", symbol: "ETHUSDT", interval: "4h", limit: 6})` — top trader bias
6. `get_futures_aggregated_liquidation_history({symbol: "ETH", exchange_list: "Binance,OKX,Bybit", interval: "4h", limit: 12})` — recent liq waves
7. `get_futures_aggregated_cvd_history({symbol: "ETH", exchange_list: "Binance,OKX,Bybit", interval: "4h", limit: 12, unit: "usd"})` — taker imbalance
8. `get_futures_rsi_list({sort_by: "rsi_4h", limit: 300})` — find ETH в результате
9. `get_futures_macd_list({sort_by: "macd_4h", limit: 300})` — то же
10. **Symbol-gated ETF flow call** — feeds the ETF bonus in scoring:
    - `BTC` → `get_bitcoin_etf_flow_history({limit: 7})`
    - `ETH` → `get_ethereum_etf_flow_history({limit: 7})`
    - any other symbol (SOL etc.) → **skip the call**, append `<symbol>_etf_flow_unavailable` to `missing_data`. No penalty (bonus, не основа).

**Удалены из pipeline (HOBBYIST tier-locked):**
- `get_futures_coins_markets` — заменён на `get_futures_price_history` step 1
- `get_futures_liquidation_max_pain` — max-pain cluster scoring component удалён; его заменяет `liquidation_history` analysis (см. Long score components)
- Hyperliquid whale positions — удалён из `/risk` output (раньше упоминался)

Дальше — normalize + score + format.

### Normalization (одна форма для всех символов)

```json
{
  "symbol": "ETH",
  "timestamp": "<ISO-8601>",
  "price": 3450.12,
  "open_interest": {
    "current_usd": 12500000000,
    "change_4h_pct": 1.2,
    "change_24h_pct": 3.1,
    "trend": "rising | flat | falling"
  },
  "funding": {
    "current_pct": 0.012,
    "trajectory_24h": "rising | flat | falling",
    "status": "neutral | hot | cold"
  },
  "long_short": {
    "global_account_ratio": 1.85,
    "top_position_ratio": 1.10,
    "divergence": "retail_long_topshorts | aligned | retail_short_topslongs"
  },
  "liquidations": {
    "long_24h_usd": 45000000,
    "short_24h_usd": 22000000,
    "imbalance": "long_dominant | balanced | short_dominant"
  },
  "indicators": {
    "rsi_4h": 54, "rsi_12h": 52, "rsi_24h": 50,
    "macd_4h": 8.1
  },
  "cvd_24h": {
    "net_usd": 8500000,
    "direction": "buyers_dominant | sellers_dominant | balanced"
  },
  "etf_flow_7d": {
    "available": true,
    "net_usd": 125000000,
    "direction": "inflow | outflow | flat",
    "source_tool": "get_ethereum_etf_flow_history"
  },
  "missing_data": [],
  "raw_sources": {}
}
```

### Directional scoring (НЕ scalar 0-100)

Вернуть **обе** стороны независимо:

```json
{
  "long_score": 0,
  "short_score": 0,
  "regime": "trend | range | transition",
  "conviction": "low | medium | high",
  "reasons": [],
  "risks": [],
  "missing_data": [],
  "bias": "Long Watch | Short Watch | Mixed | No edge",
  "action": "human-readable line"
}
```

**Long score components** (sum, cap 100). Все на 4h (HOBBYIST):

- `+20` MACD 4h positive AND `macd_4h > previous_4h_macd` (rising)
- `+15` RSI 4h ∈ [40, 65] — room to run, not overbought
- `+15` OI rising на 4h AND 12h horizon (`change_4h_pct > 0` AND `change_24h_pct > 0`)
- `+10` funding neutral or slightly negative (`current_pct ≤ 0.01`)
- `+15` long-position liquidations > short × 1.5 за 24h (squeeze setup) — _только если данные есть_
- `+10` retail account ratio < 1.2 AND top position ratio > 1 (counter-retail; smart money long-leaning)
- `+15` CVD net buyers за 24h (`cvd_24h.net_usd > 0`)
- `+10` **symbol-matched** ETF net inflow positive за last 7d — bonus. Tool gating:
  - `BTC` → `get_bitcoin_etf_flow_history({limit: 7})`, sum positive ⇒ +10
  - `ETH` → `get_ethereum_etf_flow_history({limit: 7})`, sum positive ⇒ +10
  - `SOL` (или любой другой) — компонент пропускается, `missing_data: ["<symbol>_etf_flow_unavailable"]`, **никаких penalty** (bonus, не основа). Никогда не применять ETH ETF flow к BTC/SOL.

**Short score components** (sum, cap 100):

- `+20` MACD 4h negative AND `macd_4h < previous_4h_macd` (falling)
- `+15` RSI 4h ∈ [35, 60] — room to fall, not oversold
- `+15` OI rising на 4h AND 12h horizon while price falling (bear positioning grows)
- `+10` funding hot (`current_pct > 0.03`) — over-leveraged longs at risk
- `+15` short liquidations > long × 1.5 за 24h
- `+10` retail account ratio > 1.5 AND top position ratio < 1 (counter-retail short)
- `+15` CVD net sellers за 24h (`cvd_24h.net_usd < 0`)
- `+10` **symbol-matched** ETF net outflow за last 7d — bonus, та же gating-таблица.

**Penalties (apply к более сильному score):**

- `-10` за каждый missing_data input в составе scoring (скорректировано до `-5` если входной сигнал был bonus, не основой)
- `-15` если RSI 4h противоречит MACD 4h direction (mixed signals: RSI > 60 но MACD falling, или RSI < 40 но MACD rising)
- `-10` если price stale (latest OHLC bar timestamp >30 min ago относительно tool-call time — на 4h interval бары обновляются каждые 4h, но отставание > 30 min на свежем баре редко и сигнализирует stale data)

**Regime:**

- `range` — RSI 4h ∈ [45, 55] AND ATR-эквивалент через max-min OHLC за 24h < 2% от price
- `trend` — abs(macd_4h) above some threshold AND OI direction совпадает с price direction
- `transition` — иначе

**Conviction:**

- `high` — gap (`abs(long_score - short_score) ≥ 30`) AND regime != transition
- `medium` — gap ∈ [15, 30)
- `low` — gap < 15 OR regime = transition

**Bias mapping (exhaustive — every (long_score, short_score) pair maps deterministically):**

Apply правила в этом порядке, первое совпадение выигрывает:

1. **Both ≥ threshold AND `abs(long - short) ≥ 15`** → доминирующая сторона: "Long Watch (contested)" если `long > short`, иначе "Short Watch (contested)". Обе стороны имеют материальные сигналы — не игнорировать противоположный.
2. **Both ≥ threshold AND `abs(long - short) < 15`** → "Mixed (both elevated)". Сильные противоречивые сигналы — manual review required, никаких setup hints.
3. **`long_score ≥ threshold` only** (i.e. `short_score < threshold`) → "Long Watch"
4. **`short_score ≥ threshold` only** → "Short Watch"
5. **`max(long_score, short_score) < threshold`** → "No edge" — independent of насколько ниже. Не разделять на "Mixed" vs "No edge" по `< threshold-30` cutoff (создавало неопределённый средний диапазон).

Catch-all `else` не нужен — правила 1-5 покрывают всё пространство `(long ∈ [0,100], short ∈ [0,100], threshold ∈ [50,95])`.

### Output format

```
ETH Snapshot (2026-05-05 12:34 UTC)
Bias: Long Watch
Long score: 78 / Short score: 22
Conviction: medium  Regime: trend

Reasons (long):
1. OI rises across 4h and 12h, +1.2%/+3.1%
2. MACD 4h positive and rising
3. CVD: buyers dominant, +$8.5M last 24h
4. Long-position liquidations $45M vs short $22M — squeeze setup
5. Top traders position ratio 1.10 vs retail 1.85 — smart money long-leaning

Risks:
1. RSI 4h = 58, mid-range; momentum room limited
2. Funding 0.012% — neutral, but rising

Missing data:
- None

Action:
Watch long setup; manual review only. This is observation, not financial advice.
```

Если bias = "No edge":

```
ETH Snapshot (2026-05-05 12:34 UTC)
Bias: No edge
Long score: 38 / Short score: 41
Conviction: low  Regime: range

No actionable setup. Market in range, indicators mixed.
Reasons:
- ...
```

### Phrasing guardrails

**ЗАПРЕЩЕНО**: "BUY NOW", "SELL NOW", "open long immediately", "open short immediately", "go long", "go short", обещания цены/направления, советы про размер позиции/leverage, "guaranteed", "100%", "сейчас отличный вход".

**РАЗРЕШЕНО**: "watch long setup", "watch short setup", "possible squeeze", "manual review required", "wait for retest", "avoid chasing", "no edge detected", "monitor for confirmation".

Каждый snapshot завершается дисклеймером: "This is observation, not financial advice. No automated trading."

## Multi-symbol scan (`/scan`)

1. Read state.watchlist (после migration shim — массив объектов). Если пуст — default `[{symbol:"BTC",threshold:state.threshold,direction:"both"},{symbol:"ETH",...},{symbol:"SOL",...}]`.
2. Параллельно вызвать snapshot pipeline для каждого entry.
3. **Per-entry filter**:
   - `direction == "long"` → крест если `long_score >= entry.threshold`
   - `direction == "short"` → крест если `short_score >= entry.threshold`
   - `direction == "both"` → крест если `max(long_score, short_score) >= entry.threshold`
4. Output — компактный список с per-symbol threshold отметкой:

```
Scan results:
- ETH (≥70 long): Long Watch, 78/22, conviction medium  → /eth для деталей  ✓ crossed
- BTC (≥75 both): No edge, 41/38, conviction low  · below threshold
- SOL (≥70 both): Short Watch, 18/72, conviction high  → /sol для деталей  ✓ crossed
```

Если ничего не прошло — "No symbols crossed their thresholds. Lower with /watch SYMBOL N or /set_threshold."

## Risk-only report (`/risk SYMBOL`)

**Tool calls**: тот же 10-step snapshot pipeline что и `/eth` (с symbol-gated ETF на step 10). Отличие — пропустить блок scoring; собрать только структурированный risk-разбор:

```
Risk report for ETH (2026-05-05 12:34 UTC)
- Price: $3,450.12 (24h range from price_history: $3,402 — $3,512, ±1.6%)
- Open interest: $12.5B agg, +3.1% over 24h, rising on 4h+12h
- Funding (OI-weighted): 0.012%, rising trajectory, status neutral
- Long/short retail (Binance ETHUSDT 4h): account ratio 1.85
- Long/short top traders (Binance ETHUSDT 4h): position ratio 1.10
- Liquidations 24h: long $45M / short $22M (long-dominant; bear pressure on longs)
- RSI: 4h 54 / 12h 52 / 24h 50 — mid-range
- MACD 4h: +8.1 — positive
- CVD 24h: +$8.5M (buyers dominant)
- ETF flows (last 7d): +$X net inflow [BTC/ETH only — symbol-gated]

Volatility window (24h OHLC range): 1.6% — normal.
```

Note: max-pain clusters и Hyperliquid whales отсутствуют в risk-отчёте на HOBBYIST tier (locked). Не упоминать.

## Why command (`/why`)

1. Read `state.last_signal`.
2. Если `null` — `No signal in memory yet. Run /eth, /btc, /sol, or /scan first.`
3. Если есть — расписать:
   - Bias decision: какое правило bias-mapping сработало (1-5)
   - Long score breakdown: какие компоненты дали `+N` и почему (referencing `state.last_signal.snapshot` data)
   - Short score breakdown: то же
   - Penalties applied
   - Missing data + impact на penalty

Read schema:
- `state.last_signal.snapshot` — full normalized object (OI/funding/L-S/liq/RSI/MACD/CVD/ETF)
- `state.last_signal.rendered` — original output text для context
- `state.last_signal.at` — timestamp

## Watchlist commands

`/watch SYMBOL [N] [direction]`:

Form rules:
- `/watch BTC` — legacy short form: threshold = `state.threshold` (global), direction = `both`
- `/watch BTC 80` — threshold-only: direction = `both`
- `/watch BTC 75 long` — full: per-symbol threshold + direction filter

Procedure:
1. Read state. Run watchlist migration shim if schema 1.
2. Parse args. Validate symbol (uppercase, in cached supported list); threshold ∈ [50, 95]; direction ∈ {long, short, both}.
3. Build entry: `{symbol, threshold: <parsed-or-default>, direction: <parsed-or-"both">, added_at: <ISO-now>}`.
4. Dedup: если symbol уже в watchlist — заменить existing entry, не добавлять второй.
5. Write state.
6. Confirmation: `Added ETH (threshold 75, direction long). Watchlist: BTC (75 both), ETH (75 long), SOL (70 both).`

`/unwatch SYMBOL`:
1. Read state, remove entry с matching symbol (любая direction/threshold).
2. Write.
3. `Removed ETH. Watchlist: BTC (75 both), SOL (70 both).`

## Settings commands

`/settings`:

```
Watchlist:
- BTC: threshold 75, direction both
- ETH: threshold 75, direction long
- SOL: threshold 70, direction both
Global threshold: 70

Last signal: ETH Long Watch 78/22 at 2026-05-05 12:34 UTC
```

`/set_threshold 75`:
1. Validate 50 ≤ N ≤ 95. Reject with explanation otherwise.
2. Read state, update **global** `state.threshold` (НЕ модифицирует per-symbol overrides в watchlist[]).
3. Write.
4. `Global threshold updated to 75. Per-symbol overrides preserved: BTC 75, ETH 75, SOL 70.`

Note: чтобы изменить per-symbol threshold — `/watch SYMBOL N [direction]` (replace existing entry).

## Single-dimension queries

Lightweight commands для быстрого ad-hoc check одной метрики. Каждая делает 1-3 tool calls (vs 10 в full snapshot), не пишет `last_signal`, не считает scoring.

### `/help`

Static text. Список всех 16 команд с usage и one-line описанием. Никаких CoinGlass calls. Should включать:
- Trading: /eth, /btc, /sol, /scan, /risk, /pulse, /funding, /oi, /etf, /why, /last
- Watchlist: /watch, /unwatch, /settings, /set_threshold
- Meta: /help

### `/last`

1. Read `state.last_signal`.
2. Если `null` — `No signal in memory yet. Run /eth, /btc, /sol, or /scan first.`
3. Если есть — render `state.last_signal.rendered` напрямую (text-блок). Plus header: `Last signal recorded at <state.last_signal.at>.`
4. Никаких CoinGlass calls.

### `/funding SYMBOL`

1. Validate symbol.
2. Parallel:
   - `get_futures_funding_rate_oi_weight_history({symbol, interval: "4h", limit: 6})`
   - `get_futures_funding_rate_rank({type: "current"})` — для context "где этот symbol относительно top/bottom"
3. Output:
   ```
   ETH funding (4h, OI-weighted)
   Current: 0.012% · Status: neutral
   Trajectory (last 24h, 6 bars): 0.008 → 0.011 → 0.012 → 0.014 → 0.012 → 0.012 (rising flat)
   Rank: #34 of 200 by current funding (mid-pack)
   ```

### `/oi SYMBOL`

1. Validate.
2. Parallel:
   - `get_futures_aggregated_open_interest_history({symbol, interval: "4h", limit: 12})` — agg trend
   - Per-exchange split: 3 separate `get_futures_open_interest_history` calls для top exchanges (Binance, OKX, Bybit) с тем же interval
3. Output:
   ```
   ETH open interest (4h)
   Aggregated: $12.5B · 4h Δ: +0.4% · 12h Δ: +1.2% · 24h Δ: +3.1%  → rising
   Per-exchange (24h Δ):
     - Binance: $4.8B (+2.8%)
     - OKX: $2.1B (+4.5%)
     - Bybit: $3.2B (+1.9%)
   ```

### `/etf SYMBOL`

Symbol-gated:
- `BTC` → `get_bitcoin_etf_flow_history({limit: 30})`
- `ETH` → `get_ethereum_etf_flow_history({limit: 30})`
- любой другой symbol → `ETF flow data only available for BTC and ETH on CoinGlass MCP. /etf SOL is not supported.`

Output (BTC example):
```
BTC ETF flows (last 30 days)
Total net: +$1.2B
Last 7 days: +$245M (5 inflow days, 2 outflow days)
Latest day (2026-05-04): +$32M
Top inflow: 2026-04-28 ($95M)
Top outflow: 2026-04-21 (-$18M)
Trend: net inflow regime
```

### `/pulse SYMBOL`

Compact 4-line output. Минимально: 3-4 tool calls (price, OI, funding, RSI):
1. `get_futures_price_history({exchange:"Binance", symbol:"<S>USDT", interval:"4h", limit:6})` — current price + 24h delta
2. `get_futures_aggregated_open_interest_history({symbol:"<S>", interval:"4h", limit:6})` — 24h OI delta
3. `get_futures_funding_rate_oi_weight_history({symbol:"<S>", interval:"4h", limit:1})` — current funding
4. `get_futures_rsi_list({sort_by:"rsi_4h", limit:300})` — find symbol → rsi_4h

Output:
```
ETH pulse (2026-05-05 12:34 UTC)
Price: $3,450 (4h Δ +0.4%)
OI: $12.5B (24h Δ +3.1% rising)
Funding 4h: 0.012% (neutral)
RSI 4h: 54 (mid-range)
```

Никакого scoring. Никакого `last_signal`. Чистый snapshot одной строкой.

## Missing data handling

Если tool отсутствует в `tools/list` ИЛИ возвращает 4xx/`not-available-on-plan`:

- Записать в `missing_data: ["<tool_name>"]`
- Применить `-5` penalty к scoring sub-input, который от него зависел (если основа сигнала — `-10`)
- В output показать `missing_data` строку прозрачно: "Missing data: liquidation_order (tier-gated)"
- Никогда не падать; никогда не выдумывать значения

Если **все** core tools (markets, OI, funding) недоступны — единственный output: "CoinGlass MCP unreachable or unauthorized. Try later or escalate to operator."

## Anti-patterns

- **Не использовать** REST endpoint matrix CoinGlass для inference (что доступно где) — derive at runtime из tools/list + tool-call errors
- **Не вызывать** все 30 tools на каждый /eth — pipeline выше использует 10, остальное только по явному запросу
- **Не вызывать** STANDARD-tier-locked tools (`get_futures_coins_markets`, `get_futures_liquidation_max_pain`, `get_hyperliquid_whale_positions`, `get_futures_liquidation_heatmap_*`) — на HOBBYIST они вернут 401 "Upgrade plan"; их места в pipeline уже заменены или удалены
- **Не использовать** `interval` менее `4h` (1m, 5m, 15m, 30m, 1h) — на HOBBYIST 403
- **Не агрегировать** scoring до scalar 0-100 — сохранять directional split (long_score, short_score)
- **Не давать** entry/stop/TP цены без явной просьбы пользователя; и даже тогда — только educational ATR-based ranges, никогда конкретные orders
- **Не повторять** snapshot pipeline в loop внутри одного chat-сообщения — pipeline стоит ~10 tool calls; для periodic monitoring используется внешний Argo CronWorkflow `labs-watch-scan` (см. Phase 1.5 / cron alerts ниже)

## Cron alerts (Phase 1.5)

Pasive monitoring через **Argo CronWorkflow `labs-watch-scan`** (см. `platform-gitops/argo-workflows/cluster-templates/cronworkflow-labs-watch-scan.yaml`). Cluster-owned cron каждые 30 мин:

1. Читает watchlist из S3 (`s3://platform-state/labs/openclaw/workspace/state/eth-trading-intel.json`) read-only
2. Для каждой entry дёргает CoinGlass MCP curl (упрощённый scoring: funding direction + price 24h + OI delta — 4 binary signals, scaled to 0..100)
3. Сравнивает с `entry.threshold` + `entry.direction` filter
4. Если crossed AND `last_alert_at[symbol]` ≥ 4h ago → POST Telegram Bot API sendMessage с alert-сообщением. Recommends "Run /eth SYMBOL for full analysis."
5. Updates dedup state в `s3://platform-state/labs/openclaw/workspace/state/eth-trading-intel-alerts.json` (отдельный файл от chat-state, не модифицирует watchlist)

**Cron simple_score умышленно проще** chat-skill полного scoring rubric. Cron — это pre-filter "стоит проснуться и посмотреть", не финальный сигнал. Chat skill сохраняет полную сложность для interactive deep-dive.

## Phase 2 hooks (не имплементировать сейчас)

- Bybit market+derivatives через свой `labs-trading-data` (`smooth-soaring-candy.md`)
- pandas-ta server-side для детерминистичных индикаторов
- CryptoPanic news sentiment
- Etherscan whale/gas
- `/digest` daily summary command

Когда Phase 2 ship'нется — этот skill дополнится новыми tools без переписывания scoring rubric.

## References

- **CoinGlass MCP Beta** — `https://api-mcp.coinglass.com/mcp` (streamable-HTTP, header `CG-API-KEY`). Текущий ключ на Hobbyist tier; `tools/list` отдаёт 30 tools (см. список выше).
- **CoinGlass official agent skills** — `https://github.com/coinglass-official/coinglass-api-skills`. **REST-based**, не MCP — оттуда не наследуем код, но используем как routing-cheat-sheet когда пользователь просит данные **за пределами** scope этого skill (futures, ETF, options, on-chain exchange flows, indicators, news, financial calendar). Карта intent→endpoint:
  - **futures**: funding-rate, liquidation, long-short-ratio, open-interest, order-book-l2, taker-buy-sell, trading-market, hyperliquid-positions
  - **etf**: bitcoin-etf, ethereum-etf, solana-etf, xrp-etf, grayscale
  - **spots**: order-book, taker-buy-sell, trading-market
  - **options**: put/call ratio, options flow, max pain
  - **on-chain**: exchange-data (inflow/outflow, reserve), token (holder distribution), transactions (whale)
  - **indic**: futures, spots, other (fear & greed, sentiment)
  - **other**: financial-calendar (FOMC), news
  Если такие данные нужны — найти в `tools/list` ближайший по namespace tool (e.g. `get_bitcoin_etf_flow_history` для ETF) и вызвать напрямую через MCP. REST-skill из upstream **не клонировать в наш репо**.
- **Phase 2 architecture** — `~/.claude/plans/smooth-soaring-candy.md` (own `labs-trading-data` service с Bybit + CryptoPanic + Etherscan + pandas-ta).
