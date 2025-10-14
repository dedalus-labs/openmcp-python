"""Tests for completion capability.

These cases track the behaviour defined in
``docs/mcp/spec/schema-reference/completion-complete.md`` and the narrative in
``docs/mcp/capabilities/completion/protocol-messages.md``.
"""

from __future__ import annotations

import pytest

from openmcp import MCPServer, completion, types
from openmcp.completion import CompletionResult


@pytest.mark.anyio
async def test_prompt_completion_registration() -> None:
    """Prompt completions should respond with registered values (spec receipts)."""

    server = MCPServer("comp")

    with server.collecting():

        @completion(prompt="code_review")
        def language(argument: types.CompletionArgument, context: types.CompletionContext | None):
            assert argument.name == "language"
            assert argument.value.startswith("py")
            return ["python", "pytorch", "pyside"]

    ref = types.PromptReference(type="ref/prompt", name="code_review")
    argument = types.CompletionArgument(name="language", value="py")
    result = await server.invoke_completion(ref, argument)
    assert result is not None
    assert result.values == ["python", "pytorch", "pyside"]
    assert result.hasMore is None


@pytest.mark.anyio
async def test_resource_completion_limit_enforced() -> None:
    """Servers must not return more than 100 values (completion spec)."""

    server = MCPServer("comp-limit")

    long_list = [f"item-{i}" for i in range(150)]

    with server.collecting():

        @completion(resource="file:///{path}")
        def path_completion(argument: types.CompletionArgument, context: types.CompletionContext | None):
            assert argument.name == "path"
            return long_list

    ref = types.ResourceTemplateReference(type="ref/resource", uri="file:///{path}")
    argument = types.CompletionArgument(name="path", value="")
    result = await server.invoke_completion(ref, argument)
    assert result is not None
    assert len(result.values) == 100
    assert result.values[0] == "item-0"
    assert result.values[-1] == "item-99"
    assert result.hasMore is True


@pytest.mark.anyio
async def test_missing_completion_returns_empty() -> None:
    """Unknown completions resolve to empty arrays as per spec tolerance."""

    server = MCPServer("comp-missing")
    ref = types.PromptReference(type="ref/prompt", name="unknown")
    argument = types.CompletionArgument(name="language", value="py")
    result = await server.invoke_completion(ref, argument)
    assert result is not None
    assert result.values == []
    assert result.total is None


@pytest.mark.anyio
async def test_completion_result_dataclass() -> None:
    server = MCPServer("comp-result")

    with server.collecting():

        @completion(prompt="scenario")
        def scenario(argument: types.CompletionArgument, context: types.CompletionContext | None):
            return CompletionResult(values=["alpha", "beta"], total=2, has_more=False)

    ref = types.PromptReference(type="ref/prompt", name="scenario")
    argument = types.CompletionArgument(name="label", value="a")
    result = await server.invoke_completion(ref, argument)
    assert result is not None
    assert result.values == ["alpha", "beta"]
    assert result.total == 2
    assert result.hasMore is False


@pytest.mark.anyio
async def test_completion_mapping_with_has_more() -> None:
    server = MCPServer("comp-mapping")

    with server.collecting():

        @completion(resource="file:///{path}")
        def mapping_completion(argument: types.CompletionArgument, context: types.CompletionContext | None):
            return {"values": ["x", "y"], "hasMore": True}

    ref = types.ResourceTemplateReference(type="ref/resource", uri="file:///{path}")
    argument = types.CompletionArgument(name="path", value="")
    result = await server.invoke_completion(ref, argument)
    assert result is not None
    assert result.values == ["x", "y"]
    assert result.hasMore is True


@pytest.mark.anyio
async def test_completion_receives_context() -> None:
    server = MCPServer("comp-context")

    with server.collecting():

        @completion(prompt="contextual")
        def contextual(argument: types.CompletionArgument, context: types.CompletionContext | None):
            assert context is not None
            assert context.root == "root-id"
            return [argument.value.upper()]

    ref = types.PromptReference(type="ref/prompt", name="contextual")
    argument = types.CompletionArgument(name="word", value="mix")
    ctx = types.CompletionContext(root="root-id", path=["word"])
    result = await server.invoke_completion(ref, argument, context=ctx)
    assert result is not None
    assert result.values == ["MIX"]
