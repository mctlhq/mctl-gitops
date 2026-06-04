# Design: issue-52-p3-add-native-showconfirm-for-destructiv

## Current state

### Telegram SDK wrapper (`web/src/tg.ts`)

All Telegram WebApp interactions are centralised in `web/src/tg.ts`. The file
declares a `TgWebApp` interface (lines 4-39) that mirrors the subset of the SDK
used by the app. Version-gating already exists: `disableSwipes()` (line 70-76)
calls `wa?.isVersionAtLeast?.('7.7')` before accessing `disableVerticalSwipes`.
The same `isVersionAtLeast` accessor is available for gating `showConfirm`.

`showConfirm` is NOT present in the `TgWebApp` interface and there is no exported
wrapper function for it.

### OrderDetail screen (`web/src/screens/OrderDetail.tsx`)

The two affected action sites are:

1. **"Accept" button** (lines 197-201): rendered inside the maker's response list
   for each deal with `status === 'requested'` and `order.status === 'active'`.
   Handler: `() => void run(() => api.post('/deals/${d.id}/accept'), 'Accepted — contacts shared.')`.
   Effect: locks the order to `reserved`, flips the chosen deal to `accepted`,
   auto-rejects sibling deals, and reveals contact details to both parties.

2. **"Cancel order" button** (lines 210-215): rendered at the bottom of the maker
   section when `order.status` is `'active'` or `'reserved'`. Handler:
   `() => void run(() => api.post('/orders/${order.id}/cancel'), 'Order cancelled.')`.
   Effect: cancels the order, rejects all pending deals, removes the order from
   the public book.

Both handlers call the local `run(fn, okMessage)` helper (lines 33-44) which sets
`busy`, awaits the API call, triggers haptics, and updates state. There is no
confirmation interstitial in either path today.

### Backend

`POST /orders/:id/cancel` is handled by `cancelOrder` in `src/services/orders.ts`
(called from `src/routes/orders.ts` line 109-119). `POST /deals/:id/accept` is
handled by `acceptDeal` (called from `src/routes/deals.ts` line 40). Neither
route has a client-confirmation guard — that is intentionally a frontend concern.

## Proposed solution

### 1. Extend `TgWebApp` interface in `web/src/tg.ts`

Add `showConfirm` to the existing interface:

```ts
showConfirm?(message: string, callback: (confirmed: boolean) => void): void;
```

The method signature matches Telegram's Bot API spec (Bot API 6.2+).

### 2. Export `showConfirm` wrapper from `web/src/tg.ts`

Add a new exported async function:

```ts
/**
 * Show a confirmation dialog. Returns true if the user confirmed.
 * Uses WebApp.showConfirm (Bot API 6.2+) when available; falls back to
 * window.confirm; defaults to true if both are unavailable.
 */
export function showConfirm(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    if (wa?.showConfirm) {
      try {
        wa.showConfirm(message, resolve);
        return;
      } catch {
        // fall through
      }
    }
    if (typeof window.confirm === 'function') {
      resolve(window.confirm(message));
      return;
    }
    resolve(true);
  });
}
```

This matches the pattern of every other wrapper in `tg.ts`: it accesses `wa`
(the module-level `window.Telegram?.WebApp` reference), wraps in try/catch to
survive stubs, and falls back gracefully. No version check via `isVersionAtLeast`
is needed because the feature is detected directly (`wa?.showConfirm`), which is
the simpler and more robust pattern for opt-in APIs.

### 3. Wrap the "Accept" handler in `web/src/screens/OrderDetail.tsx`

Import `showConfirm` alongside the existing tg imports (line 4).

Change the "Accept" button's inline `onClick` from:
```tsx
onClick={() => void run(() => api.post(`/deals/${d.id}/accept`), 'Accepted — contacts shared.')}
```
to:
```tsx
onClick={async () => {
  const ok = await showConfirm('Accept this response? Contacts will be shared and other responses rejected.');
  if (!ok) return;
  void run(() => api.post(`/deals/${d.id}/accept`), 'Accepted — contacts shared.');
}}
```

### 4. Wrap the "Cancel order" handler in `web/src/screens/OrderDetail.tsx`

Change the "Cancel order" button's inline `onClick` from:
```tsx
onClick={() => void run(() => api.post(`/orders/${order.id}/cancel`), 'Order cancelled.')}
```
to:
```tsx
onClick={async () => {
  const ok = await showConfirm('Cancel this order? This cannot be undone.');
  if (!ok) return;
  void run(() => api.post(`/orders/${order.id}/cancel`), 'Order cancelled.');
}}
```

### Why the `busy` guard does not need changing

The `run` helper sets `busy = true` as its first statement. Because the `showConfirm`
await completes before `run` is invoked, and `busy` is only set inside `run`, the
button remains interactive during the dialog. This is correct: the user should be
able to tap "Cancel" in the dialog and walk away without the button becoming
permanently disabled. The `disabled={busy}` prop correctly blocks re-entry once
the user has confirmed and `run` is executing.

## Alternatives

### A. In-app custom modal (React state + CSS overlay)

Build a `<ConfirmModal>` component rendered inside `OrderDetail`. Pros: full
styling control, testable with React Testing Library. Cons: significant additional
code; inconsistent with Telegram's native UX (users expect the platform dialog
for destructive confirmations); the codebase currently has no modal infrastructure,
so this would be over-engineering for two use sites. Dropped.

### B. Inline "are you sure?" toggle state (two-tap confirmation)

On first tap, flip a `confirming` boolean that changes the button label to "Tap
again to confirm" and requires a second tap within a timeout. Pros: no dialog,
fully custom. Cons: non-standard pattern, harder to implement correctly with
timeouts and focus management, does not use the available platform API. Dropped.

### C. Only add the guard in-line without a `tg.ts` wrapper

Call `wa?.showConfirm` and `window.confirm` directly inside `OrderDetail.tsx`.
Pros: fewer files changed. Cons: duplicates fallback logic across the two call
sites, bypasses the established pattern of centralising all Telegram SDK access
in `tg.ts`, and is harder to test or mock. Dropped.

## Platform impact

### Migrations
None. This is a pure frontend change. No schema, API, or configuration changes.

### Backward compatibility
The fallback chain (`wa.showConfirm` -> `window.confirm` -> proceed) ensures the
feature degrades gracefully on any client version. Existing behaviour in unsupported
environments is preserved exactly: if both confirmation methods are absent the
action still executes (same as today), which is acceptable because the fallback-
to-proceed path only applies in sandboxed or legacy environments where the user
deliberately initiated the action.

### Resource impact
Negligible. Two additional async handlers; no new dependencies, no additional
network calls.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Telegram client invokes `showConfirm` callback synchronously, resolving the Promise inside the microtask queue before the component has updated | `Promise` resolution is always async (microtask), so React state updates issued before the `await` still batch correctly. No issue in practice. |
| Stale closure captures an old `order.id` or `d.id` in the confirm handler | Both values are captured fresh from the render closure, same as today. No change in closure semantics. |
| `window.confirm` is blocked in certain WebView embeddings on Android | Third branch in fallback resolves `true`, preserving current behaviour. |
