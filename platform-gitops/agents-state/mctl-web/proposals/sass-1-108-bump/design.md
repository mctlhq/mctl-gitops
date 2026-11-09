# Design: sass-1-108-bump

## Current state
sass 1.98.0 compiles SCSS in the Nuxt/Vite build (`context/architecture.md`). Output is static CSS in `dist/`.

## Proposed solution
Change `sass` in `package.json` to the exact version `1.108.0` and regenerate the lockfile. Compare built CSS and build warnings before and after. Exact pinning avoids landing on 1.106.x/1.107.x via a range. Can be merged independently of the Nuxt upgrade, or in the same release train.

## Alternatives
- Caret range `^1.108.0`: could allow a future regression; dropped in favour of an exact pin.
- Stay on 1.98.0: no benefit, grows the gap; dropped.
- Jump only to 1.105.x: skips the revert fix and is not the latest; dropped.

## Platform impact
- Migrations: none.
- Backward compatibility: 1.108.0 restores behaviour broken in 1.106.0; diff the CSS output to confirm.
- Resource impact: build-time only; no runtime or `labs` memory impact.
- Risks and mitigations: unexpected CSS diff or new deprecation warnings (review the diff; revert if visual change).
