# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Elicitation capability adapter.

Spec receipts:
- docs/mcp/capabilities/elicitation/index.md
- docs/mcp/spec/schema-reference/elicitation-create.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import anyio
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.exceptions import McpError

from ... import types
from ...utils import get_logger


DEFAULT_TIMEOUT = 60.0


@dataclass
class _SessionState:
    failures: int = 0


class ElicitationService:
    """Proxy for ``elicitation/create`` requests."""

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout
        self._states: dict[Any, _SessionState] = {}
        self._logger = get_logger("openmcp.elicitation")

    async def create(self, params: types.ElicitRequestParams) -> types.ElicitResult:
        session = self._current_session()

        if not session.check_client_capability(types.ClientCapabilities(elicitation=types.ElicitationCapability())):
            raise McpError(
                types.ErrorData(
                    code=types.METHOD_NOT_FOUND, message="Client does not advertise the elicitation capability"
                )
            )

        self._validate_schema(params.requestedSchema)

        state = self._states.setdefault(session, _SessionState())
        try:
            with anyio.fail_after(self._timeout):
                request = types.ServerRequest(types.ElicitRequest(params=params))
                result = await session.send_request(request, types.ElicitResult)
        except TimeoutError:
            state.failures += 1
            raise McpError(
                types.ErrorData(code=types.INTERNAL_ERROR, message="elicitation request timed out")
            ) from None
        except McpError as exc:
            state.failures += 1
            raise exc
        else:
            state.failures = 0
            return result

    def _current_session(self):
        try:
            ctx = request_ctx.get()
        except LookupError as exc:
            raise RuntimeError("Elicitation requests require an active MCP session") from exc
        return ctx.session

    def _validate_schema(self, requested: dict[str, Any]) -> None:
        if requested.get("type") != "object":
            raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message="requestedSchema.type must be 'object'"))

        properties = requested.get("properties")
        if not isinstance(properties, dict) or not properties:
            raise McpError(
                types.ErrorData(
                    code=types.INVALID_PARAMS, message="requestedSchema.properties must be a non-empty object"
                )
            )

        allowed = {"string", "number", "integer", "boolean"}
        for name, schema in properties.items():
            if not isinstance(schema, dict):
                raise McpError(
                    types.ErrorData(
                        code=types.INVALID_PARAMS, message=f"Schema for property '{name}' must be an object"
                    )
                )
            schema_type = schema.get("type")
            if schema_type not in allowed:
                raise McpError(
                    types.ErrorData(
                        code=types.INVALID_PARAMS,
                        message=f"Unsupported schema type '{schema_type}' for property '{name}'",
                    )
                )


__all__ = ["ElicitationService"]
