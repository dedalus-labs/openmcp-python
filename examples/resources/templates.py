# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: URI template resource example.

Demonstrates resource templates with parameterized URIs following RFC 6570.
Templates advertise patterns; actual resources are registered separately.

Spec:
- https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- resources/templates/list returns available patterns
- resources/read resolves specific URIs

Usage:
    uv run python examples/resources/templates.py
"""

from __future__ import annotations

import asyncio
import json

from openmcp import MCPServer, resource, resource_template


server = MCPServer("template-resources")

# Mock database for demonstration
USER_DB = {
    "alice": {"name": "Alice Smith", "role": "engineer", "active": True},
    "bob": {"name": "Bob Jones", "role": "designer", "active": True},
}

with server.binding():

    @resource_template(
        name="user-profile",
        uri_template="user://{username}/profile",
        title="User Profile",
        description="Retrieve user profile by username",
        mime_type="application/json",
    )
    def user_template_metadata():
        """Resource template metadata.

        This decorator advertises the template pattern but doesn't handle reads.
        Register corresponding @resource handlers for actual URIs.
        """
        pass

    # Register specific resource instances matching the template
    @resource(
        uri="user://alice/profile",
        name="Alice Profile",
        mime_type="application/json",
    )
    def alice_profile() -> str:
        return json.dumps(USER_DB["alice"], indent=2)

    @resource(
        uri="user://bob/profile",
        name="Bob Profile",
        mime_type="application/json",
    )
    def bob_profile() -> str:
        return json.dumps(USER_DB["bob"], indent=2)

    @resource_template(
        name="api-endpoint",
        uri_template="api://v1/{service}/{method}",
        title="API Endpoint",
        description="Access API documentation by service and method",
    )
    def api_template_metadata():
        """Multi-parameter template example."""
        pass

    @resource(
        uri="api://v1/users/list",
        name="List Users API",
        mime_type="text/plain",
    )
    def users_list_doc() -> str:
        return "GET /api/v1/users - List all users\nReturns: JSON array of user objects"


async def main() -> None:
    await server.serve(transport="streamable-http", port=8080)


if __name__ == "__main__":
    asyncio.run(main())
