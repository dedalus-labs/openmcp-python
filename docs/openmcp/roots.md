# Roots

**DRAFT**: This documentation may change before publication as DX evolves.

**Problem**: MCP servers need to access client filesystems safely. Without boundaries, a server could read `/etc/passwd` or traverse `../../../secrets.json` when the client intended to expose only `~/projects/my-app`.

**Solution**: Clients advertise filesystem roots—explicit boundaries for what paths a server may access. Servers validate every filesystem operation against these roots, rejecting traversal attempts and out-of-bounds accesses before touching disk.

**OpenMCP**: The `RootsService` implements cache-aside architecture with per-session snapshots and immutable `RootGuard` reference monitors. Guards canonicalize paths (resolving symlinks, normalizing separators), parse file URIs across Windows and POSIX, and enforce boundaries via ancestor checks. Servers decorate handlers with `@require_within_roots()` to automatically reject invalid paths. Clients send `notifications/roots/list_changed` when boundaries shift; OpenMCP debounces these updates and maintains version-stable pagination cursors so ongoing `roots/list` requests never see torn reads.

---

## Overview

The roots capability (`https://modelcontextprotocol.io/specification/2025-06-18/client/roots`) establishes a reference monitor pattern for filesystem access in MCP. Clients declare which directories a server may touch; servers consult these boundaries before every path operation.

**Key properties**:
- **Defense in depth**: Even if a tool receives a malicious path from an LLM, the guard rejects it before filesystem access.
- **Symlink resolution**: Guards resolve symlinks to prevent bypass via `ln -s /etc secrets`.
- **File URI support**: Windows (`file:///c:/Users/alice/project`) and POSIX (`file:///home/alice/project`) URIs parse correctly.
- **Debounced updates**: When clients change roots mid-session, OpenMCP waits 250ms to batch notifications, avoiding cache thrash.
- **Version-stable cursors**: Pagination tokens embed snapshot versions. Stale cursors raise `INVALID_PARAMS`, forcing clients to restart pagination with fresh data.

---

## Specification

**Spec receipt**: `https://modelcontextprotocol.io/specification/2025-06-18/client/roots`

Clients advertise roots during capability negotiation or dynamically via `notifications/roots/list_changed`. Servers query roots with:

**`roots/list` request**:
```json
{
  "method": "roots/list",
  "params": { "cursor": "optional-opaque-token" }
}
```

**Response**:
```json
{
  "roots": [
    { "uri": "file:///home/alice/project", "name": "My Project" }
  ],
  "nextCursor": "base64-encoded-offset-and-version"
}
```

**`notifications/roots/list_changed` notification**:
```json
{
  "method": "notifications/roots/list_changed"
}
```

Servers MUST paginate `roots/list` if the client has many roots (limit defaults to 50). Invalid or stale cursors raise `INVALID_PARAMS` (-32602).

---

## Security Model

Roots implement a **reference monitor**: every filesystem access passes through the guard, which canonicalizes the path and checks ancestry against allowed roots.

**Threat model**:
1. **Directory traversal**: `../../../etc/passwd` canonicalizes to `/etc/passwd`, rejected if not under a declared root.
2. **Symlink bypass**: `project/secrets -> /etc` resolves to `/etc`, rejected if original root was `project`.
3. **Case sensitivity**: Windows paths like `C:\Users` and `c:\users` normalize to the same canonical form.
4. **Network paths (UNC)**: Windows `//server/share` URIs parse correctly via `urllib.request.url2pathname`.

**Non-goals**:
- Race conditions: Guards check paths at validation time, not open time. TOCTOU is possible but rare in typical MCP usage.
- Quota enforcement: Roots prevent unauthorized access but don't limit disk usage within allowed boundaries.

---

## RootGuard Path Validation

The `RootGuard` class (lines 57-100 in `src/openmcp/server/services/roots.py`) is the core reference monitor.

**Construction**:
```python
from openmcp.server.services.roots import RootGuard
from mcp import types

roots = (
    types.Root(uri="file:///home/alice/project", name="Project"),
    types.Root(uri="file:///tmp/scratch", name="Scratch"),
)
guard = RootGuard(roots)
```

**Validation logic**:
```python
from pathlib import Path

guard.within(Path("/home/alice/project/src/main.py"))  # True
guard.within("/home/alice/project/../project/src")     # True (canonicalized)
guard.within("/etc/passwd")                            # False
guard.within("file:///home/alice/project/data.json")   # True (file URI)
```

**Algorithm (`_canonicalize` method, lines 69-100)**:
1. **Parse input**: If string starts with `file://`, extract scheme, netloc, path.
   - Windows UNC: `file://server/share` → `//server/share` via `url2pathname`.
   - POSIX: `file:///path` → `/path`.
   - Otherwise: treat as local path string or `Path` object.
2. **Expand user**: `~/project` → `/home/alice/project`.
3. **Resolve symlinks**: `Path.resolve(strict=False)` follows symlinks without requiring existence.
4. **Normalize case** (Windows only): `Path(os.path.normcase(...))` ensures `C:\` and `c:\` match.
5. **Check ancestry**: For each root, verify `candidate == root` or `root in candidate.parents`.

**Edge cases**:
- Empty roots: `guard.within(anything)` returns `False` (deny-by-default).
- Relative paths: Resolved against current working directory, then checked.
- RuntimeError during resolution (rare Windows quirks): Silently ignored, using best-effort path.

---

## File URI Parsing

File URIs differ across platforms. OpenMCP handles both per RFC 8089.

**Windows examples**:
```python
# Local drive
"file:///c:/Users/alice/project"  →  Path("C:/Users/alice/project")

# UNC path
"file://server/share/folder"     →  Path("//server/share/folder")
```

**POSIX examples**:
```python
# Absolute path
"file:///home/alice/project"     →  Path("/home/alice/project")

# Localhost explicit
"file://localhost/tmp/scratch"   →  Path("/tmp/scratch")
```

**Implementation** (lines 76-90):
- On Windows: Use `urllib.request.url2pathname` for correct backslash conversion and UNC handling.
- On POSIX: Strip `file://` scheme, treat netloc as host (convert `//host/path` if not `localhost`), unquote percent-encoded characters.

**Testing note**: The Windows branches (`if os.name == "nt"`) are marked `# pragma: no cover` because CI runs on POSIX. Manually verify on Windows or use Docker with a Windows container.

---

## Cache-Aside Pattern

`RootsService` (lines 120-257) maintains per-session snapshots to avoid repeated RPC round-trips.

**Architecture**:
```
Client advertises roots
         ↓
Server calls client's roots/list (paginated)
         ↓
Snapshot stored in WeakKeyDictionary[ServerSession, _CacheEntry]
         ↓
Guard built from snapshot
         ↓
Handlers call guard.within(path)
```

**Cache entry** (lines 50-54):
```python
@dataclass(frozen=True)
class _CacheEntry:
    version: int             # Increments on refresh
    snapshot: Snapshot       # Immutable tuple of Root objects
    guard: RootGuard         # Immutable guard built from snapshot
```

**Version-stable cursors** (lines 197-233):
```python
def encode_cursor(self, session: ServerSession, offset: int) -> str:
    version = self.version(session)
    data = orjson.dumps({"v": version, "o": offset})
    return base64.urlsafe_b64encode(data).decode()

def decode_cursor(self, session: ServerSession, cursor: str | None) -> tuple[int, int]:
    expected_version = self.version(session)
    # ... parse cursor ...
    if version != expected_version:
        raise McpError(
            types.ErrorData(
                code=types.INVALID_PARAMS,
                message="Stale cursor for roots/list; please restart pagination",
                data={"expected": expected_version, "received": version},
            )
        )
    return version, offset
```

When a client sends `notifications/roots/list_changed`, OpenMCP debounces for 250ms (configurable via `debounce_delay`), then fetches fresh roots and increments the version. Any inflight pagination with old cursors will fail on the next call, forcing clients to restart.

**Why debounce?** A client editing `.mcprc` might trigger 10 notifications in rapid succession. Debouncing batches these into one refresh.

---

## Server-Side Usage

### Basic guard check (manual)

```python
from openmcp import MCPServer, tool
from mcp.server.lowlevel.server import request_ctx
from pathlib import Path

server = MCPServer("files")

with server.binding():
    @tool(description="Read file from allowed roots")
    async def read_file(path: str) -> str:
        # Manual validation
        context = request_ctx.get()
        guard = server.roots.guard(context.session)
        if not guard.within(path):
            raise ValueError(f"{path} is outside allowed roots")

        return Path(path).read_text()
```

### Decorator-based guard (recommended)

```python
@tool(description="Read file with automatic validation")
@server.require_within_roots(argument="path")
async def read_file_safe(path: str) -> str:
    # If we reach here, path is guaranteed valid
    return Path(path).read_text()
```

The `@require_within_roots()` decorator (lines 375-410 in `app.py`):
1. Extracts the specified argument (default `"path"`).
2. Retrieves the session from `request_ctx.get()`.
3. Calls `server.roots.guard(session).within(candidate)`.
4. Raises `McpError(INVALID_PARAMS)` if validation fails.
5. Otherwise, invokes the handler normally.

**Choosing argument name**:
```python
@server.require_within_roots(argument="file_path")
async def read(file_path: str) -> str:
    return Path(file_path).read_text()

@server.require_within_roots(argument="source")
async def copy(source: str, destination: str) -> str:
    # Only 'source' is validated; validate 'destination' manually if needed
    return f"Copied {source} to {destination}"
```

### Multi-path validation

```python
@tool(description="Copy file within roots")
@server.require_within_roots(argument="source")
async def copy_file(source: str, destination: str) -> str:
    # source is auto-validated; check destination manually
    context = request_ctx.get()
    guard = server.roots.guard(context.session)
    if not guard.within(destination):
        raise ValueError(f"{destination} is outside allowed roots")

    Path(destination).write_text(Path(source).read_text())
    return f"Copied {source} to {destination}"
```

**Why not decorate multiple arguments?** Python decorators stack, but `@require_within_roots()` expects a single argument name. For multi-path tools, validate additional paths manually inside the handler.

---

## Client Configuration

Clients advertise roots during initialization or dynamically via notifications.

### Static roots (initialization time)

```python
# Client-side pseudo-code (implementation varies by SDK)
client = MCPClient()
await client.initialize(
    client_capabilities={
        "roots": {
            "listChanged": True  # Client supports notifications
        }
    }
)

# Server queries roots/list
response = await client.request("roots/list")
# Returns: {"roots": [...], "nextCursor": null}
```

### Dynamic roots (runtime updates)

```python
# Client detects filesystem change (e.g., user edits .mcprc)
await client.notify("notifications/roots/list_changed")

# Server receives notification, debounces 250ms, then refreshes cache
# Next tool call sees updated roots
```

### Example client roots list response

```json
{
  "roots": [
    {
      "uri": "file:///home/alice/project",
      "name": "My Project"
    },
    {
      "uri": "file:///tmp/scratch",
      "name": "Temporary Workspace"
    }
  ],
  "nextCursor": null
}
```

**Pagination**: If a client has 200 roots, the server requests 50 at a time:

```
Request 1: roots/list { cursor: null }
Response 1: { roots: [...50...], nextCursor: "token1" }

Request 2: roots/list { cursor: "token1" }
Response 2: { roots: [...50...], nextCursor: "token2" }

...

Request 4: roots/list { cursor: "token3" }
Response 4: { roots: [...50...], nextCursor: null }
```

---

## Examples

### Safe file reader tool

```python
from openmcp import MCPServer, tool
from pathlib import Path

server = MCPServer("file-tools")

with server.binding():
    @tool(description="Read file contents from within client roots")
    @server.require_within_roots(argument="path")
    async def read_file(path: str) -> str:
        """Read a file from disk.

        Args:
            path: Absolute path to file (must be within client roots)

        Returns:
            File contents as text

        Raises:
            INVALID_PARAMS: If path is outside declared roots
            FileNotFoundError: If file doesn't exist
        """
        return Path(path).read_text()
```

**Client usage**:
```python
# Client declares roots: file:///home/alice/project

# Valid call
await client.call_tool("read_file", {"path": "/home/alice/project/README.md"})
# Returns file contents

# Invalid call (traversal attempt)
await client.call_tool("read_file", {"path": "/home/alice/project/../../../etc/passwd"})
# Server raises: INVALID_PARAMS: Path '/etc/passwd' is outside the client's declared roots
```

### File listing tool with directory validation

```python
from openmcp import tool, get_context
from pathlib import Path

@tool(description="List files in directory")
@server.require_within_roots(argument="directory")
async def list_files(directory: str) -> list[str]:
    """List all files in a directory.

    Args:
        directory: Path to directory (must be within roots)

    Returns:
        List of filenames (not full paths)
    """
    path = Path(directory)
    if not path.is_dir():
        raise ValueError(f"{directory} is not a directory")

    return [f.name for f in path.iterdir() if f.is_file()]
```

### Manual guard for resource handlers

Resources don't support decorators, so validate manually:

```python
from openmcp import resource, get_context
from mcp.server.lowlevel.server import request_ctx
from pathlib import Path

@resource("file://local/{path}", description="Serve local file as resource")
async def serve_file(path: str) -> str:
    """Serve file contents.

    Template parameter 'path' is extracted from URI like:
    file://local/home/alice/project/data.json
    """
    # Manual validation
    context = request_ctx.get()
    guard = server.roots.guard(context.session)
    if not guard.within(path):
        raise ValueError(f"{path} is outside allowed roots")

    return Path(path).read_text()
```

### Client roots configuration (pseudo-code)

```python
# Client-side: Configure roots before connecting to server
import os
from pathlib import Path

def get_allowed_roots() -> list[dict]:
    """Determine which directories to expose to MCP servers."""
    project_root = Path(os.getcwd())
    temp_dir = Path("/tmp/mcp-scratch")

    return [
        {
            "uri": project_root.as_uri(),  # e.g., file:///home/alice/project
            "name": "Current Project"
        },
        {
            "uri": temp_dir.as_uri(),      # e.g., file:///tmp/mcp-scratch
            "name": "Temporary Storage"
        }
    ]

# When client receives roots/list request from server:
async def handle_roots_list(params: dict) -> dict:
    roots = get_allowed_roots()
    cursor = params.get("cursor")

    # Simple implementation without pagination
    # (production client should paginate if many roots)
    if cursor:
        raise ValueError("No pagination needed for small root list")

    return {
        "roots": roots,
        "nextCursor": None
    }
```

### Testing guard behavior

```python
from openmcp.server.services.roots import RootGuard
from mcp import types
from pathlib import Path

def test_guard_validation():
    roots = (
        types.Root(uri="file:///home/alice/project", name="Project"),
    )
    guard = RootGuard(roots)

    # Valid paths
    assert guard.within("/home/alice/project/src/main.py")
    assert guard.within(Path("/home/alice/project/data"))
    assert guard.within("file:///home/alice/project/README.md")

    # Traversal attempts (canonicalized to /etc)
    assert not guard.within("/home/alice/project/../../../etc/passwd")
    assert not guard.within("/etc/passwd")

    # Outside root
    assert not guard.within("/home/bob/secrets")

    # Empty roots
    empty_guard = RootGuard(())
    assert not empty_guard.within("/home/alice/project/src")
```

### Debouncing demonstration

```python
import asyncio
from openmcp import MCPServer

server = MCPServer("test", notification_flags=NotificationFlags(roots_changed=True))

# Simulate rapid client notifications
async def client_edits_config():
    for _ in range(10):
        # Client sends notifications/roots/list_changed
        await server.roots.on_list_changed(session)
        await asyncio.sleep(0.05)  # 50ms between notifications

    # OpenMCP debounces to single refresh after 250ms quiet period
    await asyncio.sleep(0.3)

    # Only ONE RPC call to client's roots/list endpoint
    # (instead of 10 if no debouncing)
```

**Tuning debounce delay**:
```python
# Custom debounce for slow networks or chatty clients
server = MCPServer("files")
server.roots = RootsService(
    server._call_roots_list,
    debounce_delay=1.0  # Wait 1 second before refreshing
)
```

---

## See Also

- **Specification**: `https://modelcontextprotocol.io/specification/2025-06-18/client/roots`
- **Pagination**: `https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/pagination`
- **Reference implementation**: `src/openmcp/server/services/roots.py` (RootGuard: lines 57-100)
- **Related docs**:
  - `docs/openmcp/tools.md` — Tool registration and schema inference
  - `docs/openmcp/resources.md` — Resource serving and subscriptions
  - `docs/openmcp/context.md` — Accessing session context in handlers
  - `docs/openmcp/pagination.md` — Cursor-based pagination semantics (when implemented)
- **Security references**:
  - RFC 8089 (File URI Scheme): `https://www.rfc-editor.org/rfc/rfc8089.html`
  - OWASP Path Traversal: `https://owasp.org/www-community/attacks/Path_Traversal`
