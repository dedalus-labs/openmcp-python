# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Prompt capability service.

Implements the prompts capability as specified in the Model Context Protocol:

- https://modelcontextprotocol.io/specification/2025-06-18/server/prompts
  (prompts capability, list and get operations, list-changed notifications)
- https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/pagination
  (cursor-based pagination for prompts/list)

Handles prompt registration, argument validation, and result coercion from
various return types (GetPromptResult, tuples, dicts) to MCP message format.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from mcp.shared.exceptions import McpError

from ..notifications import NotificationSink, ObserverRegistry
from ..pagination import paginate_sequence
from ... import types
from ...context import context_scope
from ...prompt import PromptSpec, extract_prompt_spec
from ...utils import maybe_await_with_args


class PromptsService:
    def __init__(self, *, logger, pagination_limit: int, notification_sink: NotificationSink) -> None:
        self._logger = logger
        self._pagination_limit = pagination_limit
        self._prompt_specs: dict[str, PromptSpec] = {}
        self._prompt_defs: dict[str, types.Prompt] = {}
        self.observers = ObserverRegistry(notification_sink)

    def register(self, target: PromptSpec | Callable[..., Any]) -> PromptSpec:
        spec = target if isinstance(target, PromptSpec) else extract_prompt_spec(target)  # type: ignore[arg-type]
        if spec is None:
            raise ValueError("Prompt functions must be decorated with @prompt")
        self._prompt_specs[spec.name] = spec
        self._refresh_prompts()
        return spec

    @property
    def names(self) -> list[str]:
        return sorted(self._prompt_defs)

    async def list_prompts(self, request: types.ListPromptsRequest) -> types.ListPromptsResult:
        with context_scope():
            cursor = request.params.cursor if request.params is not None else None
            prompts = list(self._prompt_defs.values())
            page, next_cursor = paginate_sequence(prompts, cursor, limit=self._pagination_limit)
            self.observers.remember_current_session()
            return types.ListPromptsResult(prompts=page, nextCursor=next_cursor)

    async def get_prompt(self, name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
        with context_scope():
            spec = self._prompt_specs.get(name)
            if spec is None:
                raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message=f"Prompt '{name}' is not registered"))

            provided = dict(arguments or {})
            missing = [arg.name for arg in (spec.arguments or []) if arg.required and arg.name not in provided]
            if missing:
                raise McpError(
                    types.ErrorData(
                        code=types.INVALID_PARAMS, message=f"Missing required arguments: {', '.join(sorted(missing))}"
                    )
                )

            try:
                rendered = await maybe_await_with_args(spec.fn, provided if spec.arguments else provided)  # type: ignore[arg-type]
            except TypeError as exc:
                raise TypeError(str(exc)) from exc

            return self._coerce_prompt_result(spec, rendered)

    async def notify_list_changed(self) -> None:
        notification = types.ServerNotification(types.PromptListChangedNotification(params=None))
        await self.observers.broadcast(notification, self._logger)

    def _refresh_prompts(self) -> None:
        self._prompt_defs.clear()
        for spec in self._prompt_specs.values():
            prompt = types.Prompt(
                name=spec.name,
                title=spec.title,
                description=spec.description,
                arguments=spec.arguments,
                icons=spec.icons,
                meta=dict(spec.meta) if spec.meta is not None else None,
            )
            self._prompt_defs[spec.name] = prompt

    def _coerce_prompt_result(self, spec: PromptSpec, result: Any) -> types.GetPromptResult:
        if isinstance(result, types.GetPromptResult):
            description = result.description or spec.description
            return types.GetPromptResult(messages=result.messages, description=description)

        if isinstance(result, dict):
            messages = result.get("messages")
            if messages is None:
                raise TypeError("Prompt mapping must include 'messages'")
            description = result.get("description", spec.description)
            return types.GetPromptResult(messages=self._coerce_prompt_messages(messages), description=description)

        if result is None:
            return types.GetPromptResult(messages=[], description=spec.description)

        if isinstance(result, str):
            raise TypeError("Prompt renderer returned raw string; supply role + content.")

        return types.GetPromptResult(messages=self._coerce_prompt_messages(result), description=spec.description)

    def _coerce_prompt_messages(self, values: Iterable[Any]) -> list[types.PromptMessage]:
        messages: list[types.PromptMessage] = []
        for item in values:
            messages.append(self._coerce_prompt_message(item))
        return messages

    def _coerce_prompt_message(self, item: Any) -> types.PromptMessage:
        if isinstance(item, types.PromptMessage):
            return item

        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content")
            if role is None or content is None:
                raise TypeError("Prompt message mapping requires 'role' and 'content'.")
            return types.PromptMessage(role=str(role), content=self._coerce_prompt_content(content))

        if isinstance(item, (tuple, list)) and len(item) == 2:
            role, content = item
            return types.PromptMessage(role=str(role), content=self._coerce_prompt_content(content))

        raise TypeError("Prompt message must be PromptMessage, mapping, or (role, content) tuple.")

    def _coerce_prompt_content(self, content: Any) -> types.ContentBlock:
        if isinstance(
            content,
            (types.TextContent, types.ImageContent, types.AudioContent, types.ResourceLink, types.EmbeddedResource),
        ):
            return content

        if isinstance(content, str):
            return types.TextContent(type="text", text=content)

        if isinstance(content, dict):
            content_type = content.get("type")
            if content_type == "text":
                return types.TextContent(**content)
            if content_type == "image":
                return types.ImageContent(**content)
            if content_type == "audio":  # pragma: no cover - seldom used
                return types.AudioContent(**content)
            if content_type == "resource":
                resource_payload = content.get("resource")
                if isinstance(resource_payload, dict):
                    try:
                        resource = types.TextResourceContents(**resource_payload)
                    except Exception:
                        resource = types.BlobResourceContents(**resource_payload)
                else:
                    raise TypeError("Embedded resource requires mapping payload.")
                return types.EmbeddedResource(type="resource", resource=resource)

        raise TypeError(f"Unsupported prompt content: {type(content)!r}")
