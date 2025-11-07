# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Tests for MCP metadata endpoint (.well-known/mcp-server.json)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import anyio
import pytest
from httpx import AsyncClient

from openmcp import MCPServer, tool
from openmcp.server import NotificationFlags
from openmcp.server.authorization import AuthorizationConfig


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
async def basic_server() -> MCPServer:
    """Create a basic server without connection configuration."""
    return MCPServer("test-server", version="1.0.0")


@pytest.fixture
async def configured_server() -> MCPServer:
    """Create a server with full connection configuration."""
    server = MCPServer(
        "supabase-server",
        version="1.0.0",
        resource_uri="https://mcp.example.com/supabase",
        connector_kind="supabase",
        connector_params={"supabase_url": str, "anon_key": str},
        auth_methods=["service_role_key", "user_jwt"],
    )
    return server


@pytest.fixture
async def server_with_tools() -> MCPServer:
    """Create a server with registered tools."""
    server = MCPServer(
        "tools-server",
        resource_uri="https://mcp.example.com/tools",
        connector_kind="api",
    )

    with server.binding():

        @tool()
        async def get_weather(location: str) -> str:
            """Get weather for a location."""
            return f"Sunny in {location}"

        @tool()
        async def get_time() -> str:
            """Get current time."""
            return "12:00 PM"

    return server


@pytest.fixture
async def server_with_auth() -> MCPServer:
    """Create a server with authorization enabled."""
    auth_config = AuthorizationConfig(
        enabled=True,
        authorization_servers=["https://as.example.com"],
        required_scopes=["read:resources", "write:resources"],
    )
    server = MCPServer(
        "auth-server",
        resource_uri="https://mcp.example.com/auth",
        connector_kind="authenticated",
        authorization=auth_config,
    )
    return server


@pytest.mark.anyio
async def test_basic_metadata_structure(basic_server: MCPServer) -> None:
    """Test metadata structure for a basic server without connection config."""
    metadata = basic_server.get_mcp_metadata()

    assert "mcp_server_version" in metadata
    assert metadata["mcp_server_version"] == "2025-06-18"
    assert "resource_uri" not in metadata
    assert "connector_schema" not in metadata
    assert "tools" not in metadata
    assert "required_scopes" not in metadata


@pytest.mark.anyio
async def test_full_connector_schema(configured_server: MCPServer) -> None:
    """Test metadata with complete connection configuration."""
    metadata = configured_server.get_mcp_metadata()

    assert metadata["mcp_server_version"] == "2025-06-18"
    assert metadata["resource_uri"] == "https://mcp.example.com/supabase"

    connector_schema = metadata["connector_schema"]
    assert connector_schema["version"] == "1"
    assert connector_schema["resource_kind"] == "supabase"
    assert connector_schema["params"] == {"supabase_url": "str", "anon_key": "str"}
    assert connector_schema["auth_supported"] == ["service_role_key", "user_jwt"]


@pytest.mark.anyio
async def test_metadata_with_tools(server_with_tools: MCPServer) -> None:
    """Test metadata includes registered tools."""
    metadata = server_with_tools.get_mcp_metadata()

    assert "tools" in metadata
    tools = metadata["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 2
    assert "get_weather" in tools
    assert "get_time" in tools


@pytest.mark.anyio
async def test_metadata_with_authorization(server_with_auth: MCPServer) -> None:
    """Test metadata includes required scopes when authorization is enabled."""
    metadata = server_with_auth.get_mcp_metadata()

    assert "required_scopes" in metadata
    assert metadata["required_scopes"] == ["read:resources", "write:resources"]


@pytest.mark.anyio
async def test_partial_connector_schema() -> None:
    """Test connection schema with only some fields populated."""
    server = MCPServer(
        "partial-server",
        connector_kind="custom",
    )

    metadata = server.get_mcp_metadata()
    connector_schema = metadata["connector_schema"]

    assert connector_schema["version"] == "1"
    assert connector_schema["resource_kind"] == "custom"
    assert "params" not in connector_schema
    assert "auth_supported" not in connector_schema


@pytest.mark.anyio
async def test_connector_params_only() -> None:
    """Test connection schema with only params defined."""
    server = MCPServer(
        "params-server",
        connector_params={"api_key": str, "endpoint": str},
    )

    metadata = server.get_mcp_metadata()
    connector_schema = metadata["connector_schema"]

    assert connector_schema["version"] == "1"
    assert connector_schema["params"] == {"api_key": "str", "endpoint": "str"}
    assert "resource_kind" not in connector_schema
    assert "auth_supported" not in connector_schema


@pytest.mark.anyio
async def test_auth_methods_only() -> None:
    """Test connection schema with only auth methods defined."""
    server = MCPServer(
        "auth-methods-server",
        auth_methods=["oauth2", "api_key"],
    )

    metadata = server.get_mcp_metadata()
    connector_schema = metadata["connector_schema"]

    assert connector_schema["version"] == "1"
    assert connector_schema["auth_supported"] == ["oauth2", "api_key"]
    assert "resource_kind" not in connector_schema
    assert "params" not in connector_schema


@pytest.mark.anyio
async def test_metadata_properties() -> None:
    """Test individual metadata properties on MCPServer."""
    server = MCPServer(
        "prop-test-server",
        resource_uri="https://example.com/api",
        connector_kind="rest",
        connector_params={"base_url": str},
        auth_methods=["bearer"],
    )

    assert server.resource_uri == "https://example.com/api"
    assert server.connector_kind == "rest"
    assert server.connector_params == {"base_url": str}
    assert server.auth_methods == ["bearer"]


@pytest.mark.anyio
async def test_metadata_properties_none() -> None:
    """Test metadata properties are None when not configured."""
    server = MCPServer("empty-server")

    assert server.resource_uri is None
    assert server.connector_kind is None
    assert server.connector_params is None
    assert server.auth_methods is None


@pytest.mark.anyio
async def test_http_endpoint_route_exists(configured_server: MCPServer) -> None:
    """Test HTTP transport includes metadata endpoint route."""
    from openmcp.server.transports import StreamableHTTPTransport

    transport = StreamableHTTPTransport(configured_server)
    handler = transport._build_handler(transport._build_session_manager())
    routes = list(transport._build_routes(path="/mcp", handler=handler))

    # Should have 2 routes: main MCP endpoint + metadata endpoint
    assert len(routes) == 2

    # Find the metadata route
    metadata_route = next((r for r in routes if r.path == "/.well-known/mcp-server.json"), None)
    assert metadata_route is not None
    assert "GET" in metadata_route.methods

    # Test the endpoint can be called directly
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/.well-known/mcp-server.json",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)

    response = await metadata_route.endpoint(request)
    assert response.status_code == 200
    assert "cache-control" in response.headers

    # JSONResponse stores the body directly, we can access it via .body attribute
    # The response returns JSON which we can parse
    data = json.loads(response.body)

    assert data["mcp_server_version"] == "2025-06-18"
    assert data["resource_uri"] == "https://mcp.example.com/supabase"
    assert data["connector_schema"]["resource_kind"] == "supabase"


@pytest.mark.anyio
async def test_metadata_json_serialization(configured_server: MCPServer) -> None:
    """Test metadata can be serialized to JSON."""
    metadata = configured_server.get_mcp_metadata()

    # Should not raise
    json_str = json.dumps(metadata)
    assert json_str

    # Should round-trip correctly
    parsed = json.loads(json_str)
    assert parsed == metadata


@pytest.mark.anyio
async def test_empty_tools_list() -> None:
    """Test metadata excludes tools field when no tools are registered."""
    server = MCPServer("no-tools-server")
    metadata = server.get_mcp_metadata()

    assert "tools" not in metadata


@pytest.mark.anyio
async def test_tools_list_updates_dynamically() -> None:
    """Test metadata reflects dynamically registered tools."""
    server = MCPServer("dynamic-server", allow_dynamic_tools=True)

    metadata_before = server.get_mcp_metadata()
    assert "tools" not in metadata_before

    with server.binding():

        @tool()
        async def dynamic_tool() -> str:
            return "dynamic"

    metadata_after = server.get_mcp_metadata()
    assert "tools" in metadata_after
    assert "dynamic_tool" in metadata_after["tools"]


@pytest.mark.anyio
async def test_connector_params_type_names() -> None:
    """Test connection params correctly serialize type names."""
    server = MCPServer(
        "types-server",
        connector_params={
            "string_param": str,
            "int_param": int,
            "bool_param": bool,
            "float_param": float,
        },
    )

    metadata = server.get_mcp_metadata()
    params = metadata["connector_schema"]["params"]

    assert params["string_param"] == "str"
    assert params["int_param"] == "int"
    assert params["bool_param"] == "bool"
    assert params["float_param"] == "float"


@pytest.mark.anyio
async def test_authorization_without_scopes() -> None:
    """Test metadata when authorization is enabled but no scopes defined."""
    auth_config = AuthorizationConfig(enabled=True, required_scopes=[])
    server = MCPServer("no-scopes-server", authorization=auth_config)

    metadata = server.get_mcp_metadata()
    assert "required_scopes" not in metadata


@pytest.mark.anyio
async def test_authorization_disabled() -> None:
    """Test metadata when authorization is disabled."""
    auth_config = AuthorizationConfig(enabled=False, required_scopes=["read"])
    server = MCPServer("disabled-auth-server", authorization=auth_config)

    metadata = server.get_mcp_metadata()
    assert "required_scopes" not in metadata


@pytest.mark.anyio
async def test_metadata_caching_headers() -> None:
    """Test metadata endpoint includes appropriate caching headers."""
    pytest.importorskip("httpx")

    server = MCPServer("cache-test-server")
    from openmcp.server.transports import StreamableHTTPTransport

    transport = StreamableHTTPTransport(server)
    handler = transport._build_handler(transport._build_session_manager())
    routes = list(transport._build_routes(path="/mcp", handler=handler))

    # Find the metadata route
    metadata_route = next(r for r in routes if r.path == "/.well-known/mcp-server.json")
    assert metadata_route is not None

    # Create a mock request
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/.well-known/mcp-server.json",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)

    response = await metadata_route.endpoint(request)
    assert response.status_code == 200
    assert "cache-control" in response.headers
    assert "max-age=3600" in response.headers["cache-control"]


@pytest.mark.anyio
async def test_metadata_comprehensive_example() -> None:
    """Test a comprehensive example with all features enabled."""
    auth_config = AuthorizationConfig(
        enabled=True,
        authorization_servers=["https://auth.example.com"],
        required_scopes=["mcp:read", "mcp:write", "mcp:execute"],
    )

    server = MCPServer(
        "comprehensive-server",
        version="2.0.0",
        resource_uri="https://mcp.example.com/comprehensive",
        connector_kind="hybrid",
        connector_params={
            "api_endpoint": str,
            "websocket_url": str,
            "timeout": int,
            "retry_enabled": bool,
        },
        auth_methods=["oauth2", "api_key", "jwt"],
        authorization=auth_config,
    )

    with server.binding():

        @tool()
        async def comprehensive_tool_1() -> str:
            return "result1"

        @tool()
        async def comprehensive_tool_2() -> str:
            return "result2"

        @tool()
        async def comprehensive_tool_3() -> str:
            return "result3"

    metadata = server.get_mcp_metadata()

    # Verify all sections present
    assert metadata["mcp_server_version"] == "2025-06-18"
    assert metadata["resource_uri"] == "https://mcp.example.com/comprehensive"

    assert metadata["connector_schema"]["version"] == "1"
    assert metadata["connector_schema"]["resource_kind"] == "hybrid"
    assert metadata["connector_schema"]["params"] == {
        "api_endpoint": "str",
        "websocket_url": "str",
        "timeout": "int",
        "retry_enabled": "bool",
    }
    assert metadata["connector_schema"]["auth_supported"] == ["oauth2", "api_key", "jwt"]

    assert len(metadata["tools"]) == 3
    assert "comprehensive_tool_1" in metadata["tools"]
    assert "comprehensive_tool_2" in metadata["tools"]
    assert "comprehensive_tool_3" in metadata["tools"]

    assert metadata["required_scopes"] == ["mcp:read", "mcp:write", "mcp:execute"]
