# Hash str-constant inline prompt sources in the resolver

## Context
`orchestrator/resolver.py::_hash_prompt_source` handles an `inline:` prompt source by importing `module:symbol` and hashing `inspect.getsource(obj)`. `inspect.getsource` raises `TypeError` for a module-level `str`, and the resolver turns that into `ResolverError("prompt source inline ref does not resolve: ...")`. Four of the nine `inline:` sources in `agents/_manifests/*/agent.yaml` are `str` constants: `orchestrator/run_service_agent.py:PROMPT`, `orchestrator/run_authoring_canary.py:PROMPT`, `orchestrator/run_scout.py:RELEVANCE_PROMPT` and `orchestrator/run_scout.py:SCORING_PROMPT`.

Today the bug is latent. Only issue-investigator runs through `resolver.execute()`, and its prompt source is a function. But mctl-gitops already has shadow `ReleaseBindingIntent`s for service-agent, scout and authoring-canary (`platform-gitops/agent-platform/releases/shadow/`). As soon as any of them is resolved through `execute()`, the run is refused. Until then, editing these constants changes no prompt hash, which weakens provenance. This proposal takes the issue's option 1: when the object is a `str`, hash a domain-separated form of its value; callables keep `inspect.getsource`; any other type still fails closed.

## User stories
- AS a platform operator I WANT service-agent, scout and authoring-canary to resolve through `resolver.execute()` SO THAT moving them onto the declarative release path is not refused on a prompt-hash error.
- AS an auditor of execution plans I WANT a prompt hash that changes whenever one of these str prompts changes SO THAT `ExecutionPlan.prompt_hashes` shows prompt drift.
- AS a maintainer I WANT CI to hash every manifest `inline:` ref SO THAT a ref that cannot be hashed fails in CI instead of at `execute()` time.

## Acceptance criteria (EARS)
- WHEN `_hash_prompt_source` receives an `inline` source whose symbol resolves to a `str` THE SYSTEM SHALL return `"sha256:" + sha256(("str:" + value).encode("utf-8")).hexdigest()`.
- WHEN the value of such a `str` constant changes THE SYSTEM SHALL return a different hash.
- WHEN an `inline` source resolves to a function, method or class THE SYSTEM SHALL return exactly `"sha256:" + sha256(inspect.getsource(obj).encode()).hexdigest()`, the same value as today.
- IF an `inline` source resolves to any other type (for example `int`, `bytes`, a class instance, or a builtin such as `builtins:len`) THEN THE SYSTEM SHALL raise `ResolverError`.
- IF an `inline` ref has an empty module path (`":symbol"`), a module that will not import, or a missing symbol THEN THE SYSTEM SHALL raise `ResolverError`.
- WHEN the test suite runs THE SYSTEM SHALL compute `_hash_prompt_source` for every prompt source of every manifest loaded by `orchestrator.manifest.load_all()`, and fail if any of them raises.
- WHILE `str` constants are hashed by value THE SYSTEM SHALL keep a `str` value and a function whose source text is the same string from producing the same hash (the `str:` prefix).
- WHILE this change is in place THE SYSTEM SHALL keep `tests/test_agent_inventory.py` and the existing `tests/test_resolver.py` expectations passing without changes.

## Out of scope
- Moving inline prompts into files under `agents/` (mctlhq/mctl-agents#603).
- Changing `tools/publish_agent_release.py`, which hashes the whole named file for `inline:` sources and is unaffected.
- Moving service-agent, scout or authoring-canary onto `resolver.execute()` at runtime, or editing any gitops release intent.
- Hashing the source text of the assignment through AST (the issue's option 2).
- Extending `orchestrator/validate_manifest.py::_check_prompt_sources` to do more than its current `hasattr` check (recorded as an open question).

## Open questions
- Should `validate_manifest._check_prompt_sources` also call the resolver's hash, rather than only `hasattr`, so the manifest validator catches this class of bug too? Assumed no here: the new pytest covers CI, and keeping the change small is preferred. The implementer may add it if it is a one-line reuse.
- Should `bytes` constants be supported as well? Assumed no: no manifest uses one today, and an unsupported type fails closed.
