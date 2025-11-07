# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Tests for JWT validation service."""

import time

import base64
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from openmcp.server.authorization import AuthorizationError
from openmcp.server.services.jwt_validator import Clock, JWTValidator, JWTValidatorConfig, SystemClock


def _b64url_uint(value: int) -> str:
    byte_length = (value.bit_length() + 7) // 8
    data_bytes = value.to_bytes(byte_length, "big")
    return base64.urlsafe_b64encode(data_bytes).decode("utf-8").rstrip("=")


def build_rsa_jwk(public_key, kid: str) -> dict[str, str]:
    numbers = public_key.public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "kid": kid,
        "alg": "RS256",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }


def generate_rsa_keypair(kid: str = "test-key-1"):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "private_key": private_key,
        "public_key": public_key,
        "private_pem": private_pem,
        "public_pem": public_pem,
        "kid": kid,
    }


class MockClock(Clock):
    """Mock clock for testing time-dependent logic."""

    def __init__(self, current_time: float | None = None):
        self._current_time = current_time or time.time()

    def now(self) -> float:
        return self._current_time

    def advance(self, seconds: float) -> None:
        """Advance clock by specified seconds."""
        self._current_time += seconds


@pytest.fixture
def rsa_keypair():
    """Generate RSA keypair for testing."""
    return generate_rsa_keypair()


@pytest.fixture
def mock_jwks_server(httpx_mock, rsa_keypair):
    """Mock JWKS endpoint returning test public key."""
    jwks_response = {"keys": [build_rsa_jwk(rsa_keypair["public_key"], rsa_keypair["kid"]) ]}

    httpx_mock.add_response(
        url="https://as.example.com/.well-known/jwks.json",
        json=jwks_response,
    )

    return jwks_response


def create_test_token(
    rsa_keypair,
    claims: dict | None = None,
    headers: dict | None = None,
) -> str:
    """Create a test JWT token."""
    default_claims = {
        "iss": "https://as.example.com",
        "sub": "user_123",
        "aud": "https://mcp.example.com",
        "exp": time.time() + 900,  # 15 min
        "iat": time.time(),
        "scope": "mcp:tools:call offline_access",
        "client_id": "test_client",
        "jti": "test-jti-123",
    }

    default_headers = {"kid": rsa_keypair["kid"]}

    merged_claims = {**default_claims, **(claims or {})}
    merged_headers = {**default_headers, **(headers or {})}
    merged_headers = {k: v for k, v in merged_headers.items() if v is not None}

    return jwt.encode(
        merged_claims,
        rsa_keypair["private_pem"],
        algorithm="RS256",
        headers=merged_headers,
    )


@pytest.mark.asyncio
async def test_valid_jwt_validation(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test successful JWT validation with all claims valid."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
        required_scopes=["mcp:tools:call"],
    )

    validator = JWTValidator(config)
    token = create_test_token(rsa_keypair)

    context = await validator.validate(token)

    assert context.subject == "user_123"
    assert "mcp:tools:call" in context.scopes
    assert context.claims["client_id"] == "test_client"
    assert context.claims["iss"] == "https://as.example.com"


@pytest.mark.asyncio
async def test_expired_token_rejected(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test that expired tokens are rejected."""
    clock = MockClock()
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
        clock=clock,
    )

    validator = JWTValidator(config)

    # Create token that expires in 10 seconds
    token = create_test_token(
        rsa_keypair,
        claims={
            "exp": clock.now() + 10,
            "iat": clock.now(),
        },
    )

    # Advance clock past expiration (beyond leeway)
    clock.advance(10 + 61)  # Expired + leeway (60s) + 1s

    with pytest.raises(AuthorizationError, match="token expired"):
        await validator.validate(token)


@pytest.mark.asyncio
async def test_leeway_tolerance(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test clock skew tolerance with leeway."""
    clock = MockClock()
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
        leeway=60.0,  # 60 second tolerance
        clock=clock,
    )

    validator = JWTValidator(config)

    # Token expires in 10 seconds
    token = create_test_token(
        rsa_keypair,
        claims={
            "exp": clock.now() + 10,
            "iat": clock.now(),
        },
    )

    # Advance clock 30 seconds past expiration (within 60s leeway)
    clock.advance(40)

    # Should still be accepted due to leeway
    context = await validator.validate(token)
    assert context.subject == "user_123"


@pytest.mark.asyncio
async def test_invalid_issuer_rejected(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test tokens from wrong issuer are rejected."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
    )

    validator = JWTValidator(config)

    token = create_test_token(
        rsa_keypair,
        claims={"iss": "https://evil.example.com"},  # Wrong issuer
    )

    with pytest.raises(AuthorizationError, match="invalid issuer"):
        await validator.validate(token)


@pytest.mark.asyncio
async def test_invalid_audience_rejected(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test tokens for wrong audience are rejected (RFC 8707)."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com/server1",  # Specific server
    )

    validator = JWTValidator(config)

    token = create_test_token(
        rsa_keypair,
        claims={"aud": "https://mcp.example.com/server2"},  # Wrong server
    )

    with pytest.raises(AuthorizationError, match="invalid audience"):
        await validator.validate(token)


@pytest.mark.asyncio
async def test_missing_required_scopes_rejected(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test tokens without required scopes are rejected."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
        required_scopes=["mcp:tools:call", "mcp:admin:write"],
    )

    validator = JWTValidator(config)

    token = create_test_token(
        rsa_keypair,
        claims={"scope": "mcp:tools:call"},  # Missing mcp:admin:write
    )

    with pytest.raises(AuthorizationError, match="insufficient scopes"):
        await validator.validate(token)


@pytest.mark.asyncio
async def test_scope_extraction_from_scp_claim(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test scope extraction from scp claim (alternative format)."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
        required_scopes=["read", "write"],
    )

    validator = JWTValidator(config)

    # Some AS implementations use scp (list) instead of scope (string)
    token = create_test_token(
        rsa_keypair,
        claims={"scope": None, "scp": ["read", "write", "delete"]},  # List format overrides default scope
    )

    context = await validator.validate(token)
    assert set(context.scopes) == {"read", "write", "delete"}


@pytest.mark.asyncio
async def test_jwks_caching_reduces_fetches(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test JWKS cache prevents repeated fetches."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
        jwks_cache_ttl=3600.0,  # 1 hour
    )

    validator = JWTValidator(config)

    # First validation - should fetch JWKS
    token1 = create_test_token(rsa_keypair)
    await validator.validate(token1)

    # Second validation - should use cache
    token2 = create_test_token(rsa_keypair, claims={"jti": "different-jti"})
    await validator.validate(token2)

    # JWKS should only be fetched once (cache hit on second)
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_jwks_cache_expiration(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test JWKS cache expires after TTL."""
    clock = MockClock()
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
        jwks_cache_ttl=300.0,  # 5 minutes
        clock=clock,
    )

    validator = JWTValidator(config)

    # First validation
    token1 = create_test_token(rsa_keypair, claims={"iat": clock.now(), "exp": clock.now() + 900})
    await validator.validate(token1)

    # Advance clock past cache TTL
    clock.advance(301)

    # Add second JWKS response (cache expired, will refetch)
    httpx_mock.add_response(
        url="https://as.example.com/.well-known/jwks.json",
        json=mock_jwks_server,
    )

    # Second validation should refetch JWKS
    token2 = create_test_token(rsa_keypair, claims={"jti": "new-jti", "iat": clock.now(), "exp": clock.now() + 900})
    await validator.validate(token2)

    # Should have fetched JWKS twice
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.asyncio
async def test_new_kid_triggers_refresh(httpx_mock, rsa_keypair, mock_jwks_server):
    """Unknown kids should force a JWKS refresh even before TTL expiry."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
        jwks_cache_ttl=3600.0,
    )

    validator = JWTValidator(config)

    # First token uses initial kid (fetch JWKS once)
    original_token = create_test_token(rsa_keypair)
    await validator.validate(original_token)

    # Prepare a brand new key set with a different kid but reuse same validator.
    alt_keypair = generate_rsa_keypair("rotated-key")

    httpx_mock.add_response(
        url="https://as.example.com/.well-known/jwks.json",
        json={"keys": [build_rsa_jwk(alt_keypair["public_key"], alt_keypair["kid"])]},
    )

    rotated_token = create_test_token(alt_keypair, claims={"jti": "rotated"})

    context = await validator.validate(rotated_token)
    assert context.subject == "user_123"

    # Two requests total: original + refresh for new kid.
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.asyncio
async def test_missing_kid_rejected(httpx_mock, rsa_keypair):
    """Test tokens without kid header are rejected."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
    )

    validator = JWTValidator(config)

    token = create_test_token(
        rsa_keypair,
        headers={"kid": None},  # Remove kid
    )

    with pytest.raises(AuthorizationError, match="missing kid"):
        await validator.validate(token)


@pytest.mark.asyncio
async def test_invalid_signature_rejected(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test tokens with invalid signatures are rejected."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
    )

    validator = JWTValidator(config)

    # Create token with valid structure
    token = create_test_token(rsa_keypair)

    # Tamper with signature by replacing it with garbage
    parts = token.split(".")
    parts[2] = "aW52YWxpZHNpZw"  # base64 for "invalidsig"
    tampered_token = ".".join(parts)

    with pytest.raises(AuthorizationError, match="invalid JWT signature"):
        await validator.validate(tampered_token)


@pytest.mark.asyncio
async def test_multiple_issuers_supported(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test validation accepts tokens from any configured issuer."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer=["https://as.example.com", "https://as-backup.example.com"],  # Multiple issuers
        audience="https://mcp.example.com",
    )

    validator = JWTValidator(config)

    # Token from first issuer
    token1 = create_test_token(rsa_keypair, claims={"iss": "https://as.example.com"})
    context1 = await validator.validate(token1)
    assert context1.subject == "user_123"

    # Token from second issuer
    token2 = create_test_token(rsa_keypair, claims={"iss": "https://as-backup.example.com"})
    context2 = await validator.validate(token2)
    assert context2.subject == "user_123"


@pytest.mark.asyncio
async def test_audience_list_in_token(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test validation handles aud claim as list (some AS implementations)."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
    )

    validator = JWTValidator(config)

    # Token with aud as list (valid if our audience is in the list)
    token = create_test_token(
        rsa_keypair,
        claims={"aud": ["https://mcp.example.com", "https://other.example.com"]},
    )

    context = await validator.validate(token)
    assert context.subject == "user_123"


@pytest.mark.asyncio
async def test_nbf_validation(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test not-before claim validation."""
    clock = MockClock()
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
        clock=clock,
    )

    validator = JWTValidator(config)

    # Token valid starting 100 seconds in the future
    token = create_test_token(
        rsa_keypair,
        claims={
            "nbf": clock.now() + 100,
            "iat": clock.now(),
            "exp": clock.now() + 900,
        },
    )

    # Should be rejected (not yet valid)
    with pytest.raises(AuthorizationError, match="not yet valid"):
        await validator.validate(token)

    # Advance clock past nbf
    clock.advance(101)

    # Should now be accepted
    context = await validator.validate(token)
    assert context.subject == "user_123"


@pytest.mark.asyncio
async def test_future_iat_rejected(httpx_mock, rsa_keypair, mock_jwks_server):
    """Tokens issued absurdly in the future should be rejected."""
    clock = MockClock()
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
        clock=clock,
        leeway=30.0,
    )

    validator = JWTValidator(config)

    token = create_test_token(
        rsa_keypair,
        claims={
            "iat": clock.now() + 120,
            "exp": clock.now() + 900,
        },
    )

    with pytest.raises(AuthorizationError, match="issued in the future"):
        await validator.validate(token)


@pytest.mark.asyncio
async def test_custom_claims_preserved(httpx_mock, rsa_keypair, mock_jwks_server):
    """Test custom claims (like ddls:*) are preserved in context."""
    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
    )

    validator = JWTValidator(config)

    token = create_test_token(
        rsa_keypair,
        claims={
            "ddls:connectors": ["ddls:conn_018f..."],
            "ddls:execution_backend": {"url": "https://backend.example.com"},
        },
    )

    context = await validator.validate(token)

    # Custom claims accessible in context.claims
    assert context.claims["ddls:connectors"] == ["ddls:conn_018f..."]
    assert context.claims["ddls:execution_backend"]["url"] == "https://backend.example.com"


@pytest.mark.asyncio
async def test_jwks_fetch_failure_raises_error(httpx_mock, rsa_keypair):
    """Test graceful handling of JWKS fetch failures."""
    # Mock 500 error from JWKS endpoint
    httpx_mock.add_response(
        url="https://as.example.com/.well-known/jwks.json",
        status_code=500,
    )

    config = JWTValidatorConfig(
        jwks_uri="https://as.example.com/.well-known/jwks.json",
        issuer="https://as.example.com",
        audience="https://mcp.example.com",
    )

    validator = JWTValidator(config)
    token = create_test_token(rsa_keypair)

    with pytest.raises(AuthorizationError, match="failed to fetch JWKS"):
        await validator.validate(token)
