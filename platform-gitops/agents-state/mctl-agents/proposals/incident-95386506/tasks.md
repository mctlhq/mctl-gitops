# Tasks: incident-95386506

1. [ ] In config/settings.py add "mctl-glovo" to NON_ROTATING_SERVICES / SERVICES, following the existing pattern.
2. [ ] Check for other places that mirror the SERVICES list (tests, schemas, enums) and update them consistently.
3. [ ] Verify the investigator no longer raises "not a known service" for https://github.com/mctlhq/mctl-glovo/issues/42 (run the unit tests).
