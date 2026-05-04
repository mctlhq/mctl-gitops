---
name: eth-trading-intel
description: Read-only crypto trading intelligence for ETH/BTC/SOL via the CoinGlass MCP server. Use when the user types /eth /btc /sol /scan /risk /why /watch /unwatch /settings /set_threshold, or asks for an open-interest, funding, long/short, liquidation, RSI/MACD, max-pain, or whale-positions snapshot. Observation-only. Never executes trades. Output is a directional snapshot (long_score, short_score, regime, conviction) plus reasons, risks, and explicit missing_data.
---

# eth-trading-intel

## Purpose

Превратить данные CoinGlass MCP в structured trading snapshot для ETH/BTC/SOL. Только observation. Никогда не торговать. Цель — отфильтровать шум: возвращать "no edge detected" честно, когда сигнала нет, вместо натягивания нарратива.

## When to use

Сработать на любую из команд:

- `/eth` — snapshot по ETH
- `/btc` — snapshot по BTC
- `/sol` — snapshot по SOL
- `/scan` — параллельные snapshots по watchlist (по умолчанию BTC+ETH+SOL), фильтр по threshold
- `/risk SYMBOL` — детальный risk-разбор без scoring
- `/why` — объяснение последнего сигнала
- `/watch SYMBOL` / `/unwatch SYMBOL` — добавить/убрать из watchlist
- `/settings` — показать текущий watchlist + threshold
- `/set_threshold N` — задать threshold (50–95)

Также активироваться на свободные формулировки: "разбор по ETH", "что там с фандингом", "open interest snapshot", "посмотри ликвидации", "max pain", "rsi на coinglass".

## Available CoinGlass MCP tools (Hobbyist tier, confirmed 2026-05-05)

30 tools под префиксом `coinglass__` (точное префиксирование зависит от openclaw bundling — проверять в реальном агенте). Используем подмножество:

**Discovery (вызывать только при необходимости проверить символ/exchange):**
- `get_futures_supported_coins`, `get_futures_supported_exchanges`, `get_futures_supported_exchange_pairs`

**Open Interest:**
- `get_futures_aggregated_open_interest_history` — agg OHLC по всем биржам, params: `symbol`, `interval`, `limit` (≤1000)
- `get_futures_open_interest_history` — single pair single exchange

**Funding:**
- `get_futures_funding_rate_oi_weight_history` — OI-weighted средняя funding по биржам (predпочтителен), params: `symbol`, `interval`
- `get_futures_funding_rate_history` — single pair OHLC funding
- `get_futures_funding_rate_exchange_list` — current funding по всем coins на exchange (для контекста)
- `get_futures_funding_rate_rank` — top/bottom 20 funding (для регима)

**Long/Short:**
- `get_futures_global_long_short_account_ratio_history` — global retail account ratio, params: `exchange` + `symbol` (pair, e.g. BTCUSDT) + `interval`
- `get_futures_top_long_short_account_ratio_history` — top traders account ratio
- `get_futures_top_long_short_position_ratio_history` — top traders position ratio (size, не accounts)

**Liquidations:**
- `get_futures_aggregated_liquidation_history` — agg liq amounts (bars), params: `symbol` + `exchange_list` + `interval`
- `get_futures_liquidation_max_pain` — **ключевой**: текущая цена + price levels где сосредоточены крупнейшие notional positions. **Замена для heatmap** на Hobbyist tier. Params: `symbol_list`, `range` (12h/24h/48h/3d/7d/14d/30d). Без exchange.
- `get_futures_liquidation_exchange_list` — breakdown по биржам

**Indicators (current values для всех coins одним запросом):**
- `get_futures_rsi_list` — params: `sort_by: "rsi_<interval>"`, `order`, `limit`. Возвращает RSI на 15m/30m/1h/4h/12h/24h.
- `get_futures_macd_list` — params: `sort_by: "macd_<interval>"`, `order`, `limit`. Возвращает MACD на 1m/5m/15m/30m/1h/4h.

**Price/markets:**
- `get_futures_coins_markets` — snapshot price + avg funding + agg OI + 24h vol. Params: `symbol_list`. **Использовать первым** в pipeline для быстрого общего контекста.
- `get_futures_price_history` — OHLCV time series
- `get_futures_coins_price_change` — % change для всех coins

**Volume / orderflow:**
- `get_futures_aggregated_cvd_history` — agg CVD (taker imbalance), params: `symbol` + `exchange_list` + `interval` + `unit` ("usd"|"coin")

**Whales:**
- `get_hyperliquid_whale_positions` — позиции на Hyperliquid >$1M, params: `symbol` filter

**ETF flows (для bigger picture):**
- `get_ethereum_etf_flow_history`, `get_bitcoin_etf_flow_history` — daily net flows. Params: `limit` (default 30, max 2000).

**ОТСУТСТВУЕТ на Hobbyist tier** (если нужно — обновлять до Standard $299 / Professional $699):
- Liquidation Order events (real-time individual liquidations)
- Liquidation Heatmap models (Pair/Coin × Model 1/2/3) — но `liquidation_max_pain` покрывает 80% сигнальной ценности
- Liquidation Map

Эти tools НЕ должны вызываться. Если они впервые появятся в `tools/list` после tier upgrade — отметить и расширить scoring.

## State file

Persistent state в `/home/node/.openclaw/workspace/state/eth-trading-intel.json`:

```json
{
  "watchlist": ["BTC", "ETH", "SOL"],
  "threshold": 70,
  "last_signal": null,
  "last_signal_at": null
}
```

Read через Bash: `cat /home/node/.openclaw/workspace/state/eth-trading-intel.json 2>/dev/null || echo '{}'`.

Write через Bash: `mkdir -p /home/node/.openclaw/workspace/state && echo '<json>' > /home/node/.openclaw/workspace/state/eth-trading-intel.json`.

s3-sync sidecar мирорит `/home/node/.openclaw/` в S3 каждые 10s, так что состояние переживает pod restart.

При записи `last_signal` сохранять полный snapshot объект (для `/why`).

Validation:
- threshold ∈ [50, 95]
- watchlist symbols upper-case, only valid futures coins (если не уверен — `get_futures_supported_coins`, кэшировать в памяти агента на сессию)

## Snapshot pipeline (`/eth`, `/btc`, `/sol`)

Параллельные tool calls (1 round trip). Все вызовы через `coinglass__<tool>`:

1. `get_futures_coins_markets({symbol_list: "ETH"})` — price, agg OI, agg funding, 24h vol
2. `get_futures_aggregated_open_interest_history({symbol: "ETH", interval: "1h", limit: 24})` — OI delta 1h/4h/24h
3. `get_futures_funding_rate_oi_weight_history({symbol: "ETH", interval: "1h", limit: 24})` — funding trajectory
4. `get_futures_global_long_short_account_ratio_history({exchange: "Binance", symbol: "ETHUSDT", interval: "4h", limit: 6})` — retail bias
5. `get_futures_top_long_short_position_ratio_history({exchange: "Binance", symbol: "ETHUSDT", interval: "4h", limit: 6})` — top trader bias
6. `get_futures_aggregated_liquidation_history({symbol: "ETH", exchange_list: "Binance,OKX,Bybit", interval: "1h", limit: 24})` — recent liq waves
7. `get_futures_liquidation_max_pain({symbol_list: "ETH", range: "24h"})` — nearest stop clusters
8. `get_futures_rsi_list({sort_by: "rsi_4h", limit: 200})` — найти ETH в результате (или повторить с разными sort_by)
9. `get_futures_macd_list({sort_by: "macd_4h", limit: 200})` — то же
10. `get_futures_aggregated_cvd_history({symbol: "ETH", exchange_list: "Binance,OKX,Bybit", interval: "1h", limit: 24, unit: "usd"})` — taker imbalance

(8 и 9 неэффективны если нужен только ETH; альтернативно — индикаторы из price_history + ручной TA. Для Phase 1 использовать `_list` versions, optimize later.)

Дальше — normalize + score + format.

### Normalization (одна форма для всех символов)

```json
{
  "symbol": "ETH",
  "timestamp": "<ISO-8601>",
  "price": 3450.12,
  "open_interest": {
    "current_usd": 12500000000,
    "change_1h_pct": 0.4,
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
    "imbalance": "long_dominant | balanced | short_dominant",
    "max_pain": {
      "available": true,
      "long_cluster_price": 3380,
      "short_cluster_price": 3540,
      "current_distance_to_long_cluster_pct": -2.0,
      "current_distance_to_short_cluster_pct": 2.6
    }
  },
  "indicators": {
    "rsi_15m": 62, "rsi_1h": 58, "rsi_4h": 54, "rsi_1d": 50,
    "macd_1h": 12.3, "macd_4h": 8.1
  },
  "cvd_24h": {
    "net_usd": 8500000,
    "direction": "buyers_dominant | sellers_dominant | balanced"
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

**Long score components** (sum, cap 100):

- `+15` MACD positive on 4h AND rising on 1h
- `+10` RSI 4h ∈ [40, 65] (room to run, not overbought)
- `+15` OI rising on both 1h and 4h (`change_1h_pct > 0` AND `change_4h_pct > 0`)
- `+10` funding neutral or slightly negative (`current_pct ≤ 0.01`) — long bias не переплачивает
- `+10` price within ±1% of `long_cluster_price` (потенциальный bounce)
- `+10` long-position liquidations > short × 1.5 за 24h (squeeze setup) — _только если данные есть_
- `+10` retail account ratio < 1.2 AND top position ratio > 1 (контр-retail; "smart money long")
- `+10` CVD net buyers за 24h
- `+10` **symbol-matched** ETF net inflow positive за last 7d — bonus. Tool gating:
  - `BTC` → `get_bitcoin_etf_flow_history({limit: 7})`, sum positive ⇒ +10
  - `ETH` → `get_ethereum_etf_flow_history({limit: 7})`, sum positive ⇒ +10
  - `SOL` (или любой другой symbol без ETF tool в `tools/list`) — компонент пропускается, добавляется `missing_data: ["<symbol>_etf_flow_unavailable"]`, **никаких penalty** (это bonus, не основа). Никогда не применять ETH ETF flow к BTC/SOL и наоборот.

**Short score components** (sum, cap 100):

- `+15` MACD negative on 4h AND falling on 1h
- `+10` RSI 4h ∈ [35, 60] (room to fall, not oversold)
- `+15` OI rising on 1h AND 4h while price falling (bear positioning grows)
- `+10` funding hot (`current_pct > 0.03`) — over-leveraged longs at risk
- `+10` price within ±1% of `short_cluster_price` (потенциальный rejection)
- `+10` short liquidations > long × 1.5 за 24h
- `+10` retail account ratio > 1.5 AND top position ratio < 1 (counter-retail short)
- `+10` CVD net sellers за 24h
- `+10` **symbol-matched** ETF net outflow за last 7d — bonus, та же gating-таблица что и для long-bonus выше (BTC→bitcoin_etf, ETH→ethereum_etf, SOL→skip+missing_data). Кросс-применение запрещено.

**Penalties (apply к более сильному score):**

- `-15` если `funding hot` AND текущая цена внутри ±1% от **противоположного** cluster (трамплин в ловушку)
- `-10` за каждый missing_data input в составе scoring (скорректировано до `-5` если входной сигнал был bonus, не основой)
- `-10` если RSI 4h противоречит MACD 4h (mixed signals)
- `-15` если price stale (>5 min от tool call)

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
1. OI rises across 1h and 4h, +1.2%/+3.1%
2. MACD 4h positive and rising on 1h
3. CVD: buyers dominant, +$8.5M last 24h
4. Price 2% above nearest long liquidation cluster ($3,380), -1.2% below short cluster ($3,540)
5. Top traders position ratio 1.10 vs retail 1.85 — smart money long-leaning

Risks:
1. RSI 4h = 58, mid-range; momentum room limited
2. Funding 0.012% — neutral, but rising

Missing data:
- None

Action:
Watch long setup; manual review only. Wait for retest of $3,380 zone before
considering entry. This is observation, not financial advice.
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

1. Read state.watchlist (default ["BTC","ETH","SOL"]).
2. Параллельно вызвать snapshot pipeline для каждого symbol.
3. Фильтр: `max(long_score, short_score) >= state.threshold`.
4. Output — компактный список:

```
Scan results (threshold 70):
- ETH: Long Watch, 78/22, conviction medium  → /eth для деталей
- BTC: No edge, 41/38, conviction low
- SOL: Short Watch, 18/72, conviction high  → /sol для деталей
```

Если ничего не прошло threshold — "No symbols crossed threshold. Lower with /set_threshold or wait."

## Risk-only report (`/risk SYMBOL`)

Полный pipeline БЕЗ scoring. Просто структурированный risk-разбор:

```
Risk report for ETH (2026-05-05 12:34 UTC)
- Open interest: $12.5B agg, +3.1% over 24h, rising on 1h+4h
- Funding (OI-weighted): 0.012%, rising trajectory, status neutral
- Long/short retail (Binance ETHUSDT 4h): account ratio 1.85
- Long/short top traders (Binance ETHUSDT 4h): position ratio 1.10
- Liquidations 24h: long $45M / short $22M (long-dominant; bear pressure on longs)
- Max pain clusters (24h): long $3,380 (-2.0%), short $3,540 (+2.6%)
- RSI: 15m 62 / 1h 58 / 4h 54 / 1d 50 — mid-range
- MACD: 1h +12.3 / 4h +8.1 — positive
- CVD 24h: +$8.5M (buyers dominant)
- Whales (Hyperliquid >$1M): N positions, M long / K short
- ETF flows (last 7d): +$X net inflow

Volatility window (24h OHLC range): N% — normal.
```

## Why command (`/why`)

Read `state.last_signal`. Если есть — пройтись по reasons + risks + missing_data, показать как именно scoring пришёл к bias. Если nothing — "No signal in memory yet. Run /eth or /scan first."

## Watchlist commands

`/watch SYMBOL`:
1. Read state, append SYMBOL to watchlist (uppercase, dedup).
2. Validate symbol in supported list (cached).
3. Write state.
4. "Added ETH to watchlist. Current: BTC, ETH, SOL. Threshold 70."

`/unwatch SYMBOL`:
1. Read state, remove.
2. Write.
3. "Removed ETH. Current: BTC, SOL."

## Settings commands

`/settings`:

```
Watchlist: BTC, ETH, SOL
Threshold: 70
Last signal: ETH Long Watch 78/22 at 2026-05-05 12:34 UTC
```

`/set_threshold 75`:
1. Validate 50 ≤ N ≤ 95. Reject with explanation otherwise.
2. Read state, update threshold, write.
3. "Threshold updated to 75."

## Missing data handling

Если tool отсутствует в `tools/list` ИЛИ возвращает 4xx/`not-available-on-plan`:

- Записать в `missing_data: ["<tool_name>"]`
- Применить `-5` penalty к scoring sub-input, который от него зависел (если основа сигнала — `-10`)
- В output показать `missing_data` строку прозрачно: "Missing data: liquidation_order (tier-gated)"
- Никогда не падать; никогда не выдумывать значения

Если **все** core tools (markets, OI, funding) недоступны — единственный output: "CoinGlass MCP unreachable or unauthorized. Try later or escalate to operator."

## Anti-patterns

- **Не использовать** REST endpoint matrix CoinGlass для inference (что доступно где) — derive at runtime из tools/list + tool-call errors
- **Не вызывать** все 30 tools на каждый /eth — pipeline выше использует ~10, остальное только по явному запросу
- **Не делать** автоматические повторные вызовы по cron (Phase 1 = on-demand only; cron в Phase 2)
- **Не агрегировать** scoring до scalar 0-100 — сохранять directional split
- **Не давать** entry/stop/TP цены без явной просьбы пользователя; и даже тогда — только educational ATR-based ranges, никогда конкретные orders

## Phase 2 hooks (не имплементировать сейчас)

- Bybit market+derivatives через свой `labs-trading-data` (`smooth-soaring-candy.md`)
- pandas-ta server-side для детерминистичных индикаторов
- CryptoPanic news sentiment
- Etherscan whale/gas
- Cron-based scanner с Telegram push (3-of-3 gate из `smooth-soaring-candy.md`)

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
