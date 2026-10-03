# Tasks: incident-88963642

1. [ ] In the mctl-agents repo, check whether `agents/seerrsense/` already exists.
2. [ ] Edit `config/settings.py`: add `"seerrsense"` to `NON_ROTATING_SERVICES` if no
       `agents/seerrsense/` scaffold exists, otherwise add it to `SERVICES`.
3. [ ] Confirm the edited list is still valid Python (no syntax errors, no duplicate entries).
4. [ ] No image tag bump needed — this is a config/data change picked up on next run.
