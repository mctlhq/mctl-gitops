# Design: vue-patch-3-5-33

## Current state

According to `context/architecture.md`, **Vue 3.5.30** is in use. Vue is a transitive dependency — installed as a peer dependency of Nuxt. In the mctl-web `package.json`, Vue may be specified explicitly or resolved through Nuxt.

## Proposed solution

**Targeted Vue bump to 3.5.33:**

1. If `vue` is listed explicitly in `package.json` (in `dependencies` or `devDependencies`) — update to `"^3.5.33"`.
2. If `vue` is resolved transitively through Nuxt — force a lockfile update (`npm update vue` / `pnpm update vue`), confirming version 3.5.33 is pinned.
3. Run `nuxt build` for validation.

The change is strictly a patch: Vue follows semver, and patch versions contain no breaking changes.

This update is recommended **before** the Nuxt 4.4.2 upgrade (task `nuxt-upgrade-4-4-2`) to ease debugging: it makes the source of any issues easier to isolate.

## Alternatives

1. **Wait for Vue 3.6.0** — there is no reason to delay a patch update for a future minor. Dropped.
2. **Skip the update, fold it into Nuxt updates** — possible, but if Nuxt 4.4.2 already pulls Vue 3.5.33 transitively, then a single Nuxt PR resolves both. In that case this proposal can be closed as subsumed by `nuxt-upgrade-4-4-2`. Dropped as a backup plan: the isolated quick bump now is preferable.
3. **Pin to 3.5.33** without `^` — overly strict for patch releases. Dropped.

## Platform impact

- **Migration:** none — patch release within 3.5.x.
- **Backward compatibility:** full — semver guarantees no breaking changes in patch versions.
- **Resource impact:** zero — the bundle size barely changes between patch versions.
- **Risks and mitigations:** very low regression risk. Mitigation: `nuxt build` + a smoke test in staging.
