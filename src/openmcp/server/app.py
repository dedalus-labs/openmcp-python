"""Composable MCP server built on the reference SDK."""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from functools import wraps
import base64
import inspect
from typing import Any, Literal, TYPE_CHECKING
from collections.abc import Callable, Iterable, Mapping

import anyio
import anyio.abc

from .._sdk_loader import ensure_sdk_importable
from .transports.base import BaseTransport, TransportFactory

ensure_sdk_importable()

import mcp.types as types
from mcp.server.lowlevel.server import (
    NotificationOptions,
    Server,
    lifespan as default_lifespan,
    request_ctx,
)
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.models import InitializationOptions
from mcp.shared.exceptions import McpError
from mcp.shared.session import RequestResponder

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
from .authorization import AuthorizationConfig, AuthorizationManager, AuthorizationProvider
from .services import (
    CompletionService,
    LoggingService,
    PromptsService,
    ResourcesService,
    RootsService,
    SamplingService,
    ElicitationService,
    ToolsService,
    PingService,
)
from .subscriptions import SubscriptionManager
from .notifications import DefaultNotificationSink, NotificationSink
from .transports import StdioTransport, StreamableHTTPTransport
from mcp.server.transport_security import TransportSecuritySettings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcp.server.session import ServerSession

TransportLiteral = Literal["stdio", "streamable-http"]


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
        http_security: TransportSecuritySettings | None = None,
        authorization: AuthorizationConfig | None = None,
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
        self.roots = RootsService(self._call_roots_list)
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
        self.sampling = SamplingService()
        self.elicitation = ElicitationService()
        self.ping = PingService(
            notification_sink=self._notification_sink,
            logger=self._logger,
        )

        self._http_security_settings = (
            http_security if http_security is not None else self._default_http_security_settings()
        )

        self._authorization_manager: AuthorizationManager | None = None
        if authorization and authorization.enabled:
            self._authorization_manager = AuthorizationManager(authorization)

        self._transport_factories: dict[str, TransportFactory] = {}
        self.register_transport("stdio", lambda server: StdioTransport(server))
        stream_http_factory = lambda server: StreamableHTTPTransport(
            server, security_settings=self._http_security_settings
        )
        self.register_transport(
            "streamable-http",
            stream_http_factory,
            aliases=("streamable_http", "shttp", "http"),
        )

        self.notification_handlers[types.InitializedNotification] = self._handle_initialized
        self.notification_handlers[types.RootsListChangedNotification] = self._handle_roots_list_changed

        # //////////////////////////////////////////////////////////////////
        # Register default handlers
        # //////////////////////////////////////////////////////////////////

        @self.list_resources()
        async def _list_resources(request: types.ListResourcesRequest) -> types.ListResourcesResult:
            return await self.resources.list_resources(request)

        @self.read_resource()
        async def _read_resource(uri: types.AnyUrl) -> list[ReadResourceContents]:
            result = await self.resources.read(str(uri))
            converted: list[ReadResourceContents] = []
            for item in result.contents:
                if isinstance(item, types.TextResourceContents):
                    converted.append(
                        ReadResourceContents(content=item.text, mime_type=item.mimeType)
                    )
                elif isinstance(item, types.BlobResourceContents):
                    data = base64.b64decode(item.blob)
                    converted.append(
                        ReadResourceContents(content=data, mime_type=item.mimeType)
                    )
                else:  # pragma: no cover - defensive
                    raise TypeError(f"Unsupported resource content type: {type(item)!r}")
            return converted

        @self.list_resource_templates()
        async def _list_templates(request: types.ListResourceTemplatesRequest) -> types.ListResourceTemplatesResult:
            cursor = request.params.cursor if request.params is not None else None
            return await self.resources.list_templates(cursor)

        @self.list_tools()
        async def _list_tools(request: types.ListToolsRequest) -> types.ListToolsResult:
            return await self.tools.list_tools(request)

        @self.call_tool(validate_input=False)
        async def _call_tool(
            name: str,
            arguments: dict[str, Any] | None,
        ) -> tuple[list[types.ContentBlock], dict[str, Any] | None]:
            result = await self.tools.call_tool(name, arguments or {})
            if result.isError:
                message = "Tool execution failed"
                if result.content:
                    first = result.content[0]
                    if isinstance(first, types.TextContent) and first.text:
                        message = first.text
                raise McpError(types.ErrorData(code=types.INTERNAL_ERROR, message=message))

            structured = result.structuredContent if result.structuredContent is not None else None
            return list(result.content), structured

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

    def active_sessions(self) -> tuple["ServerSession", ...]:
        """Return a snapshot of currently tracked client sessions."""

        return self.ping.active()

    async def ping_client(
        self,
        session: "ServerSession",
        *,
        timeout: float | None = None,
    ) -> bool:
        """Send ``ping`` to a specific client session (docs/mcp/spec/schema-reference/ping.md)."""

        return await self.ping.ping(session, timeout=timeout)

    async def ping_clients(
        self,
        sessions: Iterable["ServerSession"] | None = None,
        *,
        timeout: float | None = None,
        max_concurrency: int | None = None,
    ) -> dict["ServerSession", bool]:
        """Ping a set of client sessions, defaulting to all active connections."""

        return await self.ping.ping_many(
            sessions,
            timeout=timeout,
            max_concurrency=max_concurrency,
        )

    async def ping_current_session(self, *, timeout: float | None = None) -> bool:
        """Convenience wrapper that pings the client associated with the active request."""

        try:
            context = request_ctx.get()
        except LookupError as exc:  # pragma: no cover - defensive
            raise RuntimeError("ping_current_session requires an active request context") from exc

        return await self.ping_client(context.session, timeout=timeout)

    async def _handle_message(self, message, session, lifespan_context, raise_exceptions: bool = False):
        if isinstance(message, (RequestResponder, types.ClientNotification)):
            self.ping.register(session)
            self.ping.touch(session)
        await super()._handle_message(message, session, lifespan_context, raise_exceptions)

    def start_ping_heartbeat(
        self,
        task_group: anyio.abc.TaskGroup,
        *,
        interval: float = 5.0,
        jitter: float = 0.2,
        timeout: float = 2.0,
        phi_threshold: float | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        """Launch a background heartbeat probe loop for all sessions."""

        self.ping.start_heartbeat(
            task_group,
            interval=interval,
            jitter=jitter,
            timeout=timeout,
            phi_threshold=phi_threshold,
            max_concurrency=max_concurrency,
        )

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

    async def request_sampling(
        self, params: types.CreateMessageRequestParams
    ) -> types.CreateMessageResult:
        """Proxy ``sampling/createMessage`` (docs/mcp/spec/schema-reference/sampling-createmessage.md)."""

        return await self.sampling.create_message(params)

    async def request_elicitation(
        self, params: types.ElicitRequestParams
    ) -> types.ElicitResult:
        """Proxy ``elicitation/create`` (docs/mcp/spec/schema-reference/elicitation-create.md)."""

        return await self.elicitation.create(params)

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

    def require_within_roots(self, *, argument: str = "path") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator enforcing that a handler argument resolves within allowed roots."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if not inspect.iscoroutinefunction(func):
                raise TypeError("require_within_roots expects an async function")

            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                if argument not in kwargs:
                    raise McpError(
                        types.ErrorData(
                            code=types.INVALID_PARAMS,
                            message=f"Argument '{argument}' is required for roots validation",
                        )
                    )

                try:
                    context = request_ctx.get()
                except LookupError as exc:
                    raise RuntimeError("Roots guard requires an active request context") from exc

                guard = self.roots.guard(context.session)
                candidate = kwargs[argument]
                if not guard.within(candidate):
                    raise McpError(
                        types.ErrorData(
                            code=types.INVALID_PARAMS,
                            message=f"Path '{candidate}' is outside the client's declared roots",
                        )
                    )

                return await func(*args, **kwargs)

            return wrapper

        return decorator

    async def _call_roots_list(
        self,
        session,
        params: Mapping[str, Any] | None,
    ) -> Mapping[str, Any]:
        request = types.ListRootsRequest(params=params)
        result = await session.send_request(types.ServerRequest(request), types.ListRootsResult)
        payload: dict[str, Any] = {
            "roots": [root.model_dump(by_alias=True) for root in result.roots],
        }
        next_cursor = getattr(result, "nextCursor", None)
        if next_cursor is not None:
            payload["nextCursor"] = next_cursor
        return payload

    async def _handle_initialized(self, _notification: types.InitializedNotification) -> None:
        try:
            context = request_ctx.get()
        except LookupError:  # pragma: no cover - defensive
            return
        self.ping.register(context.session)
        await self.roots.on_session_open(context.session)

    async def _handle_roots_list_changed(self, _notification: types.RootsListChangedNotification) -> None:
        try:
            context = request_ctx.get()
        except LookupError:  # pragma: no cover - defensive
            return
        await self.roots.on_list_changed(context.session)

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

    @property
    def authorization_manager(self) -> AuthorizationManager | None:
        return self._authorization_manager

    def set_authorization_provider(self, provider: AuthorizationProvider) -> None:
        if self._authorization_manager is None:
            raise RuntimeError("Authorization is not enabled for this server")
        self._authorization_manager.set_provider(provider)

    # //////////////////////////////////////////////////////////////////
    # Binding context
    # //////////////////////////////////////////////////////////////////

    @contextmanager
    def binding(self):
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
    # Transport registry
    # //////////////////////////////////////////////////////////////////

    @staticmethod
    def _default_http_security_settings() -> TransportSecuritySettings:
        """Return conservative defaults for streamable HTTP security."""

        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*"],
            allowed_origins=["https://as.dedaluslabs.ai"],
        )

    def register_transport(
        self,
        name: str,
        factory: TransportFactory,
        *,
        aliases: Iterable[str] | None = None,
    ) -> None:
        canonical = name.lower()
        self._transport_factories[canonical] = factory
        for alias in aliases or ():
            self._transport_factories[alias.lower()] = factory

    def _transport_for_name(self, name: str) -> BaseTransport:
        factory = self._transport_factories.get(name)
        if factory is None:
            raise ValueError(f"Unsupported transport '{name}'.")
        transport = factory(self)
        if not isinstance(transport, BaseTransport):  # pragma: no cover - defensive
            raise TypeError("Transport factory must return a BaseTransport instance")
        return transport

    def configure_streamable_http_security(
        self, settings: TransportSecuritySettings | None
    ) -> None:
        """Update the security guard used by the Streamable HTTP transport."""

        self._http_security_settings = (
            settings if settings is not None else self._default_http_security_settings()
        )

    # //////////////////////////////////////////////////////////////////
    # Transport helpers
    # //////////////////////////////////////////////////////////////////

    async def serve_stdio(
        self,
        *,
        raise_exceptions: bool = False,
        stateless: bool = False,
    ) -> None:
        transport = self._transport_for_name("stdio")
        await transport.run(raise_exceptions=raise_exceptions, stateless=stateless)

    async def serve(
        self,
        *,
        transport: str | None = None,
        **kwargs: Any,
    ) -> None:
        selected = (transport or self._default_transport).lower()
        if selected in {"stdio", "streamable-http", "streamable_http", "http", "shttp"}:
            if selected == "stdio":
                await self.serve_stdio(**kwargs)
                return
            await self.serve_streamable_http(**kwargs)
            return
        transport_instance = self._transport_for_name(selected)
        await transport_instance.run(**kwargs)

    async def serve_streamable_http(
        self,
        host: str = "127.0.0.1",
        port: int = 3000,
        path: str = "/mcp",
        log_level: str = "info",
        **uvicorn_options: Any,
    ) -> None:
        transport = self._transport_for_name("streamable-http")
        await transport.run(
            host=host,
            port=port,
            path=path,
            log_level=log_level,
            **uvicorn_options,
        )

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
