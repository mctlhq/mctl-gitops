# Validate runtime config at startup and remove placeholder apiSecret

## Context
nuxt.config.ts contains runtimeConfig.apiSecret = '123', a placeholder. Nuxt 4.7 supports Standard Schema validators for runtime config; yup already supports Standard Schema, so no new library is needed (ADR 0001 stays intact).

## User stories
- AS a platform owner I WANT misconfiguration to fail fast and no placeholder secrets SO THAT the public site stays secure and maintainable.

## Acceptance criteria (EARS)
- WHEN the app starts with a missing or invalid runtimeConfig value THE SYSTEM SHALL fail with one combined error.
- WHEN the config is validated THE SYSTEM SHALL not contain the placeholder apiSecret value.
- IF apiSecret is unused THEN THE SYSTEM SHALL remove it.

## Out of scope
- Replacing yup or vee-validate.
