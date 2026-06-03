# Tasks: issue-34-fix-web-rework-create-order-step-navigat

- [ ] 1. Gate the step-2 action row with `!hasMainButton()` in `CreateOrder.tsx`
  File: `web/src/screens/CreateOrder.tsx`, lines 283-286.
  Replace:
  ```jsx
  <div style={{ display: 'flex', gap: 10 }}>
    <button className="pd-btn-ghost-sm" style={{ flex: '0 0 auto' }} onClick={() => setStep(1)}>Back</button>
    {!hasMainButton() && <button className="pd-btn-block" style={{ marginTop: 0, flex: 1 }} disabled={!amountValid} onClick={primaryAction}>Continue</button>}
  </div>
  ```
  With:
  ```jsx
  {!hasMainButton() && (
    <div style={{ display: 'flex', gap: 10 }}>
      <button className="pd-btn-ghost-sm" style={{ flex: '0 0 auto' }} onClick={() => setStep(1)}>Back</button>
      <button className="pd-btn-block" style={{ marginTop: 0, flex: 1 }} disabled={!amountValid} onClick={primaryAction}>Continue</button>
    </div>
  )}
  ```
  DoD: The `<div>` and both child buttons exist in the rendered tree only when
  `hasMainButton()` returns false. The Back and Continue buttons always appear
  together in the same row; neither can appear alone.

- [ ] 2. Gate the step-3 action row with `!hasMainButton()` in `CreateOrder.tsx` (depends on 1)
  File: `web/src/screens/CreateOrder.tsx`, lines 314-319.
  Replace:
  ```jsx
  <div style={{ display: 'flex', gap: 10 }}>
    <button className="pd-btn-ghost-sm" style={{ flex: '0 0 auto' }} onClick={() => setStep(2)}>Back</button>
    {!hasMainButton() && <button className="pd-btn-block" style={{ marginTop: 0, flex: 1 }} disabled={busy} onClick={primaryAction}>
      {busy ? 'Publishing…' : 'Publish request'}
    </button>}
  </div>
  ```
  With:
  ```jsx
  {!hasMainButton() && (
    <div style={{ display: 'flex', gap: 10 }}>
      <button className="pd-btn-ghost-sm" style={{ flex: '0 0 auto' }} onClick={() => setStep(2)}>Back</button>
      <button className="pd-btn-block" style={{ marginTop: 0, flex: 1 }} disabled={busy} onClick={primaryAction}>
        {busy ? 'Publishing…' : 'Publish request'}
      </button>
    </div>
  )}
  ```
  DoD: Same invariant as task 1: row only rendered when not in Telegram. Publish
  button is disabled while `busy` is true. Error paragraph above the row
  (existing `{err && ...}` at line 313) is unaffected and remains visible.

- [ ] 3. Run `npm run build:api` (or the web build equivalent) to confirm no
  TypeScript / Vite compile errors (depends on 2)
  DoD: Build exits 0 with no type errors in `CreateOrder.tsx`.

## Tests

- [ ] T1. Plain-browser (AUTH_DEV_BYPASS) step 1: only a single "Continue"
  button is rendered; no Back button is present in the DOM.
- [ ] T2. Plain-browser step 2: exactly one Back ghost button and one Continue
  block button are rendered in the same flex container. Continue is disabled
  when `wantAmount` is empty or non-numeric; enabled after a valid amount is
  entered.
- [ ] T3. Plain-browser step 3: exactly one Back ghost button and one "Publish
  request" block button are rendered in the same flex container. Publish is
  disabled while `busy` is true (i.e. during the in-flight POST).
- [ ] T4. Telegram-client simulation (set `window.Telegram.WebApp.initData` to a
  non-empty string so `isTelegram` is true): on steps 2 and 3, no in-page Back
  button and no in-page primary-action button appear in the DOM. The Telegram
  native BackButton is shown (its `show()` method is called) and hidden when
  returning to step 1.
- [ ] T5. Regression: clicking Back on step 2 (in-page) decrements step to 1;
  clicking Back on step 3 decrements step to 2. The `wantAmount` value is
  preserved across the round-trip (state is not reset on back-navigation).

## Rollback

The change touches a single file (`web/src/screens/CreateOrder.tsx`) and adds no
new dependencies or CSS. To roll back: revert the two JSX hunks to their previous
form (re-remove the outer `!hasMainButton()` wrapper and restore the inner guard
on the primary-action button only). A `git revert <commit>` is sufficient; no
migration or data change is involved.
