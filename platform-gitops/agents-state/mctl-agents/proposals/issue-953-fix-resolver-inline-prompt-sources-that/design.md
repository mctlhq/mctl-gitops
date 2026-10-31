# Design: issue-953-fix-resolver-inline-prompt-sources-that

## Current state
- `orchestrator/resolver.py:947-978` `_hash_prompt_source(source: PromptSource)`:
  - `file` hashes the bytes on disk through `_content_hash`.
  - `glob` hashes the concatenated bytes of the sorted matches.
  - `inline` partitions `module:symbol`, runs `importlib.import_module(module_name.replace("/", ".").removesuffix(".py"))` and `getattr`, then `inspect.getsource(obj)`. It catches `(ImportError, AttributeError, ValueError, TypeError, OSError)` and raises `ResolverError("prompt source inline ref does not resolve: ...")`.
  - For a `str`, `inspect.getsource` raises `TypeError`, so the call always fails.
- `orchestrator/resolver.py:1157`: `ExecutionPlan.prompt_hashes = tuple(_hash_prompt_source(s) for s in definition.prompt_sources)`. This is the only caller, and it is reached through `execute()`.
- `PromptSource` is defined in `orchestrator/manifest.py:52` (`kind`, `value`). `manifest.load_all()` (`manifest.py:321`) loads every `agents/_manifests/*/agent.yaml`.
- Inline sources in the manifests:
  - Functions: `run_shepherd.py:_format_bundle_via_sdk`, `run_mentor.py:build_prompt`, and `_build_prompt` in issue-investigator, incident-responder and implementer.
  - `str` constants: `run_service_agent.py:PROMPT` (line 82), `run_authoring_canary.py:PROMPT` (line 15), and `run_scout.py:RELEVANCE_PROMPT` / `SCORING_PROMPT` (lines 32 and 38).
- Tests:
  - `tests/test_resolver.py:782` pins the function-hash formula for `run_issue_investigator._build_prompt`.
  - `:793` checks that `":symbol"` fails closed.
  - `:801` checks that `builtins:len` fails closed. A builtin function is not a `str`, so it must keep failing.
  - `tests/test_agent_inventory.py:80-101` and `orchestrator/validate_manifest.py:193-229` only check `hasattr`.
- `tools/publish_agent_release.py` uses its own scheme (it hashes the whole file for inline sources) and is not involved.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/agent-platform/releases/shadow/` (directory listing): it contains `authoring-canary.yaml`, `scout.yaml` and `service-agent.yaml`, along with implementer, incident-responder, issue-investigator, mentor and shepherd. This confirms the issue's statement that shadow intents exist for the three affected agents.
- `$MCTL_GITOPS_ROOT/agent-platform/releases/production/`: does not exist in this checkout. I did not look for production bindings anywhere else, so this is not evidence that none exist.
- No mctl MCP tools were called. The change is library code in the resolver and has no deployed service configuration to check.

## Proposed solution
Change only the `inline` branch of `_hash_prompt_source`:

```python
if source.kind == "inline":
    module_name, _, symbol = source.value.partition(":")
    try:
        module = importlib.import_module(module_name.replace("/", ".").removesuffix(".py"))
        obj = getattr(module, symbol)
    except (ImportError, AttributeError, ValueError, TypeError) as exc:
        raise ResolverError(f"prompt source inline ref does not resolve: {source.value} ({exc})") from exc
    if isinstance(obj, str):
        # inspect.getsource rejects a str. Hash the value, prefixed so it
        # cannot collide with a callable whose source is the same text.
        payload = "str:" + obj
    elif inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.isclass(obj):
        try:
            payload = inspect.getsource(obj)
        except (TypeError, OSError) as exc:
            raise ResolverError(f"prompt source inline ref has no retrievable source: {source.value} ({exc})") from exc
    else:
        raise ResolverError(
            f"prompt source inline ref is not a str or function: {source.value} ({type(obj).__name__})"
        )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
```

Notes:
- Function hashes are unchanged: the payload is `inspect.getsource(obj)` and is hashed the same way. The test at `tests/test_resolver.py:782` still holds.
- `builtins:len` is a builtin function. `inspect.isfunction` returns False for it, so it gets the explicit type `ResolverError`. Either way it still fails closed, which satisfies `:801`.
- The narrower allow-list (`isfunction`, `ismethod`, `isclass`) is deliberate. Today any object `inspect.getsource` accepts is hashed, including a module. Keeping class support costs nothing. A module object as an inline ref would hash the whole module, which nothing uses today. If the implementer finds that keeping "anything getsource accepts" is safer, they may instead call `getsource` for every non-str and keep the existing `TypeError` catch. The acceptance criteria hold either way.
- Update the docstring to say that `inline` hashes a callable's source text, or `"str:" + value` for a string constant.
- New test in `tests/test_resolver.py`: parametrize over `manifest.load_all().values()` and over each manifest's `prompt_sources`, assert that `_hash_prompt_source` returns a string matching `^sha256:[0-9a-f]{64}$`, and add explicit checks for the four str refs. The test needs no gitops catalog: `_hash_prompt_source` does not touch `CATALOG_DIR`.

## Alternatives
1. **Hash the AST source segment of the assignment** (issue option 2). This would use `ast.parse` on the module file, find the `Assign`/`AnnAssign` whose target is `symbol`, and hash `ast.get_source_segment`. It keeps "hash source text" uniform, but it adds parsing code and edge cases: tuple targets, reassignment, prompts built by concatenation or `.format` at import time, where the source segment differs from the runtime value. Dropped as more code for no benefit to current cases. Hashing the runtime value is also arguably better provenance, because it is what the model actually receives.
2. **Hash the whole module file for every inline source** (the `publish_agent_release.py` approach). This is robust, but it changes every existing function hash, which breaks `tests/test_resolver.py:782` and the issue's acceptance criterion. It also makes the hash churn on unrelated edits. Dropped.
3. **Turn the four constants into functions** (`def prompt() -> str`). This fixes the symptom in the manifests, but it leaves the resolver branch broken for the next str ref and churns the callers. It also conflicts with #947, which needs `run_service_agent.py:PROMPT` to stay a `str`. Dropped.

## Platform impact
- No migration and no gitops change. Hashes already recorded for function sources are unchanged.
- The four str sources had no hash before, because `execute()` failed on them. Their first hashes are new values, so nothing existing is invalidated.
- Backward compatibility: the only behaviour change is that str refs now succeed. Every other error path still raises `ResolverError`. Only the message for an unsupported type changes.
- Risk: the `str:` prefix becomes part of the hash contract. A later change to the encoding would change these hashes. Mitigation: document the prefix in the docstring and pin it in a test.
- Resource impact: negligible.
