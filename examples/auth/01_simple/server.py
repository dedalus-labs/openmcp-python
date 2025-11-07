# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Simplified Supabase REST API demo using only environment credentials.

Quick start::

    $ export SUPABASE_URL="https://<project>.supabase.co"
    $ export SUPABASE_SECRET_KEY="<service_role_key>"
    $ cd ~/Desktop/dedalus-labs/codebase/openmcp
    $ uv run python examples/auth/01_simple/server.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

from openmcp import MCPServer, tool

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL must be set")
if not SUPABASE_SECRET_KEY:
    raise RuntimeError("SUPABASE_SECRET_KEY must be set")

server = MCPServer(name="supabase-rest-demo")


with server.binding():

    @tool(description="Query Supabase REST API directly using the configured secret key.")
    async def supabase_query(
        table: str = "users",
        columns: str = "*",
        limit: int | None = 5,
    ) -> dict[str, Any]:
        """Execute a Supabase REST API query.

        Args:
            table: Table name to query
            columns: Columns to select (default: all columns)
            limit: Maximum rows to return (default: 5, None = no limit)

        Returns:
            Query results with status and body
        """
        params = {"select": columns}
        if limit is not None:
            params["limit"] = str(limit)

        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }

        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            body: Any = response.json()
        else:
            body = response.text

        log_context = {
            "event": "supabase.request",
            "table": table,
            "limit": limit,
            "status": response.status_code,
            "url": url,
        }

        row_count = len(body) if isinstance(body, list) else None

        if response.status_code >= 400:
            server._logger.warning("supabase request failed", extra={"context": {**log_context, "body": body}})
        else:
            server._logger.info("supabase request succeeded", extra={"context": {**log_context, "row_count": row_count}})

        return {
            "url": url,
            "status": response.status_code,
            "body": body,
        }


async def main() -> None:
    print(f"[supabase-demo] starting — SUPABASE_URL={SUPABASE_URL}")
    await server.serve(
        transport="streamable-http",
        verbose=False,
        log_level="info",
        uvicorn_options={"access_log": False},
    )


if __name__ == "__main__":
    asyncio.run(main())
