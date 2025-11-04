from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

import openmcp._sdk_loader as sdk_loader


def _write_reference_sdk(root: Path) -> None:
    """Create a minimal reference SDK layout that satisfies imports."""

    package_dir = root / "mcp"
    shared_dir = package_dir / "shared"
    package_dir.mkdir()
    shared_dir.mkdir()

    (package_dir / "__init__.py").write_text("")
    (shared_dir / "__init__.py").write_text("")
    (shared_dir / "version.py").write_text("SUPPORTED_PROTOCOL_VERSIONS = ['draft']\n")
    (package_dir / "types.py").write_text("LATEST_PROTOCOL_VERSION = 'final'\n")


def _patch_import_module(monkeypatch, should_raise):
    real_import = importlib.import_module

    def fake_import(name):
        if name == "mcp" and should_raise():
            raise ModuleNotFoundError("missing reference SDK")
        return real_import(name)

    monkeypatch.setattr(sdk_loader, "import_module", fake_import)


def test_ensure_sdk_importable_adds_path_and_aligns_protocol(monkeypatch, tmp_path):
    modules_snapshot = dict(sys.modules)
    modules_snapshot.pop("mcp", None)
    for key in list(modules_snapshot):
        if key.startswith("mcp."):
            modules_snapshot.pop(key, None)
    monkeypatch.setattr(sys, "modules", modules_snapshot)
    monkeypatch.setattr(sys, "path", [])

    _patch_import_module(monkeypatch, lambda: str(tmp_path) not in sys.path)

    _write_reference_sdk(tmp_path)
    monkeypatch.setattr(sdk_loader, "_SDK_RELATIVE_PATH", tmp_path)

    sdk_loader.ensure_sdk_importable()

    assert str(tmp_path) in sys.path

    from mcp.shared import version as shared_version  # type: ignore import-not-found
    from mcp import types as mcp_types  # type: ignore import-not-found

    assert shared_version.SUPPORTED_PROTOCOL_VERSIONS == [mcp_types.LATEST_PROTOCOL_VERSION]


def test_ensure_sdk_importable_raises_when_reference_missing(monkeypatch, tmp_path):
    modules_snapshot = dict(sys.modules)
    modules_snapshot.pop("mcp", None)
    for key in list(modules_snapshot):
        if key.startswith("mcp."):
            modules_snapshot.pop(key, None)
    monkeypatch.setattr(sys, "modules", modules_snapshot)
    monkeypatch.setattr(sys, "path", [])

    _patch_import_module(monkeypatch, lambda: True)

    missing_root = tmp_path / "missing"
    monkeypatch.setattr(sdk_loader, "_SDK_RELATIVE_PATH", missing_root)

    with pytest.raises(ModuleNotFoundError) as exc:
        sdk_loader.ensure_sdk_importable()

    assert str(missing_root) in str(exc.value)
