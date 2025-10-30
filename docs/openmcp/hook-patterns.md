# Resource Update Hooks

**Problem**: Exposing resources is only half the battle—servers need a clean way to signal changes when the underlying data updates, especially when those updates originate outside MCP (filesystem, databases, webhooks, background jobs).

**Solution**: Provide simple hook points that call `server.notify_resource_updated(uri)` whenever a resource changes. You can wire these hooks into file watchers, async queues, or higher-level frameworks without touching the core MCP plumbing.

**OpenMCP Patterns**

1. **Tool-driven updates** – call the notifier from the tool that mutates state.

   ```python
   from openmcp import MCPServer, resource, tool

   server = MCPServer("hooks")

   state = {"value": "initial"}

   with server.binding():

       @resource("resource://demo/value")
       def read_value() -> str:
           return state["value"]

       @tool()
       async def set_value(new_value: str) -> str:
           state["value"] = new_value
           await server.notify_resource_updated("resource://demo/value")
           return state["value"]
   ```

2. **Webhook integration** – expose an HTTP endpoint (via FastAPI/Starlette) and call the notifier when remote systems POST updates.

   ```python
   from fastapi import FastAPI

   app = FastAPI()

   @app.post("/webhook")
   async def webhook(payload: dict):
       uri = payload["resource_uri"]
       await server.notify_resource_updated(uri)
       return {"status": "queued"}
   ```

3. **Background watcher** – run a polling or event-based watcher in a background task and emit notifications as files change.

   ```python
   import asyncio
   from pathlib import Path

   async def watch_file(path: Path, uri: str) -> None:
       last_mtime = path.stat().st_mtime
       while True:
           await asyncio.sleep(1)
           current = path.stat().st_mtime
           if current != last_mtime:
               last_mtime = current
               await server.notify_resource_updated(uri)
   ```

These hooks keep OpenMCP decoupled from external systems while giving users a crisp, spec-compliant way to alert MCP clients. Pair them with the subscription registry to ensure `resources/updated` only goes to clients that have opted in.
