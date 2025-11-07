# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""JWT validation service for OAuth 2.1 resource servers.

Implements RFC 9068 JWT Profile for OAuth 2.0 Access Tokens with:
- JWKS fetching and caching (RFC 7517)
- Signature verification (RS256/ES256)
- Standard claims validation (exp, iss, aud, nbf)
- Scope validation
- Clock skew tolerance
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

try:
    import httpx
    import jwt
    from jwt.exceptions import InvalidSignatureError, InvalidTokenError
except ImportError:
    httpx = None  # type: ignore
    jwt = None  # type: ignore
    InvalidTokenError = Exception  # type: ignore
    InvalidSignatureError = Exception  # type: ignore

from ..authorization import AuthorizationContext, AuthorizationError, AuthorizationProvider
from ...utils import get_logger


class Clock(Protocol):
    """Clock abstraction for testing time-dependent logic."""

    def now(self) -> float:
        """Return current Unix timestamp."""


class SystemClock:
    """Production clock using system time."""

    def now(self) -> float:
        return time.time()


class JWTValidationError(AuthorizationError):
    """Base error for JWT validation failures."""


class MissingKidError(JWTValidationError):
    """Raised when the JWT header lacks a key identifier."""


class PublicKeyNotFoundError(JWTValidationError):
    """Raised when no JWKS entry matches the requested kid."""


class JWKSFetchError(JWTValidationError):
    """Raised when the JWKS endpoint cannot be retrieved."""


class ExpiredTokenError(JWTValidationError):
    """Raised when the token expiration has elapsed."""


class NotYetValidTokenError(JWTValidationError):
    """Raised when the token is not valid yet (nbf in the future)."""


class InvalidIssuerError(JWTValidationError):
    """Raised when the token issuer claim does not match configuration."""


class InvalidAudienceError(JWTValidationError):
    """Raised when the token audience claim does not match configuration."""


class FutureIatError(JWTValidationError):
    """Raised when the issued-at claim is unreasonably in the future."""


class MissingScopeError(JWTValidationError):
    """Raised when required scopes are not granted."""


class InvalidJWTSignatureError(JWTValidationError):
    """Raised when signature verification fails."""


@dataclass(slots=True)
class JWTValidatorConfig:
    """Configuration for JWT validation."""

    jwks_uri: str
    """JWKS endpoint URI (e.g., https://as.dedaluslabs.ai/.well-known/jwks.json)"""

    issuer: str | list[str] | None = None
    """Expected issuer(s) for iss claim validation"""

    audience: str | list[str] | None = None
    """Expected audience(s) for aud claim validation (RFC 8707)"""

    required_scopes: list[str] = field(default_factory=list)
    """Scopes required for access"""

    algorithms: list[str] = field(default_factory=lambda: ["RS256", "ES256"])
    """Allowed signing algorithms"""

    leeway: float = 60.0
    """Clock skew tolerance in seconds (default: 60s)"""

    jwks_cache_ttl: float = 3600.0
    """JWKS cache TTL in seconds (default: 1 hour)"""

    clock: Clock = field(default_factory=SystemClock)
    """Clock for time operations (injectable for testing)"""


class JWTValidator(AuthorizationProvider):
    """JWT validation provider implementing RFC 9068.

    Validates JWT access tokens by:
    1. Fetching JWKS from authorization server (cached)
    2. Verifying signature with public key
    3. Validating standard claims (exp, iss, aud, nbf)
    4. Validating scopes

    Example:
        >>> config = JWTValidatorConfig(
        ...     jwks_uri="https://as.dedaluslabs.ai/.well-known/jwks.json",
        ...     issuer="https://as.dedaluslabs.ai",
        ...     audience="https://mcp.example.com",
        ...     required_scopes=["mcp:tools:call"],
        ... )
        >>> validator = JWTValidator(config)
        >>> context = await validator.validate("eyJhbGci...")
    """

    def __init__(self, config: JWTValidatorConfig) -> None:
        if httpx is None or jwt is None:
            raise ImportError(
                "JWT validation requires httpx and pyjwt. "
                "Install with: uv add httpx pyjwt cryptography"
            )

        self.config = config
        self._logger = get_logger("openmcp.jwt_validator")

        # Manual JWKS cache: kid -> (public_key, cached_at)
        self._jwks_cache: dict[str, tuple[Any, float]] = {}
        self._jwks_cache_time: float = 0.0

    async def validate(self, token: str) -> AuthorizationContext:
        """Validate JWT access token per RFC 9068.

        Args:
            token: JWT access token (without "Bearer " prefix)

        Returns:
            AuthorizationContext with subject, scopes, and claims

        Raises:
            AuthorizationError: If validation fails
        """
        kid: str | None = None
        try:
            # Decode header to get kid
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            if not kid:
                raise MissingKidError("missing kid in JWT header")

            # Get public key (cached or fetch)
            public_key = await self._get_public_key(kid)

            # Verify signature but defer claim checks so we can apply our own
            # clock abstraction and richer error messaging.
            claims = jwt.decode(
                token,
                public_key,
                algorithms=self.config.algorithms,
                options={
                    "verify_signature": True,
                    "verify_exp": False,
                    "verify_nbf": False,
                    "verify_iat": False,
                    "verify_aud": False,
                    "verify_iss": False,
                    "require": ["exp", "iat", "sub"],
                },
            )

            # Validate registered claims using configurable clock/leeway.
            self._validate_claims(claims)

            # Extract and validate scopes
            scopes = self._extract_scopes(claims)
            if self.config.required_scopes:
                self._validate_scopes(scopes, self.config.required_scopes)

            return AuthorizationContext(
                subject=claims.get("sub"),
                scopes=scopes,
                claims=claims,
            )

        except InvalidSignatureError as exc:
            self._logger.warning(
                "JWT signature verification failed",
                extra={"event": "jwt.validation.signature_failed", "error": str(exc), "kid": kid},
            )
            raise InvalidJWTSignatureError("invalid JWT signature") from exc
        except InvalidTokenError as exc:
            self._logger.warning(
                "JWT validation failed",
                extra={"event": "jwt.validation.failed", "error": str(exc)},
            )
            raise JWTValidationError(f"JWT validation failed: {exc}") from exc

    async def _get_public_key(self, kid: str) -> Any:
        """Fetch public key from JWKS with caching.

        Implements TTL-based caching similar to Clerk SDK pattern.
        """
        now = self.config.clock.now()

        cached_entry = self._jwks_cache.get(kid)
        if cached_entry is not None:
            cached_key, cached_at = cached_entry
            if now - cached_at < self.config.jwks_cache_ttl:
                return cached_key
            # Expired entry – drop so we refetch below.
            self._jwks_cache.pop(kid, None)

        needs_refresh = (
            cached_entry is None
            or now - self._jwks_cache_time >= self.config.jwks_cache_ttl
        )

        if needs_refresh:
            await self._refresh_jwks_cache()
            self._jwks_cache_time = now

        refreshed = self._jwks_cache.get(kid)
        if refreshed is not None:
            return refreshed[0]

        raise PublicKeyNotFoundError(f"public key not found for kid: {kid}")

    async def _refresh_jwks_cache(self) -> None:
        """Fetch and cache all keys from JWKS endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.config.jwks_uri)
                response.raise_for_status()
                jwks_data = response.json()

            # Cache all keys by kid
            now = self.config.clock.now()
            for key_data in jwks_data.get("keys", []):
                kid_val = key_data.get("kid")
                if not kid_val:
                    continue

                # Convert JWK to public key using PyJWT
                import json as _json
                from jwt.algorithms import ECAlgorithm, RSAAlgorithm

                kty = key_data.get("kty")
                try:
                    if kty == "RSA":
                        public_key = RSAAlgorithm.from_jwk(_json.dumps(key_data))
                    elif kty == "EC":
                        public_key = ECAlgorithm.from_jwk(_json.dumps(key_data))
                    else:
                        continue
                except Exception:
                    continue

                self._jwks_cache[kid_val] = (public_key, now)

            self._logger.debug(
                "JWKS cache refreshed",
                extra={"event": "jwks.cache.refresh", "key_count": len(self._jwks_cache)},
            )

        except Exception as e:
            self._logger.error(
                "JWKS fetch failed",
                extra={"event": "jwks.fetch.failed", "error": str(e), "uri": self.config.jwks_uri},
            )
            raise JWKSFetchError(f"failed to fetch JWKS: {e}") from e

    def _validate_claims(self, claims: dict[str, Any]) -> None:
        """Validate standard JWT claims per RFC 9068 with skew tolerance."""

        now = self.config.clock.now()

        # exp is required (enforced during decode) but still validate semantics
        exp = self._as_timestamp(claims.get("exp"))
        if exp is None:
            raise JWTValidationError("invalid exp claim")
        if now > exp + self.config.leeway:
            raise ExpiredTokenError("token expired")

        iat = self._as_timestamp(claims.get("iat"))
        if iat is None:
            raise JWTValidationError("invalid iat claim")
        if iat - self.config.leeway > now:
            raise FutureIatError("token issued in the future")

        nbf = claims.get("nbf")
        if nbf is not None:
            nbf_ts = self._as_timestamp(nbf)
            if nbf_ts is None:
                raise JWTValidationError("invalid nbf claim")
            if now < nbf_ts - self.config.leeway:
                raise NotYetValidTokenError("token not yet valid")

        if self.config.issuer is not None:
            issuers = self.config.issuer if isinstance(self.config.issuer, list) else [self.config.issuer]
            if claims.get("iss") not in issuers:
                raise InvalidIssuerError(f"invalid issuer: {claims.get('iss')}")

        if self.config.audience is not None:
            audiences = self.config.audience if isinstance(self.config.audience, list) else [self.config.audience]
            aud_claim = claims.get("aud")
            token_auds = aud_claim if isinstance(aud_claim, list) else [aud_claim] if aud_claim else []
            if not any(audience in audiences for audience in token_auds):
                raise InvalidAudienceError(f"invalid audience: {aud_claim}")

    def _as_timestamp(self, value: Any) -> float | None:
        """Convert JWT time claim values to a float timestamp."""

        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        try:  # allow datetime strings if AS returns them
            from datetime import datetime, timezone

            if isinstance(value, str):
                normalized = value.replace("Z", "+00:00")
                dt = datetime.fromisoformat(normalized)
            else:
                dt = value
            if isinstance(dt, datetime):
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.timestamp()
        except Exception:  # pragma: no cover - defensive; datetime parsing rarely used
            return None

        return None

    def _extract_scopes(self, claims: dict[str, Any]) -> list[str]:
        """Extract scopes from JWT claims.

        Handles both:
        - scope: space-delimited string (RFC 9068)
        - scp: list of strings (some AS implementations)
        """
        # Try scope claim first (standard)
        scope_str = claims.get("scope")
        if scope_str and isinstance(scope_str, str):
            return scope_str.split()

        # Try scp claim (alternative)
        scp = claims.get("scp")
        if scp and isinstance(scp, list):
            return scp

        return []

    def _validate_scopes(self, granted: list[str], required: list[str]) -> None:
        """Validate token has required scopes.

        Args:
            granted: Scopes in token
            required: Scopes required for access

        Raises:
            AuthorizationError: If required scopes not present
        """
        granted_set = set(granted)
        required_set = set(required)

        if not required_set.issubset(granted_set):
            missing = required_set - granted_set
            raise MissingScopeError(f"insufficient scopes, missing: {missing}")


__all__ = [
    "Clock",
    "SystemClock",
    "JWTValidatorConfig",
    "JWTValidator",
    "JWTValidationError",
    "MissingKidError",
    "PublicKeyNotFoundError",
    "JWKSFetchError",
    "ExpiredTokenError",
    "NotYetValidTokenError",
    "InvalidIssuerError",
    "InvalidAudienceError",
    "FutureIatError",
    "MissingScopeError",
    "InvalidJWTSignatureError",
]
