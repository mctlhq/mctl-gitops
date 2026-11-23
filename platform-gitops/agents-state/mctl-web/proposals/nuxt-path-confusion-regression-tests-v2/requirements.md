# Post-build path-normalization smoke tests

## Context
November advisories show a recurring path-confusion class (//, %2F, /%2e/). The site is mostly prerendered, but a cheap CI guard prevents regressions and checks Worker route behaviour.

## User stories
- AS a platform owner I WANT this change SO THAT mctl.ai stays secure and maintainable

## Acceptance criteria (EARS)
- WHEN deploy.yml runs after the build THE SYSTEM SHALL request //docs, /%2e/docs, /docs%2F and repeated-slash paths against a local preview and assert expected status codes.
- WHEN the tests hit /api/* variants THE SYSTEM SHALL confirm rate limits and routing match the canonical path.
- IF a production error response contains stack, message or data details THEN THE SYSTEM SHALL fail the job.

## Out of scope
- vue-router 5 / vueuse 15 migrations
- Changes to tenant `labs`
