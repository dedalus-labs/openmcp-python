# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

import importlib

import pytest

from openmcp import types, versioning
from openmcp._sdk_loader import ensure_sdk_importable


def _build_capabilities() -> types.ServerCapabilities:
    return types.ServerCapabilities(
        tools=types.ToolsCapability(listChanged=True),
        resources=types.ResourcesCapability(subscribe=True, listChanged=True),
        prompts=types.PromptsCapability(listChanged=True),
        logging=types.LoggingCapability(),
    )


@pytest.mark.anyio
async def test_supported_protocol_versions_patched() -> None:
    # Ensure the SDK is importable and patched.
    ensure_sdk_importable()
    shared_version = importlib.import_module("mcp.shared.version")

    assert shared_version.SUPPORTED_PROTOCOL_VERSIONS == versioning.SUPPORTED_PROTOCOL_VERSIONS
    assert [shared_version.SUPPORTED_PROTOCOL_VERSIONS[-1]] == shared_version.SUPPORTED_PROTOCOL_VERSIONS


@pytest.mark.anyio
async def test_get_features_returns_flags() -> None:
    ensure_sdk_importable()
    features = versioning.get_features()

    assert features.roots_list_changed is True
    assert features.prompts_list_changed is True
    assert features.resources_list_changed is True
    assert features.tools_list_changed is True
    assert features.sampling is True


@pytest.mark.anyio
async def test_initialize_result_pydantic_accepts_latest_version() -> None:
    ensure_sdk_importable()
    capabilities = _build_capabilities()
    init_result = types.InitializeResult(
        protocolVersion=types.LATEST_PROTOCOL_VERSION,
        capabilities=capabilities,
        serverInfo=types.Implementation(name="openmcp", version="0.1.0"),
    )

    assert init_result.protocolVersion == types.LATEST_PROTOCOL_VERSION
