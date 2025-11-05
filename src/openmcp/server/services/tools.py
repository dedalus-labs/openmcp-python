# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Tool capability service.

Implements the tools capability as specified in the Model Context Protocol:

- https://modelcontextprotocol.io/specification/2025-06-18/server/tools
  (tools capability declaration, list and call operations)
- https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/pagination
  (cursor-based pagination for tools/list)

Supports ambient tool registration, argument schema inference from type hints,
output schema inference with MCP content type blocklisting, and list-changed
notifications per the specification requirements.
"""

from __future__ import annotations

import inspect
import types as pytypes
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, get_args, get_origin, get_type_hints

from pydantic import TypeAdapter

from ..dependencies import Depends
from ..dependencies.solver import resolve as resolve_dependency
from ..notifications import NotificationSink, ObserverRegistry
from ..pagination import paginate_sequence
from ..result_normalizers import normalize_tool_result
from ... import types
from ...context import Context, context_scope, get_context
from ...tool import ToolSpec, extract_tool_spec
from ...utils import maybe_await_with_args
from ...utils.schema import SchemaError, resolve_output_schema


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from logging import Logger

    from ..core import MCPServer


class ToolsService:
    """Manages tool registration, invocation, and list notifications."""

    def __init__(
        self,
        *,
        server_ref: MCPServer,
        attach_callable: Callable[[str, Callable[..., Any]], None],
        detach_callable: Callable[[str], None],
        logger: Logger,
        pagination_limit: int,
        notification_sink: NotificationSink,
    ) -> None:
        self._server = server_ref
        self._attach = attach_callable
        self._detach = detach_callable
        self._logger = logger
        self._pagination_limit = pagination_limit
        self._tool_specs: dict[str, ToolSpec] = {}
        self._tool_defs: dict[str, types.Tool] = {}
        self._attached_names: set[str] = set()
        self._allow: set[str] | None = None
        self.observers = ObserverRegistry(notification_sink)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def tool_names(self) -> list[str]:
        return sorted(self._tool_defs)

    @property
    def definitions(self) -> dict[str, types.Tool]:
        return self._tool_defs

    def register(self, target: ToolSpec | Callable[..., Any]) -> ToolSpec:
        spec: ToolSpec | None
        if isinstance(target, ToolSpec):
            spec = target
        else:
            fn = target
            spec = extract_tool_spec(fn)
            if spec is None:
                spec = ToolSpec(name=getattr(fn, "__name__", "anonymous"), fn=fn)

        assert spec is not None  # narrow for mypy
        self._tool_specs[spec.name] = spec
        self._server.record_tool_mutation(operation="register")
        self._refresh_tools()
        return spec

    def allow_tools(self, names: Iterable[str] | None) -> None:
        self._allow = set(names) if names is not None else None
        self._server.record_tool_mutation(operation="allow_tools")
        self._refresh_tools()

    async def list_tools(self, request: types.ListToolsRequest | None) -> types.ListToolsResult:
        with context_scope():
            cursor = None
            if request is not None and request.params is not None:
                cursor = request.params.cursor

            filtered: list[types.Tool] = []
            for name, tool_def in self._tool_defs.items():
                spec = self._tool_specs.get(name)
                if spec is None:
                    continue
                if not await self._tool_enabled_this_request(spec):
                    continue
                filtered.append(tool_def)

            page, next_cursor = paginate_sequence(filtered, cursor, limit=self._pagination_limit)
            self.observers.remember_current_session()
            return types.ListToolsResult(tools=page, nextCursor=next_cursor)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        with context_scope():
            spec = self._tool_specs.get(name)
            if not spec or name not in self._tool_defs:
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=f'Tool "{name}" is not available')], isError=True
                )

            if not await self._tool_enabled_this_request(spec):
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=f'Tool "{name}" is temporarily unavailable')],
                    isError=True,
                )

            call_kwargs = await self._build_call_kwargs(spec, arguments)

            try:
                result = await maybe_await_with_args(spec.fn, **call_kwargs)
            except TypeError as exc:  # argument mismatch
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=f"Invalid arguments: {exc}")], isError=True
                )

            if isinstance(result, types.ServerResult):
                message = "Tool returned types.ServerResult; return the nested CallToolResult instead."
                raise TypeError(message)

            return normalize_tool_result(result)

    async def notify_list_changed(self) -> None:
        notification = types.ServerNotification(types.ToolListChangedNotification(params=None))
        await self.observers.broadcast(notification, self._logger)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_tools(self) -> None:
        for name in list(self._attached_names):
            self._detach(name)
        self._attached_names.clear()
        self._tool_defs.clear()

        for spec in self._tool_specs.values():
            if not self._is_tool_enabled(spec):
                continue

            annotations_payload: dict[str, Any] = dict(spec.annotations or {})
            if spec.tags:
                existing = annotations_payload.get("tags", [])
                combined = {*(existing if isinstance(existing, (list, tuple, set)) else [existing]), *spec.tags}
                annotations_payload["tags"] = sorted(str(tag) for tag in combined if tag not in (None, ""))
            if spec.title is not None and "title" not in annotations_payload:
                annotations_payload = {**annotations_payload, "title": spec.title}
            annotations = None
            if annotations_payload:
                annotations = types.ToolAnnotations.model_validate(annotations_payload)

            icons = None
            if spec.icons is not None:
                icons = [types.Icon.model_validate(icon) for icon in spec.icons]

            tool_def = types.Tool(
                name=spec.name,
                description=spec.description or None,
                inputSchema=spec.input_schema or self._build_input_schema(spec.fn),
                outputSchema=spec.output_schema or self._build_output_schema(spec.fn),
                annotations=annotations,
                icons=icons,
            )
            self._tool_defs[spec.name] = tool_def
            self._attach(spec.name, spec.fn)
            self._attached_names.add(spec.name)

    def _is_tool_enabled(self, spec: ToolSpec) -> bool:
        if self._allow is not None and spec.name not in self._allow:
            return False
        enabled = spec.enabled
        if enabled is None:
            return True
        if isinstance(enabled, Depends):
            return True
        return bool(enabled(self._server))

    async def _tool_enabled_this_request(self, spec: ToolSpec) -> bool:
        enabled = spec.enabled
        if enabled is None:
            return True
        if isinstance(enabled, Depends):
            result = await resolve_dependency(enabled)
            return bool(result)
        return bool(await maybe_await_with_args(enabled, self._server))

    async def _build_call_kwargs(self, spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
        kwargs = dict(arguments)
        signature = inspect.signature(spec.fn)

        for name, param in signature.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if name in kwargs:
                continue

            dependency = None

            if isinstance(param.default, Depends):
                dependency = param.default
            elif isinstance(param.annotation, Depends):  # pragma: no cover - defensive
                dependency = param.annotation  # type: ignore[assignment]

            if dependency is not None:
                kwargs[name] = await resolve_dependency(dependency)
                continue

            if self._annotation_requires_context(param.annotation):
                try:
                    kwargs[name] = get_context()
                except LookupError:
                    raise TypeError(
                        f"Cannot inject context for parameter '{name}' outside of an MCP request"
                    ) from None
                continue

            if param.default is not inspect.Parameter.empty:
                kwargs[name] = param.default
                continue

            raise TypeError(f"Missing required argument '{name}' for tool '{spec.name}'")

        return kwargs

    @staticmethod
    def _annotation_requires_context(annotation: Any) -> bool:
        if annotation is inspect.Parameter.empty:
            return False
        if annotation is Context:
            return True
        origin = get_origin(annotation)
        if origin:
            return any(ToolsService._annotation_requires_context(arg) for arg in get_args(annotation))
        return False

    def _build_input_schema(self, fn: Callable[..., Any]) -> dict[str, Any]:
        signature = inspect.signature(fn)
        annotations: dict[str, Any] = {}
        descriptions: dict[str, str] = {}
        default_values: dict[str, Any] = {}

        for name, param in signature.parameters.items():
            if param.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
                return {"type": "object"}

            annotation = param.annotation if param.annotation is not inspect.Parameter.empty else Any
            descriptions[name] = f"Parameter {name}"

            if param.default is inspect.Parameter.empty:
                annotations[name] = annotation
            else:
                annotations[name] = NotRequired[annotation]
                default_values[name] = param.default

        if not annotations:
            return {"type": "object", "properties": {}, "additionalProperties": False}

        namespace = {"__annotations__": annotations}
        typed_dict = pytypes.new_class(
            f"{fn.__name__.title()}ToolInput", (TypedDict,), {}, lambda ns: ns.update(namespace)
        )

        try:
            schema = TypeAdapter(typed_dict).json_schema()
        except (TypeError, ValueError, NameError) as exc:  # pragma: no cover - pydantic raised unexpected error
            self._logger.debug("Failed to derive input schema for %s: %s", fn.__name__, exc)
            return {"type": "object", "additionalProperties": True}

        schema.pop("$defs", None)

        properties = schema.setdefault("properties", {})
        required = []
        for name, desc in descriptions.items():
            properties.setdefault(name, {})
            properties[name].setdefault("description", desc)
            if name in default_values:
                properties[name].setdefault("default", default_values[name])
            else:
                required.append(name)

        schema.setdefault("type", "object")
        schema["additionalProperties"] = False
        if required:
            schema["required"] = required
        _prune_titles(schema)
        return schema

    def _build_output_schema(self, fn: Callable[..., Any]) -> dict[str, Any] | None:
        signature = inspect.signature(fn)
        annotation = signature.return_annotation
        if annotation in (inspect.Signature.empty, Any, None):
            return None

        try:
            closure_ns: dict[str, Any] = {}
            if fn.__closure__:
                for cell in fn.__closure__:
                    try:
                        value = cell.cell_contents
                    except ValueError:
                        continue
                    name = getattr(value, "__name__", None)
                    if isinstance(name, str):
                        closure_ns.setdefault(name, value)

            resolved = get_type_hints(fn, include_extras=True, localns=closure_ns)
            annotation = resolved.get("return", annotation)
        except (NameError, TypeError) as exc:  # pragma: no cover - deferred evaluation failed
            self._logger.debug("Failed to resolve return annotation for %s: %s", fn.__name__, exc)

        if annotation in (Any, None, types.CallToolResult, types.ServerResult):
            return None

        if _annotation_contains(annotation, _OUTPUT_SCHEMA_BLOCKLIST):
            return None

        try:
            envelope = resolve_output_schema(annotation)
        except SchemaError:
            return None

        schema = envelope.schema
        schema.pop("$defs", None)
        _prune_titles(schema)
        return schema


def _annotation_contains(annotation: object, targets: tuple[type[Any], ...]) -> bool:
    origin = get_origin(annotation)
    if origin is None:
        return any(
            annotation is target or (inspect.isclass(annotation) and issubclass(annotation, target))
            for target in targets
            if inspect.isclass(target)
        )
    return any(_annotation_contains(arg, targets) for arg in get_args(annotation))


def _prune_titles(schema: object) -> None:
    if isinstance(schema, dict):
        schema.pop("title", None)
        for value in schema.values():
            _prune_titles(value)
    elif isinstance(schema, list):
        for item in schema:
            _prune_titles(item)


_OUTPUT_SCHEMA_BLOCKLIST: tuple[type[Any], ...] = (
    types.CallToolResult,
    types.ServerResult,
    types.TextContent,
    types.ImageContent,
    types.AudioContent,
    types.ResourceLink,
    types.EmbeddedResource,
)
