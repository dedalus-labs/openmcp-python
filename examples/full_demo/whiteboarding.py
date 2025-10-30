"""Rough UX sketches for the "ambient context" story.

Nothing here runs – it's just the plan for how we want authors to write their
servers/clients once the helpers land.  Treat these blocks as the north star we
refine against before touching the public API.

--------------------------------------------------------------------------
Client side
--------------------------------------------------------------------------

# Goal: one `async with` that does the transport + MCP handshake.
# Keep the surface area tiny (think Triton).  Everything funnels through a
# single helper that takes a `transport=` switch rather than bespoke helpers
# per transport.

from openmcp.client import open_connection

async def run_agent():
    async with open_connection(
        "http://127.0.0.1:3000/mcp",
        transport="streamable-http",  # or "stdio", "lambda-http", ...
        client_info={"name": "demo"},
    ) as client:
        tools = await client.list_tools()
        await client.call_tool("search", {"query": "mcp"})

# Design notes:
# - `open_connection` wraps transport selection + `MCPClient`.
# - Inject MCP headers (Protocol-Version, Session-Id when required).
# - Return a thin façade with the common operations (`list_tools`, `call_tool`,
#   `ping`, and lower-level `send_request` for escape hatches).
# - Expose the raw session (and even the transport handles) via attributes for
#   power users, but document the high-level calls first.
# - Lower-level pieces (transport factories, `MCPClient`) stay importable for
#   bespoke flows—it’s just not the default path.


--------------------------------------------------------------------------
Server side
--------------------------------------------------------------------------

# Today: `with server.binding(): ...` already works well, but we want to
# document the patterns so users know *when* to re-enter the context.

from openmcp import MCPServer, tool
from my_app.plugins import github

server = MCPServer("productivity")

def bootstrap():
    with server.binding():
        @tool(tags=["math"])
        def add(a: int, b: int) -> int:
            return a + b

        github.mount(server)  # plugin registers its own tools/resources/prompts

    return server


# Runtime update example (webhook / feature flag):

async def enable_research_mode():
    with server.binding():
        @tool(tags=["research"])
        async def search_arxiv(query: str):
            ...

    server.allow_tools({"add", "search_arxiv"})
    await server.notify_tools_list_changed()


# What needs to be clean before we freeze the API:
# - Context manager naming: `binding` feels accurate now that the definitions
#   persist after the block exits; make sure docs/examples use this.
# - Document the lifecycle clearly: "define inside the context, but remember to
#   call `notify_*_list_changed` after mutating things for live sessions".
# - Provide helper(s) for common mutations, e.g. `with server.update_tools()`
#   that automatically triggers the notification on exit if something changed.
# - Ensure plugins can be re-applied without double-registering (our current
#   ToolSpec handling dedupes by name—call that out explicitly).


--------------------------------------------------------------------------
Open questions
--------------------------------------------------------------------------

- Do we want symmetry between server/client naming (`binding` vs an
  eventual `open_connection` alias on the server side)?
- Should notifications (`notify_tools_list_changed`) stay as top-level `server`
  helpers or move down to the service (`server.tools.notify_list_changed()`).
- For the client helper, do we expose `client.session` (raw SDK) or only our
  façade?  Current leaning: expose both but document the common path.
"""
