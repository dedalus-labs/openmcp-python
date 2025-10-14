"""Completion capability service."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ...completion import CompletionResult, CompletionSpec, extract_completion_spec
from ... import types
from ...utils import maybe_await_with_args


class CompletionService:
    def __init__(self) -> None:
        self._completion_specs: dict[tuple[str, str], CompletionSpec] = {}

    def register(self, target) -> CompletionSpec:
        spec = target if isinstance(target, CompletionSpec) else extract_completion_spec(target)
        if spec is None:
            raise ValueError("Completion functions must be decorated with @completion")
        self._completion_specs[(spec.ref_type, spec.key)] = spec
        return spec

    async def execute(
        self,
        ref: types.PromptReference | types.ResourceTemplateReference,
        argument: types.CompletionArgument,
        context: types.CompletionContext | None,
    ) -> types.Completion | None:
        spec = self._get_spec(ref)
        if spec is None:
            return types.Completion(values=[], total=None, hasMore=None)

        result = await maybe_await_with_args(spec.fn, argument, context)

        return self._coerce_completion(result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_spec(
        self,
        ref: types.PromptReference | types.ResourceTemplateReference,
    ) -> CompletionSpec | None:
        if isinstance(ref, types.PromptReference):
            return self._completion_specs.get(("prompt", ref.name))
        return self._completion_specs.get(("resource", ref.uri))

    def _coerce_completion(
        self,
        result: types.Completion
        | CompletionResult
        | Iterable[Any]
        | Mapping[str, Any]
        | str
        | None,
    ) -> types.Completion | None:
        if result is None:
            return None
        if isinstance(result, types.Completion):
            return self._limit_completion(result)
        if isinstance(result, CompletionResult):
            return self._from_values(result.values, result.total, result.has_more)
        if isinstance(result, Mapping):
            values = result.get("values")
            if values is None:
                raise ValueError("Completion mapping must include 'values'.")
            total = result.get("total")
            has_more = result.get("hasMore", result.get("has_more"))
            return self._from_values(values, total, has_more)
        if isinstance(result, str):
            return self._from_values([result], None, None)
        if isinstance(result, Iterable):
            return self._from_values(result, None, None)
        raise TypeError(f"Unsupported completion return type: {type(result)!r}")

    def _from_values(
        self,
        values: Iterable[Any],
        total: int | None,
        has_more: bool | None,
    ) -> types.Completion:
        coerced = [str(value) for value in values]
        limited, limited_has_more = self._limit_values(coerced, has_more)
        return types.Completion(values=limited, total=total, hasMore=limited_has_more)

    def _limit_completion(self, completion: types.Completion) -> types.Completion:
        limited, has_more = self._limit_values(list(completion.values), completion.hasMore)
        return types.Completion(values=limited, total=completion.total, hasMore=has_more)

    def _limit_values(
        self,
        values: list[str],
        has_more: bool | None,
    ) -> tuple[list[str], bool | None]:
        limit = 100
        if len(values) <= limit:
            return values, has_more
        truncated = values[:limit]
        return truncated, True if has_more is None else has_more
