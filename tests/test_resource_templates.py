# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Resource template tests (spec receipts: resources-templates-list)."""

from __future__ import annotations

import pytest

from openmcp import MCPServer, resource_template
from openmcp.resource_template import ResourceTemplateSpec


@pytest.mark.anyio
async def test_resource_template_registration():
    server = MCPServer("template-demo")

    with server.binding():

        @resource_template("docs", uri_template="resource://docs/{path}", description="Documentation files")
        def _docs():
            return None

    result = await server.list_resource_templates_paginated()
    assert len(result.resourceTemplates) == 1
    tmpl = result.resourceTemplates[0]
    assert tmpl.name == "docs"
    assert tmpl.uriTemplate == "resource://docs/{path}"
    assert tmpl.description == "Documentation files"


@pytest.mark.anyio
async def test_resource_template_decorator_metadata_fields():
    server = MCPServer("template-metadata")

    with server.binding():

        @resource_template(
            "docs",
            uri_template="resource://docs/{path}",
            title="Documentation",
            description="Docs with metadata",
            icons=[{"src": "file:///docs.png"}],
            annotations={"audience": ["user"]},
            meta={"category": "docs"},
        )
        def _docs():
            return None

    result = await server.list_resource_templates_paginated()
    assert len(result.resourceTemplates) == 1
    tmpl = result.resourceTemplates[0]
    assert tmpl.title == "Documentation"
    assert tmpl.description == "Docs with metadata"
    assert tmpl.icons and tmpl.icons[0].src == "file:///docs.png"
    assert tmpl.annotations and tmpl.annotations.audience == ["user"]
    assert tmpl.meta == {"category": "docs"}


@pytest.mark.anyio
async def test_resource_template_registration_outside_binding():
    server = MCPServer("template-register")

    @resource_template("assets", uri_template="resource://assets/{name}")
    def _assets():
        return None

    server.register_resource_template(_assets)
    result = await server.list_resource_templates_paginated()
    assert [tmpl.name for tmpl in result.resourceTemplates] == ["assets"]


@pytest.mark.anyio
async def test_resource_template_pagination():
    server = MCPServer("template-pagination")

    for idx in range(120):
        spec = ResourceTemplateSpec(
            name=f"tmpl-{idx:03d}", uri_template=f"resource://tmpl/{idx:03d}/{{id}}", description=f"Template {idx}"
        )
        server.register_resource_template(spec)

    first = await server.list_resource_templates_paginated()
    assert len(first.resourceTemplates) == 50
    assert first.nextCursor == "50"

    second = await server.list_resource_templates_paginated(first.nextCursor)
    assert len(second.resourceTemplates) == 50
    assert second.nextCursor == "100"

    third = await server.list_resource_templates_paginated(second.nextCursor)
    assert len(third.resourceTemplates) == 20
    assert third.nextCursor is None
