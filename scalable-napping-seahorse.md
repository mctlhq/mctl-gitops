# PairDesk (`mctl-pairdesk`) — Status & Backlog

## Current state (2026-06-01)
- **All 5 stages COMPLETE and deployed** at `https://labs-mctl-pairdesk.mctl.ai` as `0.2.0`
- Stage 1: backend + schema + deal flow + serializer
- Stage 2: bot (webhook, /start gate, approve/reject, accept/reject deal)
- Stage 3: React Mini App (disclaimer, order book, order detail, create, my orders, admin, subscriptions)
- Stage 4: matching + fan-out notifications (want_asset, amount, give assets + rate + payment_methods, location)
- Stage 5: cursor pagination, rate limit 10/hr, setUserStatus TOCTOU fix

## Backlog (not done)

### Near-term
- **Mini App redesign** — full UI overhaul (to be specced with claude design; see design brief below)
- SERVICE_VERSION cosmetic: injected via gitops env, deploy needed to show 0.2.0 in healthz

### Later
- Stage 6: OpenClaw worker (NL parse order → draft, admin daily digest, suspicious-order flag)
- Multi-community support (schema ready with community_id, UI/bot = single-community MVP)
- Make repo public (currently private; flip to match org open-source convention)
- Extract `@mctl/*` npm packages for telegram primitives (initData verify, requireAuth, bot helpers)

## Design brief (for claude design)

### App: PairDesk Mini App redesign

**What it is:** Closed Telegram Mini App for vetted community members to post P2P exchange
requests (EUR↔RUB↔USDT). Bulletin board only — no custody, no payments, not a party to any deal.

**Current stack:** React + Vite, Telegram WebApp SDK (MainButton, BackButton, haptics),
single-page with screen routing, vanilla CSS (no framework).

**Screens to redesign:**
1. **Disclaimer gate** — first-use only; blocks the app; "I understand" button
2. **Order book** — main screen; filter chips (want/give asset, city); list of order cards; "Load more"
3. **Order detail** — full card; give options with rates; "Respond" CTA; deal list (for creator)
4. **Create order** — multi-step form: want asset + amount → give options → location + comment → preview
5. **My orders** — list of own orders with status badges
6. **Subscriptions** — manage alerts (want_asset, amount range, give assets, rate, location)
7. **Admin panel** — pending users queue (approve/reject); moderation actions
8. **Profile** — display name, rating, completed deals count

**Design constraints:**
- Must feel native in Telegram: respect `tg.themeParams` (bg_color, text_color, button_color, etc.)
- Use Telegram MainButton for primary CTAs (not custom bottom buttons)
- Support both light and dark Telegram themes
- Typography: system font stack (same as Telegram) or Inter
- No heavy dependencies — keep it vanilla CSS + React

**Reference:** mctl-loyalty uses "Direction C · Minimal Editorial" (light/Onest/blue);
PairDesk can go its own direction — suggest something appropriate for a P2P finance context
(trust, clarity, professional but not cold).

**Deliverable from claude design:**
- Component hierarchy / screen layout sketches (ASCII or description)
- CSS design tokens (colors, spacing, typography mapped to tg.themeParams)
- Key component patterns (OrderCard, ChipGroup, StepForm, StatusBadge)
- Any interaction patterns worth calling out (swipe, tap states, loading skeletons)

## Architecture reference

```
mctl-pairdesk/
├── src/                      # Node/TS Express backend
│   ├── routes/               # orders, deals, subscriptions, me, admin, rates
│   ├── services/             # orders, deals, matching, moderation, rates, audit
│   ├── telegram/             # webhook.ts, bot.ts, context.ts, initData.ts
│   └── middleware/           # auth.ts (initData verify + requireAuth), errors.ts
├── web/                      # React + Vite Mini App
│   ├── src/
│   │   ├── screens/          # OrderBook, OrderDetail, CreateOrder, MyOrders,
│   │   │                     # Subscriptions, AdminPanel, Profile, Disclaimer
│   │   ├── components.tsx    # OrderCard, Empty, shared UI
│   │   ├── types.ts          # Order, Deal, Subscription, User
│   │   └── api.ts            # typed fetch client
│   └── index.html
└── mctl-gitops/platform-gitops/services/labs/mctl-pairdesk/values.yaml
```

## Deploy notes
- Image: `ghcr.io/mctlhq/mctl-pairdesk` → `ghcr.io/mctlhq/mctl-pairdesk:x.y.z`
- Release: `gh workflow run "Release & Deploy"` on mctl-gitops with repo/git_ref/image_name/image_tag/team_name/component_name
- Tags: no `v` prefix (0.2.0, not v0.2.0)
- Bot token + webhook secret: Vault `teams/labs/mctl-pairdesk` → ExternalSecret → pod env
- DB: CNPG Postgres, requires `ssl: {rejectUnauthorized: false}`
- Dev bypass: `AUTH_DEV_BYPASS=true` + `X-Debug-User-Id` header
