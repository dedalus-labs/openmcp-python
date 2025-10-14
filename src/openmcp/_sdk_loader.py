"""Utilities for locating the reference MCP SDK.

This module ensures that the vendored Anthropics MCP reference implementation under
``references/python-sdk`` is importable. We rely on those primitives for protocol
compliance (see the upstream project for their implementation details).
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
import sys


_SDK_RELATIVE_PATH = Path(__file__).resolve().parents[2] / "references" / "python-sdk" / "src"


def ensure_sdk_importable() -> None:
    """Make the ``mcp`` package importable.

    The specification requires implementations to follow the canonical schema
    (see ``docs/mcp/spec/schema-reference/index.md``) and lifecycle rules in
    ``docs/mcp/core/lifecycle/lifecycle-phases.md``. Rather than re‑implementing
    the entire transport and schema layer, we reuse the reference SDK shipped in
    this repository.  If ``mcp`` is already on ``sys.path`` the function becomes a
    no-op; otherwise it appends the local SDK directory before importing it.
    """

    try:
        import_module("mcp")
    except ModuleNotFoundError:
        if _SDK_RELATIVE_PATH.is_dir():
            sys.path.append(str(_SDK_RELATIVE_PATH))
            import_module("mcp")
        else:
            raise ModuleNotFoundError(
                "Could not locate the reference MCP SDK. The directory"
                f" {_SDK_RELATIVE_PATH} is missing."
            )

    # Align the reference SDK's protocol support with OpenMCP.  We currently
    # implement the latest revision of the specification (2025-06-18) and make
    # that explicit so the upstream negotiation logic does not advertise
    # unsupported versions.
    from mcp.types import LATEST_PROTOCOL_VERSION
    from mcp.shared import version as shared_version

    shared_version.SUPPORTED_PROTOCOL_VERSIONS[:] = [LATEST_PROTOCOL_VERSION]


__all__ = ["ensure_sdk_importable"]
