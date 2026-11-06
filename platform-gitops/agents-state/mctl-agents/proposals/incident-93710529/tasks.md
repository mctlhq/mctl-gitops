# Tasks: incident-93710529

1. [ ] Locate the shepherd PR snapshot helper that calls `gh api graphql` and add bounded retry with backoff on HTTP 502/503/504 only.
2. [ ] Update the assert-attempt step message to include GitHub 5xx snapshot failures as a possible cause.
3. [ ] Verify existing shepherd tests pass and add a test for the 503-then-success path.
