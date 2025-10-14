"""Composable MCP server built on the reference SDK."""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import Any
from collections.abc import Callable, Iterable, Mapping

from .._sdk_loader import ensure_sdk_importable

ensure_sdk_importable()

import mcp.types as types
from mcp.server.lowlevel.server import NotificationOptions, Server, lifespan as default_lifespan
from mcp.server.models import InitializationOptions
from mcp.shared.exceptions import McpError

from ..completion import (
    CompletionSpec,
    reset_active_server as reset_completion_server,
    set_active_server as set_completion_server,
)
from ..prompt import (
    PromptSpec,
    reset_active_server as reset_prompt_server,
    set_active_server as set_prompt_server,
)
from ..resource import (
    ResourceSpec,
    reset_active_server as reset_resource_server,
    set_active_server as set_resource_server,
)
from ..resource_template import (
    ResourceTemplateSpec,
    reset_active_server as reset_resource_template_server,
    set_active_server as set_resource_template_server,
)
from ..tool import (
    ToolSpec,
    reset_active_server as reset_tool_server,
    set_active_server as set_tool_server,
)
from ..utils import get_logger
from .services import (
    CompletionService,
    LoggingService,
    PromptsService,
    ResourcesService,
    RootsService,
    ToolsService,
)
from .subscriptions import SubscriptionManager
from .notifications import DefaultNotificationSink, NotificationSink


@dataclass(slots=True)
class NotificationFlags:
    """Notifications advertised during initialization."""

    prompts_changed: bool = False
    resources_changed: bool = False
    tools_changed: bool = False
    roots_changed: bool = False


class MCPServer(Server[Any, Any]):
    """Spec-aligned server surface for MCP applications."""

    _PAGINATION_LIMIT = 50

    def __init__(
        self,
        name: str,
        *,
        version: str | None = None,
        instructions: str | None = None,
        website_url: str | None = None,
        icons: list[types.Icon] | None = None,
        notification_flags: NotificationFlags | None = None,
        experimental_capabilities: Mapping[str, Mapping[str, Any]] | None = None,
        lifespan: Callable[[Server[Any, Any]], Any] = default_lifespan,
        transport: str | None = None,
        notification_sink: NotificationSink | None = None,
    ) -> None:
        self._notification_flags = notification_flags or NotificationFlags()
        self._experimental_capabilities = {
            key: dict(value) for key, value in (experimental_capabilities or {}).items()
        }
        super().__init__(
            name,
            version=version,
            instructions=instructions,
            website_url=website_url,
            icons=icons,
            lifespan=lifespan,
        )
        self._default_transport = transport.lower() if transport else "streamable-http"
        self._logger = get_logger(f"openmcp.server.{name}")
        self._notification_sink = notification_sink or DefaultNotificationSink()

        self._subscription_manager = SubscriptionManager()
        self.resources = ResourcesService(
            subscription_manager=self._subscription_manager,
            logger=self._logger,
            pagination_limit=self._PAGINATION_LIMIT,
            notification_sink=self._notification_sink,
        )
        self.roots = RootsService(
            logger=self._logger,
            pagination_limit=self._PAGINATION_LIMIT,
            notification_sink=self._notification_sink,
        )
        self.tools = ToolsService(
            server_ref=self,
            attach_callable=self._attach_tool,
            detach_callable=self._detach_tool,
            logger=self._logger,
            pagination_limit=self._PAGINATION_LIMIT,
            notification_sink=self._notification_sink,
        )
        self.prompts = PromptsService(
            logger=self._logger,
            pagination_limit=self._PAGINATION_LIMIT,
            notification_sink=self._notification_sink,
        )
        self.completions = CompletionService()
        self.logging_service = LoggingService(
            self._logger,
            notification_sink=self._notification_sink,
        )

        # //////////////////////////////////////////////////////////////////
        # Register default handlers
        # //////////////////////////////////////////////////////////////////

        @self.list_resources()
        async def _list_resources(request: types.ListResourcesRequest) -> types.ListResourcesResult:
            return await self.resources.list_resources(request)

        @self.read_resource()
        async def _read_resource(request: types.ReadResourceRequest) -> types.ReadResourceResult:
            return await self.resources.read(request.params.uri)

        @self.list_resource_templates()
        async def _list_templates(request: types.ListResourceTemplatesRequest) -> types.ListResourceTemplatesResult:
            cursor = request.params.cursor if request.params is not None else None
            return await self.resources.list_templates(cursor)

        async def _list_roots_handler(request: types.ListRootsRequest) -> types.ServerResult:
            result = await self.roots.list_roots(request)
            return types.ServerResult(result)

        self.request_handlers[types.ListRootsRequest] = _list_roots_handler

        @self.list_tools()
        async def _list_tools(request: types.ListToolsRequest) -> types.ListToolsResult:
            return await self.tools.list_tools(request)

        @self.call_tool(validate_input=False)
        async def _call_tool(name: str, arguments: dict[str, Any] | None) -> types.CallToolResult:
            return await self.tools.call_tool(name, arguments or {})

        @self.completion()
        async def _completion_handler(
            ref: types.PromptReference | types.ResourceTemplateReference,
            argument: types.CompletionArgument,
            context: types.CompletionContext | None,
        ) -> types.Completion | None:
            return await self.completions.execute(ref, argument, context)

        @self.subscribe_resource()
        async def _subscribe(uri: Any) -> None:
            await self.resources.subscribe_current(str(uri))

        @self.unsubscribe_resource()
        async def _unsubscribe(uri: Any) -> None:
            await self.resources.unsubscribe_current(str(uri))

        @self.list_prompts()
        async def _list_prompts(request: types.ListPromptsRequest) -> types.ListPromptsResult:
            return await self.prompts.list_prompts(request)

        @self.get_prompt()
        async def _get_prompt(name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
            return await self.prompts.get_prompt(name, arguments)

        @self.set_logging_level()
        async def _set_logging_level(level: types.LoggingLevel) -> None:
            await self.logging_service.set_level(level)

    # //////////////////////////////////////////////////////////////////
    # Public API mirroring earlier behaviour
    # //////////////////////////////////////////////////////////////////

    @property
    def tool_names(self) -> list[str]:
        return self.tools.tool_names

    @property
    def prompt_names(self) -> list[str]:
        return self.prompts.names

    def register_tool(self, target: ToolSpec | Callable[..., Any]) -> ToolSpec:
        return self.tools.register(target)

    def allow_tools(self, names: Iterable[str] | None) -> None:
        self.tools.allow_tools(names)

    def register_resource(self, target: ResourceSpec | Callable[[], str | bytes]) -> ResourceSpec:
        return self.resources.register_resource(target)

    def register_resource_template(
        self,
        target: ResourceTemplateSpec | Callable[..., Any],
    ) -> ResourceTemplateSpec:
        return self.resources.register_template(target)

    def set_roots(self, roots: Iterable[types.Root]) -> None:
        self.roots.set_roots(roots)

    def register_prompt(self, target: PromptSpec | Callable[..., Any]) -> PromptSpec:
        return self.prompts.register(target)

    def register_completion(self, target) -> CompletionSpec:
        return self.completions.register(target)

    async def invoke_tool(self, name: str, **arguments: Any) -> types.CallToolResult:
        return await self.tools.call_tool(name, arguments)

    async def invoke_resource(self, uri: str) -> types.ReadResourceResult:
        return await self.resources.read(uri)

    async def invoke_prompt(
        self,
        name: str,
        *,
        arguments: dict[str, str] | None = None,
    ) -> types.GetPromptResult:
        return await self.prompts.get_prompt(name, arguments)

    async def invoke_completion(
        self,
        ref: types.PromptReference | types.ResourceTemplateReference,
        argument: types.CompletionArgument,
        context: types.CompletionContext | None = None,
    ) -> types.Completion | None:
        return await self.completions.execute(ref, argument, context)

    async def list_resource_templates_paginated(
        self,
        cursor: str | None = None,
    ) -> types.ListResourceTemplatesResult:
        return await self.resources.list_templates(cursor)

    async def notify_resource_updated(self, uri: str) -> None:
        await self.resources.notify_updated(uri)

    async def notify_resources_list_changed(self) -> None:
        if self._notification_flags.resources_changed:
            await self.resources.notify_list_changed()

    async def notify_roots_list_changed(self) -> None:
        if self._notification_flags.roots_changed:
            await self.roots.notify_list_changed()

    async def notify_tools_list_changed(self) -> None:
        if self._notification_flags.tools_changed:
            await self.tools.notify_list_changed()

    async def notify_prompts_list_changed(self) -> None:
        if self._notification_flags.prompts_changed:
            await self.prompts.notify_list_changed()

    async def log_message(
        self,
        level: types.LoggingLevel,
        data: Any,
        *,
        logger: str | None = None,
    ) -> None:
        await self.logging_service.emit(level, data, logger)

    # //////////////////////////////////////////////////////////////////
    # Initialization & capability negotiation
    # //////////////////////////////////////////////////////////////////

    def create_initialization_options(
        self,
        *,
        notification_flags: NotificationFlags | None = None,
        experimental_capabilities: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> InitializationOptions:
        flags = notification_flags or self._notification_flags
        experimental = experimental_capabilities or self._experimental_capabilities

        return super().create_initialization_options(
            notification_options=NotificationOptions(
                prompts_changed=flags.prompts_changed,
                resources_changed=flags.resources_changed,
                tools_changed=flags.tools_changed,
            ),
            experimental_capabilities={key: dict(value) for key, value in experimental.items()},
        )

    def get_capabilities(
        self,
        notification_options: NotificationOptions,
        experimental_capabilities: Mapping[str, Mapping[str, Any]],
    ) -> types.ServerCapabilities:
        caps = super().get_capabilities(notification_options, experimental_capabilities)

        if caps.resources is not None:
            caps.resources.subscribe = True
            if self._notification_flags.resources_changed:
                caps.resources.listChanged = True
        if caps.prompts is not None and self._notification_flags.prompts_changed:
            caps.prompts.listChanged = True
        if caps.tools is not None and self._notification_flags.tools_changed:
            caps.tools.listChanged = True

        return caps

    # //////////////////////////////////////////////////////////////////
    # Collecting context
    # //////////////////////////////////////////////////////////////////

    @contextmanager
    def collecting(self):
        tool_token = set_tool_server(self)
        resource_token = set_resource_server(self)
        completion_token = set_completion_server(self)
        prompt_token = set_prompt_server(self)
        template_token = set_resource_template_server(self)
        try:
            yield self
        finally:
            reset_tool_server(tool_token)
            reset_resource_server(resource_token)
            reset_completion_server(completion_token)
            reset_prompt_server(prompt_token)
            reset_resource_template_server(template_token)
    # //////////////////////////////////////////////////////////////////
    # Transport helpers
    # //////////////////////////////////////////////////////////////////

    async def serve_stdio(
        self,
        *,
        raise_exceptions: bool = False,
        stateless: bool = False,
    ) -> None:
        from mcp.server.stdio import stdio_server

        init_options = self.create_initialization_options()

        async with stdio_server() as (read_stream, write_stream):
            await self.run(
                read_stream,
                write_stream,
                init_options,
                raise_exceptions=raise_exceptions,
                stateless=stateless,
            )

    async def serve(
        self,
        *,
        transport: str | None = None,
        **kwargs: Any,
    ) -> None:
        selected = transport.lower() if transport else self._default_transport
        if selected == "stdio":
            return await self.serve_stdio(**kwargs)
        if selected in {"http", "shttp", "streamable-http", "streamable_http"}:
            return await self.serve_streamable_http(**kwargs)
        raise ValueError(f"Unsupported transport '{selected}'.")

    async def serve_streamable_http(
        self,
        host: str = "127.0.0.1",
        port: int = 3000,
        path: str = "/mcp",
    ) -> None:
        from mcp.server.streamable_http import streamable_http_server

        init_options = self.create_initialization_options()

        async with streamable_http_server(host=host, port=port, path=path) as (read_stream, write_stream):
            await self.run(read_stream, write_stream, init_options)

    # //////////////////////////////////////////////////////////////////
    # Internal helpers
    # //////////////////////////////////////////////////////////////////

    def _attach_tool(self, name: str, fn: Callable[..., Any]) -> None:
        setattr(self, name, fn)

    def _detach_tool(self, name: str) -> None:
        if hasattr(self, name):
            try:
                delattr(self, name)
            except AttributeError:  # pragma: no cover - defensive
                pass
