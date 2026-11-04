# Tasks: issue-953-fix-resolver-inline-prompt-sources-that

- [ ] 1. In `orchestrator/resolver.py::_hash_prompt_source`, split the `inline` branch into three steps: resolve (import/getattr, catching `ImportError, AttributeError, ValueError, TypeError`), classify (`str` gives the payload `"str:" + obj`; function, method or class gives `inspect.getsource(obj)` with `TypeError, OSError` turned into `ResolverError`; anything else raises `ResolverError` naming the type), then hash. — DoD: the four str refs hash, the function hash formula is byte-identical to before, and other types raise `ResolverError`.
- [ ] 2. Update the `_hash_prompt_source` docstring to describe the str encoding and the `str:` domain-separation prefix (depends on 1). — DoD: the docstring matches the behaviour.
- [ ] 3. Add the tests below to `tests/test_resolver.py` (depends on 1). — DoD: `pytest tests/test_resolver.py tests/test_agent_inventory.py` passes.

## Tests
- [ ] T1. Parametrized over every `(manifest, source)` from `orchestrator.manifest.load_all()`: `_hash_prompt_source(source)` matches `^sha256:[0-9a-f]{64}$`. No gitops catalog is required.
- [ ] T2. For each of `orchestrator/run_service_agent.py:PROMPT`, `orchestrator/run_authoring_canary.py:PROMPT`, `orchestrator/run_scout.py:RELEVANCE_PROMPT` and `orchestrator/run_scout.py:SCORING_PROMPT`: the hash equals `"sha256:" + sha256(("str:" + getattr(module, sym)).encode()).hexdigest()`, and two calls return the same value.
- [ ] T3. Monkeypatch `run_authoring_canary.PROMPT` to a different string: the hash changes.
- [ ] T4. Monkeypatch a module attribute to an `int` and to a plain `object()` instance: both raise `ResolverError`.
- [ ] T5. Domain separation: given a str constant and a function in the test module whose `inspect.getsource` text equals that constant, the two hashes differ.
- [ ] T6. The existing `test_prompt_hash_changes_when_prompt_source_changes`, `test_hash_prompt_source_fails_closed_on_empty_module_path` and `test_hash_prompt_source_fails_closed_on_unretrievable_source` pass unchanged, and `tests/test_agent_inventory.py` stays green.

## Rollback
Revert the commit. The resolver goes back to refusing str inline refs. Nothing persisted depends on the new str hashes, because no plan could have been produced for those agents before this change. Function hashes are identical either way.
