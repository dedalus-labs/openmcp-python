# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Protocol version helpers for OpenMCP.

OpenMCP currently targets the MCP 2025-06-18 specification.  This module provides
helpers for accessing the negotiated version and the associated feature flags so
callers can branch behavior explicitly if future revisions are introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Final

from ._sdk_loader import ensure_sdk_importable


ensure_sdk_importable()

from mcp.server.lowlevel.server import request_ctx
from mcp.types import LATEST_PROTOCOL_VERSION


# TODO: expand this list when we add compatibility adapters for older MCP
# revisions. For now we only speak the current spec (2025-06-18).
SUPPORTED_PROTOCOL_VERSIONS: Final[list[str]] = [LATEST_PROTOCOL_VERSION]


@dataclass(frozen=True)
class VersionFeatures:
    """Feature switches tied to a negotiated protocol version."""

    roots_list_changed: bool
    prompts_list_changed: bool
    resources_list_changed: bool
    tools_list_changed: bool
    sampling: bool


@cache
def _features_for(version: str) -> VersionFeatures:
    # For now, all toggles align with the 2025-06-18 revision.  Earlier revisions
    # can be added here when we introduce compatibility shims.
    if version != LATEST_PROTOCOL_VERSION:
        raise ValueError(f"Unsupported protocol version: {version}")

    return VersionFeatures(
        roots_list_changed=True,
        prompts_list_changed=True,
        resources_list_changed=True,
        tools_list_changed=True,
        sampling=True,
    )


def get_negotiated_version(default: str | None = None) -> str:
    """Return the protocol version negotiated for the current request.

    When called inside an MCP handler the request context is guaranteed to be
    set.  If the context is unavailable (e.g. during startup), ``default`` is
    returned instead.
    """
    try:
        ctx = request_ctx.get()
    except LookupError:
        if default is None:
            raise
        return default

    request = ctx.session
    # The reference server echoes the client's supported version or falls back
    # to the latest version.  Since OpenMCP limits support to 2025-06-18, we can
    # return that constant directly for now.  Keeping this helper allows us to
    # honour per-connection negotiation in the future without touching call
    # sites.
    return LATEST_PROTOCOL_VERSION


def get_features() -> VersionFeatures:
    """Shortcut to the feature flags for the active protocol version."""
    return _features_for(get_negotiated_version(default=LATEST_PROTOCOL_VERSION))


__all__ = ["SUPPORTED_PROTOCOL_VERSIONS", "VersionFeatures", "get_negotiated_version", "get_features"]
