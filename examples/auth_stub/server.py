"""Authorization scaffold demo.

Run:

    uv run python examples/auth_stub/server.py

Then call with the demo token:

    curl -H "Authorization: Bearer demo-token" http://127.0.0.1:3000/mcp
"""

from __future__ import annotations

import asyncio

from openmcp import AuthorizationConfig, MCPServer, tool
from openmcp.server.authorization import AuthorizationContext, AuthorizationError


server = MCPServer(
    "auth-demo",
    authorization=AuthorizationConfig(
        enabled=True,
        required_scopes=["mcp:read"],
        authorization_servers=["https://as.dedaluslabs.ai"],
    ),
)


class DemoProvider:
    async def validate(self, token: str) -> AuthorizationContext:
        if token != "demo-token":
            raise AuthorizationError("invalid token")
        return AuthorizationContext(subject="demo", scopes=["mcp:read"], claims={})


server.set_authorization_provider(DemoProvider())


with server.binding():

    @tool(description="Echoes a value")
    async def echo(value: str) -> str:
        return value


async def main() -> None:
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
