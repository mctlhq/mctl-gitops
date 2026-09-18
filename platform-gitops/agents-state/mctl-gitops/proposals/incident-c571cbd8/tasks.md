# Tasks: incident-c571cbd8

1. [ ] Edit `platform-gitops/services/labs/mctl-telegram/values.yaml`: change
       `resources.limits.memory` from `256Mi` to `512Mi`. Leave
       `resources.requests.memory`, all `resources.limits.cpu` /
       `resources.requests.cpu` values, and every other field unchanged.
2. [ ] Verify the diff touches only that one line (plus, if needed, its
       inline comment) and that the file still parses as valid YAML.
3. [ ] No image tag bump or other dependent change is needed — this is a
       resource-limit-only change to an already-deployed image (0.67.0).
