# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Resource capability service (resources, templates, subscriptions).

Spec receipts covered here:

- ``docs/mcp/capabilities/resources`` (capabilities, protocol messages, subscriptions)
- ``docs/mcp/spec/schema-reference/resources-list.md`` / ``resources-read.md``
- ``docs/mcp/spec/schema-reference/resources-templates-list.md``
- ``docs/mcp/spec/schema-reference/resources-subscribe.md``
- ``docs/mcp/capabilities/pagination`` for cursor behavior
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..adapters import normalize_resource_payload
from ..notifications import NotificationSink, ObserverRegistry
from ..pagination import paginate_sequence
from ..subscriptions import SubscriptionManager
from ... import types
from ...context import context_scope
from ...resource import ResourceSpec, extract_resource_spec
from ...resource_template import ResourceTemplateSpec, extract_resource_template_spec


class ResourcesService:
    def __init__(
        self,
        *,
        subscription_manager: SubscriptionManager,
        logger,
        pagination_limit: int,
        notification_sink: NotificationSink,
    ) -> None:
        self._logger = logger
        self._pagination_limit = pagination_limit
        self._subscriptions = subscription_manager
        self._sink = notification_sink
        self._resource_specs: dict[str, ResourceSpec] = {}
        self._resource_defs: dict[str, types.Resource] = {}
        self._resource_template_specs: dict[str, ResourceTemplateSpec] = {}
        self._resource_template_defs: list[types.ResourceTemplate] = []
        self.observers = ObserverRegistry(notification_sink)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_resource(self, target: ResourceSpec | Callable[[], str | bytes]) -> ResourceSpec:
        spec = target if isinstance(target, ResourceSpec) else extract_resource_spec(target)  # type: ignore[arg-type]
        if spec is None:
            raise ValueError("Resource functions must be decorated with @resource")
        self._resource_specs[spec.uri] = spec
        self._refresh_resources()
        return spec

    def register_template(self, target: ResourceTemplateSpec | Callable[..., Any]) -> ResourceTemplateSpec:
        spec = (
            target if isinstance(target, ResourceTemplateSpec) else extract_resource_template_spec(target)  # type: ignore[arg-type]
        )
        if spec is None:
            raise ValueError("Resource templates must be decorated with @resource_template")
        self._resource_template_specs[spec.uri_template] = spec
        self._refresh_templates()
        return spec

    # ------------------------------------------------------------------
    # Listing and reading
    # ------------------------------------------------------------------

    async def list_resources(self, request: types.ListResourcesRequest) -> types.ListResourcesResult:
        cursor = request.params.cursor if request.params is not None else None
        resources = list(self._resource_defs.values())
        page, next_cursor = paginate_sequence(resources, cursor, limit=self._pagination_limit)
        self.observers.remember_current_session()
        return types.ListResourcesResult(resources=page, nextCursor=next_cursor)

    async def list_templates(self, cursor: str | None) -> types.ListResourceTemplatesResult:
        page, next_cursor = paginate_sequence(self._resource_template_defs, cursor, limit=self._pagination_limit)
        return types.ListResourceTemplatesResult(resourceTemplates=page, nextCursor=next_cursor)

    async def read(self, uri: str) -> types.ReadResourceResult:
        spec = self._resource_specs.get(uri)
        if spec is None or uri not in self._resource_defs:
            return types.ReadResourceResult(contents=[])

        try:
            try:
                with context_scope():
                    data = spec.fn()
            except LookupError:
                data = spec.fn()
        except Exception as exc:  # pragma: no cover - defensive
            text = f"Resource error: {exc}"
            fallback = types.TextResourceContents(uri=uri, mimeType="text/plain", text=text)
            return types.ReadResourceResult(contents=[fallback])

        normalized = normalize_resource_payload(uri, spec.mime_type, data)
        return normalized

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    async def subscribe_current(self, uri: str) -> None:
        await self._subscriptions.subscribe_current(uri)

    async def unsubscribe_current(self, uri: str) -> None:
        await self._subscriptions.unsubscribe_current(uri)

    async def notify_updated(self, uri: str) -> None:
        subscribers = await self._subscriptions.subscribers(uri)
        if not subscribers:
            return

        notification = types.ServerNotification(
            types.ResourceUpdatedNotification(params=types.ResourceUpdatedNotificationParams(uri=uri))
        )

        stale: list[Any] = []
        for session in subscribers:
            try:
                await self._sink.send_notification(session, notification)
            except Exception as exc:  # pragma: no cover - defensive
                self._logger.warning("Failed to notify subscriber %s: %s", getattr(session, "name", repr(session)), exc)
                stale.append(session)

        for session in stale:
            await self._subscriptions.prune_session(session)

    # ------------------------------------------------------------------
    # Observers / notifications
    # ------------------------------------------------------------------

    async def notify_list_changed(self) -> None:
        notification = types.ServerNotification(types.ResourceListChangedNotification(params=None))
        await self.observers.broadcast(notification, self._logger)

    # ------------------------------------------------------------------
    # Accessors for tests
    # ------------------------------------------------------------------

    @property
    def resource_defs(self) -> dict[str, types.Resource]:
        return self._resource_defs

    @property
    def template_defs(self) -> list[types.ResourceTemplate]:
        return self._resource_template_defs

    @property
    def subscriptions(self) -> SubscriptionManager:
        return self._subscriptions

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_resources(self) -> None:
        self._resource_defs.clear()
        for spec in self._resource_specs.values():
            self._resource_defs[spec.uri] = types.Resource(
                uri=spec.uri, name=spec.name or spec.uri, description=spec.description, mimeType=spec.mime_type
            )

    def _refresh_templates(self) -> None:
        specs = sorted(self._resource_template_specs.values(), key=lambda s: (s.name, s.uri_template))
        self._resource_template_defs = [spec.to_resource_template() for spec in specs]
