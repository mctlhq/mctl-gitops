# labs-openclaw — памятка оператора (eth-trading-intel)

Краткая инструкция по работе с Telegram-ботом `@MCTL_AI_bot` для labs-tenant. Бот наблюдает за крипто-рынком через CoinGlass MCP (BTC, ETH, SOL и пр.) и шлёт автономные алерты при cross-сигнала по watchlist.

Все команды — **observation-only**. Никаких ордеров, никаких сделок.

## Быстрая шпаргалка команд

| Категория | Команда | Назначение |
|---|---|---|
| **Snapshot full** | `/eth` `/btc` `/sol` | Полный 10-step снимок c long/short scoring + reasons + risks |
| | `/scan` | Прогнать все символы из watchlist, отфильтровать по per-symbol threshold + direction |
| | `/risk SYMBOL` | Risk-only разбор (OI, funding, L/S ratios, RSI/MACD, CVD, ETF) без scoring |
| | `/why` | Объяснить последний signal — breakdown по reasons / risks / penalties |
| | `/last` | Рекап последнего signal без повторных вызовов CoinGlass |
| **Single-dimension** | `/funding SYMBOL` | Funding rate (4h, OI-weighted) + trajectory + рейтинг |
| | `/oi SYMBOL` | Open interest snapshot + per-exchange split (Binance/OKX/Bybit) |
| | `/etf SYMBOL` | ETF-потоки за 30 дней (только `/etf BTC` и `/etf ETH`) |
| | `/pulse SYMBOL` | Компакт-3 строки: price + funding + OI + RSI 4h |
| **Watchlist** | `/watch SYMBOL [N] [dir]` | Добавить или обновить symbol в watchlist (см. ниже) |
| | `/unwatch SYMBOL` | Убрать symbol из watchlist |
| | `/settings` | Показать watchlist + global threshold + last signal |
| | `/set_threshold N` | Изменить глобальный порог по умолчанию (диапазон 50–95) |

## `/watch` — три формы

```
/watch ETH                  → threshold = global (по умолчанию из state.threshold), direction = both
/watch ETH 75               → threshold = 75, direction = both
/watch ETH 75 long          → threshold = 75, direction = long  (alert только при long-сигнале)
/watch ETH 80 short         → threshold = 80, direction = short
```

- `direction=long` — alert если `long_score >= threshold`
- `direction=short` — alert если `short_score >= threshold`
- `direction=both` — alert если `max(long, short) >= threshold`
- Повторный `/watch` для существующего символа **заменяет** entry, не создаёт дубликат
- Threshold должен быть в `[50, 95]`. Меньшие значения отклоняются с подсказкой

## Типовые сценарии

**Подписаться на ETH (long-only setup):**
```
/watch ETH 70 long
/settings              ← проверить, что добавился
```

**Изменить порог для BTC:**
```
/watch BTC 80 long     ← перезаписывает существующую entry
```

**Отписаться:**
```
/unwatch SOL
```

**Понять почему пришёл alert:**
```
/why                   ← показать reasons / risks последнего signal
/risk SYMBOL           ← если хочется свежий risk-разбор без scoring
```

**Ad-hoc-проверка одной метрики (быстро, без full pipeline):**
```
/funding BTC           ← funding rate snapshot
/oi ETH                ← open interest snapshot
/pulse SOL             ← compact 3-line: price + funding + OI + RSI
/etf BTC               ← ETF-потоки за 30 дней
```

## Автономный мониторинг (Argo CronWorkflow `labs-watch-scan`)

- **Расписание**: каждые 30 минут UTC (`:00` и `:30`)
- **Источник watchlist**: тот же `state.watchlist` что и `/scan` — общий между chat и cron
- **Scoring**: упрощённый, 4 бинарных сигнала × 25 (диапазон 0/25/50/75/100). Грубее чем full skill, поэтому работает как pre-filter
- **Dedup**: 4 часа на символ. Если BTC alert ушёл, следующий BTC-alert возможен только через 4 часа после успешной доставки хотя бы в один operator-chat
- **Получатели**: оба operator-chat (`210408407` + `103413580`) одновременно. Список **захардкожен** в cron-workflow в `ALERT_CHAT_IDS` и ДОЛЖЕН обновляться синхронно с `channels.telegram.allowFrom` в `services/labs/openclaw/values.yaml` (см. секцию "Изменение списка получателей" ниже)
- **Формат alert**: русский, шаблон:
  ```
  ⚠️ BTC лонг — сработал watch (cron pre-filter)

  Скор: 75/100 (порог 67, направление long)
  Цена: $XXXXX.XX (Δ за 24ч: +X.XX%)
  Funding 4h: -0.0094%
  OI растёт: да

  Запустите /eth btc или /btc для полного анализа в чат-скилле.
  Это наблюдение, не финансовая рекомендация.
  ```
- Cron alert это **сигнал "проснись и посмотри"**, не финальное торговое решение. Полный анализ — `/eth /btc /sol` через chat

## Ограничения CoinGlass HOBBYIST tier

- Все CoinGlass-запросы на интервалах `4h+` (1h, 30m, 15m, 5m, 1m → HTTP 403 на этом плане)
- **Не доступны вообще**: `/heatmap`, `/whales`, max-pain clusters, hyperliquid whale positions, `coins_markets` snapshot
- ETF-потоки — только `BTC` и `ETH` (отдельные tools); `/etf SOL` отклоняется с понятным сообщением
- Если когда-то поднимем CoinGlass до Standard — нужно будет:
  - Переключить `DEFAULT_INTERVAL` в skill markdown с `4h` на `1h` (более свежие сигналы)
  - Зарегистрировать `/heatmap` и `/whales` в `customCommands`
  - Добавить max-pain и whales в snapshot pipeline

## Что бот **не** делает

- Не торгует, не выставляет ордера, не даёт entry / stop / take-profit
- Не работает как market-maker — это **observation-only**, целевая частота alert-ов ≤ 6 раз в день на 1 символ
- Не повторяет alert чаще раза в 4h на символ — намеренно, чтобы не спамить
- Не хранит auth-секреты в trading-state — отдельно через openclaw s3-sync canary guard

## Native команды openclaw (не относятся к trading)

`/commands`, `/new`, `/reset`, `/compact`, `/stop`, `/think`, `/model`, `/fast`, `/verbose`, `/status`, `/whoami`, `/context`, `/skill` — встроены в openclaw runtime. Это session/options/status-управление, к торговому боту прямого отношения не имеют.

### Известный quirk: `/help`

`/help` зарегистрирован в `customCommands` (skill) и определён в `eth-trading-intel.md` как команда, выводящая список 16 trading-команд. Однако на практике openclaw runtime может перехватывать `/help` и возвращать native-меню (Session/Options/Status/Skills/Skill/Commands) **даже при `commands.native: false`** — это эмпирически наблюдалось 2026-05-05. Если ты видишь native-меню вместо trading-списка:

- список trading-команд → эта памятка (`USER-GUIDE.md`) или `eth-trading-intel.md` секция `When to use`
- native список → `/commands` (full list openclaw-runtime)

Follow-up план: переименовать skill-команду `/help` → `/cmds` чтобы избежать collision с native router.

## Где искать что-то странное

| Что нужно | Где смотреть |
|---|---|
| Логи cron-tick | `workflows.mctl.ai/workflows/argo-workflows/labs-watch-scan-<unix-ts>` или `s3://argo-workflows-logs/labs-watch-scan-*/main.log` |
| Watchlist (chat-driven) | `s3://platform-state/labs/openclaw/workspace/state/eth-trading-intel.json` |
| Dedup state (cron-driven) | `s3://platform-state/labs/cron/eth-trading-intel-alerts.json` |
| CronWorkflow status | `kubectl -n argo-workflows get cronwf labs-watch-scan` |
| Pod openclaw | `kubectl -n labs get pod -l app.kubernetes.io/instance=labs-openclaw` |
| Skill определение | `services/labs/openclaw/skills/eth-trading-intel.md` (этот репо) |
| CronWorkflow определение | `argo-workflows/cluster-templates/cronworkflow-labs-watch-scan.yaml` (этот репо) |
| customCommands menu | `services/labs/openclaw/values.yaml` → `channels.telegram.customCommands` |

## Изменение списка получателей

Список operator-chat-ов задан в **двух местах** — оба должны меняться синхронно:

1. **`services/labs/openclaw/values.yaml`** → `channels.telegram.allowFrom` — кто **может** chat-ать с ботом
2. **`argo-workflows/cluster-templates/cronworkflow-labs-watch-scan.yaml`** → `ALERT_CHAT_IDS` (Python) и `for CHAT_ID in ...` (shell onExit) — кто **получает** автономные cron-алерты

Если добавить новый chat в #1 без #2 — он сможет писать боту, но не будет видеть autonomous alerts. Если только в #2 без #1 — наоборот: alert придёт, но native-router бота отклонит chat-команды.
