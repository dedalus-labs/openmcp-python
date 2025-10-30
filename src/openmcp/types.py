# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Re-export of the MCP schema bindings.

The MCP schema (``docs/mcp/spec/schema-reference/index.md``) defines the
canonical JSON structures exchanged between clients and servers.  The reference
SDK already provides generated Pydantic models under ``mcp.types``; this module
re-exports them so consumers of :mod:`openmcp` can rely on a single import site.
"""

from __future__ import annotations

from importlib import import_module


import_module("mcp.types")
from mcp import types as _types


__all__ = tuple(name for name in dir(_types) if not name.startswith("_"))

globals().update({name: getattr(_types, name) for name in __all__})
