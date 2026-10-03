#### Outcomes (`use_temporal=true`)

The response reports what actually happened for the issue's DevLoop workflow (`dev-loop-<org>-<repo>-<issue>`):

| Outcome | Meaning |
|---|---|
| `started` | No prior execution existed; a new DevLoop was started. |
| `already_running` | A DevLoop is running; nothing new was started. The existing run id is returned. |
| `already_exists` | A closed DevLoop exists; it is not restarted. |
| `failed` | The existing execution could not be read or the start failed; nothing was started blind. |

Use `mctl_get_dev_loop` to inspect the existing execution.
