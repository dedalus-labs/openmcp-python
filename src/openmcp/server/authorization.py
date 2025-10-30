"""Authorization scaffolding for Streamable HTTP transports.

This module prepares OpenMCP for an OAuth 2.1 protected-resource flow without
requiring the authorization server to be available at development time.

Key pieces:

* :class:`AuthorizationConfig` – opt-in server configuration.
* :class:`AuthorizationProvider` protocol – pluggable token validation.
* :class:`AuthorizationManager` – serves protected-resource metadata and wraps ASGI apps with
  bearer-token enforcement.

Implementations can supply their own provider that validates tokens against a
real authorization server once available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from ..utils import get_logger

try:  # starlette is optional – only required for streamable HTTP deployments
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route
except ImportError:  # pragma: no cover - imported lazily in transports
    BaseHTTPMiddleware = None  # type: ignore
    Request = None  # type: ignore
    JSONResponse = None  # type: ignore
    Response = None  # type: ignore
    Route = None  # type: ignore


@dataclass(slots=True)
class AuthorizationConfig:
    """Server-side authorization configuration."""

    enabled: bool = False
    metadata_path: str = "/.well-known/oauth-protected-resource"
    authorization_servers: list[str] = field(
        default_factory=lambda: ["https://as.dedaluslabs.ai"]
    )
    required_scopes: list[str] = field(default_factory=list)
    cache_ttl: int = 300
    fail_open: bool = False


@dataclass(slots=True)
class AuthorizationContext:
    """Context returned by providers after successful validation."""

    subject: str | None
    scopes: list[str]
    claims: dict[str, Any]


class AuthorizationError(Exception):
    """Raised when token validation fails."""


class AuthorizationProvider(Protocol):
    async def validate(self, token: str) -> AuthorizationContext:
        """Validate a bearer token and return the associated context."""


class _NoopAuthorizationProvider:
    async def validate(self, token: str) -> AuthorizationContext:
        raise AuthorizationError("authorization provider not configured")


class AuthorizationManager:
    """Coordinates metadata serving and ASGI middleware for authorization."""

    def __init__(
        self,
        config: AuthorizationConfig,
        provider: AuthorizationProvider | None = None,
    ) -> None:
        self.config = config
        self._provider: AuthorizationProvider = provider or _NoopAuthorizationProvider()
        self._logger = get_logger("openmcp.authorization")

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def set_provider(self, provider: AuthorizationProvider) -> None:
        self._provider = provider

    # ------------------------------------------------------------------
    # Starlette integration helpers (lazy imports to avoid hard deps)
    # ------------------------------------------------------------------

    def starlette_route(self) -> Route:
        if Route is None or JSONResponse is None:  # pragma: no cover - optional dependency
            raise RuntimeError("starlette must be installed to use HTTP authorization")

        async def metadata_endpoint(request: Request) -> Response:
            resource = self._canonical_resource(request)
            payload = {
                "resource": resource,
                "authorization_servers": self.config.authorization_servers,
                "scopes_supported": self.config.required_scopes,
            }
            headers = {"Cache-Control": f"public, max-age={self.config.cache_ttl}"}
            return JSONResponse(payload, headers=headers)

        return Route(self.config.metadata_path, metadata_endpoint, methods=["GET"])

    def wrap_asgi(self, app: Callable) -> Callable:
        if BaseHTTPMiddleware is None or Request is None or JSONResponse is None:
            raise RuntimeError("starlette must be installed to use HTTP authorization")

        manager = self

        class _Middleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:  # type: ignore[override]
                if request.url.path == manager.config.metadata_path:
                    return await call_next(request)

                auth_header = request.headers.get("authorization")
                if not auth_header or not auth_header.lower().startswith("bearer "):
                    return manager._challenge_response("missing bearer token")

                token = auth_header[7:].strip()
                try:
                    context = await manager._provider.validate(token)
                    request.scope["openmcp.auth"] = context
                    return await call_next(request)
                except AuthorizationError as exc:
                    manager._logger.warning(
                        "authorization failed",
                        extra={"event": "auth.jwt.reject", "reason": str(exc)},
                    )
                    if manager.config.fail_open:
                        manager._logger.warning(
                            "authorization fail-open engaged; allowing request",
                            extra={"event": "auth.fail_open"},
                        )
                        request.scope["openmcp.auth"] = None
                        return await call_next(request)
                    return manager._challenge_response(str(exc))

        return _Middleware(app)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _challenge_response(self, reason: str | None = None) -> Response:
        if JSONResponse is None:  # pragma: no cover
            raise RuntimeError("starlette must be installed to use HTTP authorization")

        challenge = (
            f'Bearer error="invalid_token", authorization_uri="{self.config.metadata_path}"'
        )
        headers = {"WWW-Authenticate": challenge}
        payload = {"error": "unauthorized", "detail": reason}
        return JSONResponse(payload, status_code=401, headers=headers)

    def _canonical_resource(self, request: "Request") -> str:
        # Construct scheme://host[:port] without trailing slash
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
        if not host:
            host = request.url.netloc
        base = f"{scheme}://{host}"
        return base.rstrip("/")


__all__ = [
    "AuthorizationConfig",
    "AuthorizationContext",
    "AuthorizationError",
    "AuthorizationManager",
    "AuthorizationProvider",
]
