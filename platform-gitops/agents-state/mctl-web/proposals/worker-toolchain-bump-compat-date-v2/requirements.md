# Bump wrangler/workerd toolchain and review compatibility_date

## Context
workerd v1.20261120.1 (20 Nov) is newer than the 13 Nov release targeted earlier. fetch() now throws TypeError on an unparseable response head, which could affect calls to Backstage, Telegram and Resend.

## User stories
- AS a platform owner I WANT this change SO THAT mctl.ai stays secure and maintainable

## Acceptance criteria (EARS)
- WHEN the Worker is built THE SYSTEM SHALL use a pinned wrangler version that bundles workerd >= 1.20261120.1.
- WHEN the OAuth, submit and contact flows run in staging THE SYSTEM SHALL behave identically to before.
- IF an upstream call fails with a TypeError THEN THE SYSTEM SHALL return a handled error and not leak details.
- WHILE autogated features are experimental THE SYSTEM SHALL NOT enable them.

## Out of scope
- vue-router 5 / vueuse 15 migrations
- Changes to tenant `labs`
