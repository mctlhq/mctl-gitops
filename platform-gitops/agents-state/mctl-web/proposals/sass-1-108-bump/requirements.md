# Bump sass from 1.98.0 to 1.108.0 (skip 1.106.x)

## Context
mctl-web uses sass 1.98.0. dart-sass 1.108.0 (6 Nov) reverts unintentional breaking changes (escaped identifiers in `sass:meta`, named rest args) introduced in 1.106.0, making it the first safe target after that regression. The change is build-time only: no runtime effect and no `labs` memory impact.

## User stories
- AS a maintainer I WANT a current, safe sass version SO THAT the toolchain stays up to date without regression risk.

## Acceptance criteria (EARS)
- WHEN the bump is merged THE SYSTEM SHALL pin sass to exactly 1.108.0 (no caret range).
- WHEN `nuxt build` runs THE SYSTEM SHALL produce CSS without new errors or new deprecation warnings compared to 1.98.0.
- IF the lockfile resolves sass to 1.106.x or 1.107.x THEN THE SYSTEM SHALL fail the review check.
- WHILE running in `admins` or `labs` THE SYSTEM SHALL show no change in runtime memory, since sass is build-time only.

## Out of scope
- Fixing SCSS deprecations (separate proposal `sass-deprecation-fix`).
- vite-svg-loader or other build tooling.
