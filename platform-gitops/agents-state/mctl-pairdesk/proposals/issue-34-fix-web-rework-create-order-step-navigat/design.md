# Design: issue-34-fix-web-rework-create-order-step-navigat

## Current state

### File: `web/src/screens/CreateOrder.tsx`

`CreateOrder` is a single React component with a `step` state variable (1, 2, or 3).
Navigation plumbing lives in two `useEffect` blocks (lines 170-182):

```
// Lines 170-177: registers/updates the Telegram MainButton for the primary action.
// Active on all three steps. No-ops (returns () => {}) when !isTelegram.
useEffect(() => {
  return setMainButton({ text: nextText, enabled: nextEnabled, loading: busy,
    onClick: () => primaryActionRef.current() });
}, [busy, nextEnabled, nextText, step]);

// Lines 179-182: registers/shows Telegram's native BackButton for steps 2 and 3.
// No-ops when !isTelegram (showBackButton checks for wa).
useEffect(() => {
  if (step === 1) return undefined;
  return showBackButton(() => setStep((s) => Math.max(1, s - 1)));
}, [step]);
```

The in-page fallback buttons for steps 1-3 (rendered when `hasMainButton()` is false
or, in the Back case, unconditionally):

- **Step 1 (line 220):** `{!hasMainButton() && <button className="pd-btn-block" ...>Continue</button>}`
  — correctly gated; only shown in plain browser.

- **Step 2 (lines 283-286):**
  ```jsx
  <div style={{ display: 'flex', gap: 10 }}>
    <button className="pd-btn-ghost-sm" style={{ flex: '0 0 auto' }} onClick={() => setStep(1)}>Back</button>
    {!hasMainButton() && <button className="pd-btn-block" style={{ marginTop: 0, flex: 1 }} disabled={!amountValid} onClick={primaryAction}>Continue</button>}
  </div>
  ```
  The Back button has **no `hasMainButton()` guard**. In a real Telegram session
  `hasMainButton()` is true, so the Continue half is suppressed but the Back half
  remains — a lone ghost Back button with no paired primary action, floating above
  the native Telegram MainButton.

- **Step 3 (lines 314-319):**
  ```jsx
  <div style={{ display: 'flex', gap: 10 }}>
    <button className="pd-btn-ghost-sm" style={{ flex: '0 0 auto' }} onClick={() => setStep(2)}>Back</button>
    {!hasMainButton() && <button className="pd-btn-block" style={{ marginTop: 0, flex: 1 }} disabled={busy} onClick={primaryAction}>
      {busy ? 'Publishing…' : 'Publish request'}
    </button>}
  </div>
  ```
  Same bug: Back is unconditional, Publish is gated.

### File: `web/src/tg.ts`

`hasMainButton()` (line 271) returns `isTelegram`, which is `Boolean(wa && wa.initData)`.
It is `true` only in a real Telegram client with valid initData, never in a plain
browser session (even with `AUTH_DEV_BYPASS`, `initData` returns `''`).

`setMainButton` (line 225) explicitly bails out with `if (!isTelegram || !wa) return () => {};`,
confirming that the in-page fallbacks are the only visible controls outside Telegram.

### File: `web/src/styles.css`

- `.pd-btn-ghost-sm` (lines 766-779): inline-flex ghost button, 36px min-height,
  border + subdued text colour. Used for the Back control.
- `.pd-btn-block` (lines 781-799): full-width flex block button, 46px min-height,
  accent background. Used for Continue/Publish. Has `margin-top: 12px` baked in;
  overridden inline with `marginTop: 0` when placed inside the flex row.

## Proposed solution

Wrap the **entire** bottom action `<div>` on steps 2 and 3 with `!hasMainButton()`,
mirroring the pattern already used on step 1. No logic changes, no new state, no
new CSS classes.

### Step 2 change (lines 283-286 → single guarded block)

```jsx
{!hasMainButton() && (
  <div style={{ display: 'flex', gap: 10 }}>
    <button className="pd-btn-ghost-sm" style={{ flex: '0 0 auto' }} onClick={() => setStep(1)}>Back</button>
    <button className="pd-btn-block" style={{ marginTop: 0, flex: 1 }} disabled={!amountValid} onClick={primaryAction}>Continue</button>
  </div>
)}
```

### Step 3 change (lines 314-319 → single guarded block)

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

The Telegram MainButton and native BackButton effects (lines 170-182) are unchanged.
In a real Telegram session the native controls handle all navigation; the in-page
`<div>` is simply not rendered. In a plain browser both the Back ghost and the
primary-action block render together in the paired row.

### Why this works

The root cause is the missing `!hasMainButton()` guard on the Back button. Lifting
the guard to the parent `<div>` (rather than keeping two separate inner guards) is
the simplest fix and ensures Back and Continue/Publish are either both present or
both absent — they cannot become desynchronised again in the future.

## Alternatives

### 1. Keep Back always visible but add a "no in-Telegram" CSS class

Add a utility class (e.g. `.pd-hide-in-tg`) toggled by a boolean on `<html>` at
mount, and apply it to the Back buttons. Rejected: introduces an implicit global
flag where explicit conditional rendering is clearer and already used by every
other gated element in the file.

### 2. Extract a `<StepNav>` component with built-in environment awareness

Create a shared component that accepts `step`, `onBack`, `onPrimary`, etc. and
renders the right set of native/in-page controls. Rejected for this issue: the
scope is small (two call sites, one file), and the abstraction adds indirection
without reducing complexity. Worth revisiting if a third consumer emerges.

### 3. Replace `hasMainButton()` gating with a context / feature-flag

Promote Telegram-environment detection to a React context so any sub-tree can
read it. Rejected: over-engineering for a one-line guard fix. The existing
`hasMainButton()` call is synchronous and already imported.

## Platform impact

- **Migrations:** none — Mini App only.
- **Backward compatibility:** the Telegram MainButton and BackButton paths are
  untouched; behaviour inside Telegram is identical to today (the stray Back
  button is removed, which is the fix). Plain-browser behaviour is improved:
  Back and Continue/Publish are now always paired.
- **Resource impact:** negligible (fewer DOM nodes rendered in Telegram sessions).
- **Risks:** none identified. The `!hasMainButton()` guard is already used
  successfully on step 1 and on the primary-action half of steps 2 and 3; this
  change applies the same pattern consistently.
