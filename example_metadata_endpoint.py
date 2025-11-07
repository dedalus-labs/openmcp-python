#!/usr/bin/env python3
"""Example demonstrating the .well-known/mcp-server.json metadata endpoint.

Run this example with:
    uv run python example_metadata_endpoint.py

Then in another terminal, fetch the metadata:
    curl http://127.0.0.1:8000/.well-known/mcp-server.json | jq
"""

from openmcp import MCPServer, tool


async def main() -> None:
    server = MCPServer(
        "supabase-server",
        version="1.0.0",
        resource_uri="https://mcp.example.com/supabase",
        connection_kind="supabase",
        connection_params={
            "supabase_url": str,
            "anon_key": str,
        },
        auth_methods=["service_role_key", "user_jwt"],
    )

    with server.binding():

        @tool()
        async def query_table(table: str, limit: int = 100) -> str:
            """Query a Supabase table."""
            return f"Querying {table} with limit {limit}"

        @tool()
        async def insert_row(table: str, data: dict) -> str:
            """Insert a row into a Supabase table."""
            return f"Inserted into {table}: {data}"

    print("Server starting at http://127.0.0.1:8000")
    print("Metadata endpoint: http://127.0.0.1:8000/.well-known/mcp-server.json")
    print("\nFetch metadata with:")
    print("    curl http://127.0.0.1:8000/.well-known/mcp-server.json | jq")
    print()

    await server.serve(host="127.0.0.1", port=8000)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
