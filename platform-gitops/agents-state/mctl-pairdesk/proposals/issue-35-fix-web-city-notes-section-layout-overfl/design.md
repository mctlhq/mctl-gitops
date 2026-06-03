# Design: issue-35-fix-web-city-notes-section-layout-overfl

## Current state

### Markup — `web/src/screens/CreateOrder.tsx:290-320`

Step 3 is rendered inside a `<div className="pd-form-multi">` wrapper, which contains a
single `<div className="pd-form-section">`. The relevant fragment (lines 297-307) is:

```jsx
<span className="pd-label">City <span className="pd-label-opt">· optional</span></span>
<label className="pd-field">
  <Icon name="pin" size={16} cls="pd-field-ic" />
  <input className="pd-input" inputMode="text" placeholder="e.g. Bar" value={city}
    onChange={(e) => setCity(e.target.value)}
    onFocus={(e) => scrollFieldIntoView(e.currentTarget)} />
</label>
<p className="pd-form-sub">Anything that helps a counterparty — timing, area, preferences.</p>
<textarea className="pd-input" inputMode="text" placeholder="e.g. can meet near the marina this evening"
  value={comment} onChange={(e) => setComment(e.target.value)}
  onFocus={(e) => scrollFieldIntoView(e.currentTarget)} />
```

There are two structural problems:

1. The `<p className="pd-form-sub">` helper text is positioned between the city field and
   the notes textarea. It serves as a description for the notes textarea, but structurally
   it follows the city field with no intervening label.

2. The notes `<textarea>` has no preceding label element, making the form visually
   inconsistent — every other group in the form has a `pd-label` before its control.

### CSS — `web/src/styles.css`

Key rules (line numbers from the file as read):

| Selector | Rule (relevant parts) | Line |
|---|---|---|
| `.pd-label` | `display: block; margin: 12px 0 5px;` | 590-598 |
| `.pd-label-opt` | `font-weight: 400; text-transform: none; opacity: .7;` | 599 |
| `.pd-field` | `display: flex; align-items: center; padding: 0 12px; border-radius: 12px; border: 1.5px solid transparent;` | 515-527 |
| `.pd-field .pd-input` | `align-self: stretch; padding: 11px 0;` | 530, 587 |
| `textarea.pd-input` | `resize: vertical; min-height: 64px;` | 573 |
| `input.pd-input` (standalone) | `border: 1.5px solid var(--pd-border); padding: 11px 13px; width: 100%;` | 559-568 |
| `.pd-form-sub` | `font-size: 13px; color: var(--pd-hint); margin: -8px 0 12px; line-height: 1.5;` | 921 |
| `.pd-form-multi` | `display: flex; flex-direction: column;` | 1196 |

**Root cause of the visual overflow:** `.pd-form-sub { margin: -8px 0 12px }` was written
to pull hint text closer to a preceding `.pd-label` element. When two sibling block elements
have adjacent bottom/top margins, CSS collapses them: `pd-label` bottom = 5 px, `pd-form-sub`
top = -8 px, collapsed = 5 + (-8) = -3 px — a tight but tolerable grouping.

However, in the current markup `pd-form-sub` directly follows `label.pd-field`, which has
no declared margin-bottom (zero). The collapsed margin is therefore `0 + (-8 px) = -8 px`.
The helper paragraph is shifted 8 px upward into the city field's bottom border box,
making it visually overlap the rounded city field container. On a narrow viewport the text
in that paragraph also appears clipped against the city field background.

### Other usages of these classes

`.pd-form-sub` is only used in `CreateOrder.tsx:304`. No other screen uses it.
`.pd-label` is used without adjacent `pd-form-sub` in `Subscriptions.tsx`, `Profile.tsx`,
and `CreateOrder.tsx:258` — those are unaffected.

## Proposed solution

Two targeted edits, no new classes, no API changes.

### 1. Markup fix — `web/src/screens/CreateOrder.tsx:297-307`

Add a "Notes" label before the textarea, and move `pd-form-sub` to follow that label
(its designed context). The new fragment:

```jsx
<span className="pd-label">City <span className="pd-label-opt">· optional</span></span>
<label className="pd-field">
  <Icon name="pin" size={16} cls="pd-field-ic" />
  <input className="pd-input" inputMode="text" placeholder="e.g. Bar" value={city}
    onChange={(e) => setCity(e.target.value)}
    onFocus={(e) => scrollFieldIntoView(e.currentTarget)} />
</label>
<span className="pd-label">Notes <span className="pd-label-opt">· optional</span></span>
<p className="pd-form-sub">Anything that helps a counterparty — timing, area, preferences.</p>
<textarea className="pd-input" inputMode="text" placeholder="e.g. can meet near the marina this evening"
  value={comment} onChange={(e) => setComment(e.target.value)}
  onFocus={(e) => scrollFieldIntoView(e.currentTarget)} />
```

This places `pd-form-sub` after a `pd-label` element (its intended predecessor), so the
margin-collapse math is: 5 px (pd-label bottom) + (-8 px) (pd-form-sub top) = -3 px —
a tight but designed tight-group. The Notes label also gives the textarea a visible
semantic anchor, consistent with how Payment methods (line 258) and the City field are
labelled.

### 2. CSS fix — `web/src/styles.css:921`

Change the `pd-form-sub` top margin from -8 px to 0 to eliminate the negative-margin
dependency entirely:

```css
/* before */
.pd-form-sub { font-size: var(--pd-fs-sub); color: var(--pd-hint); margin: -8px 0 12px; line-height: 1.5; }

/* after */
.pd-form-sub { font-size: var(--pd-fs-sub); color: var(--pd-hint); margin: 0 0 10px;   line-height: 1.5; }
```

The 0 top margin means the hint text sits immediately below whatever precedes it (the Notes
label's own `margin-bottom: 5px` provides the visual gap). Bottom margin reduced from 12 px
to 10 px to preserve similar vertical rhythm above the textarea. This makes `pd-form-sub`
safe to reuse after any element without layout side effects.

### Why two edits

The markup fix alone would leave the negative margin in place; future developers adding a
`pd-form-sub` after a non-label element would rediscover the same bug. The CSS fix alone
(without adding the Notes label) would improve spacing but would leave the textarea
without a label and the helper text still logically associated with the city field.

## Alternatives

### A — CSS-only: increase `pd-form-sub` margin-top to a positive value

Change `margin: -8px 0 12px` to `margin: 8px 0 12px`. This eliminates the overlap with
no JSX change. Rejected because: the notes textarea still has no label, the helper text
still appears to belong to the city field (wrong semantics), and the spacing between the
city field and helper text becomes large and inconsistent with the rest of the form.

### B — Add a `pd-form-sub--after-field` modifier class

Introduce `.pd-form-sub--after-field { margin-top: 6px }` and apply it to the paragraph.
Rejected because: it adds a one-off modifier to work around a structural problem. The
correct structure (label → hint → field) already exists in the design system; the markup
just needs to follow it.

### C — Wrap city + notes in separate `pd-form-section` blocks

Split the single `pd-form-section` in step 3 into two (one for city, one for notes). This
adds more DOM depth and margin-bottom spacing between the two optional fields. Rejected
because: the issue calls for clean vertical rhythm, not additional vertical gap. The
existing single-section structure is simpler and the two-field fix achieves the same
visual separation via the label's own 12 px top margin.

## Platform impact

- **Migrations**: none. Pure front-end change.
- **Backward compatibility**: no API, no schema, no shared library touched.
- **Resource impact**: negligible — two CSS property edits and one JSX element added.
- **Risks**: none identified. The two classes edited (`pd-form-sub`, `pd-label`) are
  local to `web/src/styles.css` and not consumed by any server-side template. The JSX
  change is confined to `CreateOrder.tsx` step 3, which has no unit tests to break.
- **Rollback**: revert the single commit that touches `styles.css` and `CreateOrder.tsx`.
