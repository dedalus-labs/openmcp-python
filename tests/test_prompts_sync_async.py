# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Sync/async function support tests for prompts.

Exercises the maybe_await_with_args utility from utils/coro.py in the prompt
capability context, ensuring both synchronous and asynchronous prompt renderers
are correctly dispatched.

Spec reference: docs/mcp/spec/schema-reference/prompts-get.md
"""

from __future__ import annotations

import asyncio

import pytest

from openmcp import MCPServer, prompt


@pytest.mark.asyncio
async def test_sync_prompt_renderer():
    """Synchronous prompt renderers execute correctly."""
    server = MCPServer("sync-prompts")

    with server.binding():

        @prompt("greet", description="Synchronous greeting")
        def greet(arguments: dict[str, str]):
            name = arguments.get("name", "User")
            return [("assistant", f"Hello, {name}!")]

    assert "greet" in server.prompt_names

    result = await server.invoke_prompt("greet", arguments={"name": "Alice"})
    assert result.description == "Synchronous greeting"
    assert len(result.messages) == 1
    assert "Alice" in result.messages[0].content.text


@pytest.mark.asyncio
async def test_async_prompt_renderer():
    """Asynchronous prompt renderers execute correctly."""
    server = MCPServer("async-prompts")

    with server.binding():

        @prompt("greet_async", description="Asynchronous greeting")
        async def greet_async(arguments: dict[str, str]):
            await asyncio.sleep(0)
            name = arguments.get("name", "User")
            return [("assistant", f"Hello from async, {name}!")]

    assert "greet_async" in server.prompt_names

    result = await server.invoke_prompt("greet_async", arguments={"name": "Bob"})
    assert result.description == "Asynchronous greeting"
    assert len(result.messages) == 1
    assert "Bob" in result.messages[0].content.text


@pytest.mark.asyncio
async def test_mixed_sync_async_prompts():
    """Server supports both sync and async prompts simultaneously."""
    server = MCPServer("mixed-prompts")

    with server.binding():

        @prompt("sync_prompt", description="Sync prompt")
        def sync_prompt(arguments: dict[str, str]):
            topic = arguments.get("topic", "general")
            return [("user", f"Tell me about {topic}")]

        @prompt("async_prompt", description="Async prompt")
        async def async_prompt(arguments: dict[str, str]):
            await asyncio.sleep(0)
            topic = arguments.get("topic", "general")
            return [("user", f"Explain {topic} in detail")]

    assert "sync_prompt" in server.prompt_names
    assert "async_prompt" in server.prompt_names

    # Invoke sync prompt
    sync_result = await server.invoke_prompt("sync_prompt", arguments={"topic": "AI"})
    assert "AI" in sync_result.messages[0].content.text

    # Invoke async prompt
    async_result = await server.invoke_prompt("async_prompt", arguments={"topic": "ML"})
    assert "ML" in async_result.messages[0].content.text


@pytest.mark.asyncio
async def test_sync_prompt_with_dict_return():
    """Sync prompts can return dict with messages."""
    server = MCPServer("sync-dict-prompt")

    with server.binding():

        @prompt("formatted")
        def formatted(arguments: dict[str, str]):
            return {
                "messages": [
                    {"role": "assistant", "content": "How can I help?"},
                    {"role": "user", "content": arguments.get("query", "Hello")},
                ],
                "description": "Formatted response",
            }

    result = await server.invoke_prompt("formatted", arguments={"query": "Test"})
    assert result.description == "Formatted response"
    assert len(result.messages) == 2
    assert result.messages[1].content.text == "Test"


@pytest.mark.asyncio
async def test_async_prompt_with_dict_return():
    """Async prompts can return dict with messages."""
    server = MCPServer("async-dict-prompt")

    with server.binding():

        @prompt("formatted_async")
        async def formatted_async(arguments: dict[str, str]):
            await asyncio.sleep(0)
            return {
                "messages": [
                    {"role": "assistant", "content": "How can I assist?"},
                    {"role": "user", "content": arguments.get("query", "Hello")},
                ],
                "description": "Async formatted response",
            }

    result = await server.invoke_prompt("formatted_async", arguments={"query": "Async"})
    assert result.description == "Async formatted response"
    assert len(result.messages) == 2
    assert result.messages[1].content.text == "Async"


@pytest.mark.asyncio
async def test_sync_prompt_with_tuple_messages():
    """Sync prompts support (role, content) tuples."""
    server = MCPServer("sync-tuple")

    with server.binding():

        @prompt("tutorial")
        def tutorial(arguments: dict[str, str]):
            step = arguments.get("step", "1")
            return [
                ("assistant", "I'll explain the steps."),
                ("user", f"Explain step {step}"),
            ]

    result = await server.invoke_prompt("tutorial", arguments={"step": "3"})
    assert len(result.messages) == 2
    assert result.messages[0].role == "assistant"
    assert result.messages[1].role == "user"
    assert "step 3" in result.messages[1].content.text


@pytest.mark.asyncio
async def test_async_prompt_with_tuple_messages():
    """Async prompts support (role, content) tuples."""
    server = MCPServer("async-tuple")

    with server.binding():

        @prompt("tutorial_async")
        async def tutorial_async(arguments: dict[str, str]):
            await asyncio.sleep(0)
            step = arguments.get("step", "1")
            return [
                ("assistant", "I'll provide the tutorial."),
                ("user", f"Explain step {step}"),
            ]

    result = await server.invoke_prompt("tutorial_async", arguments={"step": "5"})
    assert len(result.messages) == 2
    assert result.messages[0].role == "assistant"
    assert "step 5" in result.messages[1].content.text


@pytest.mark.asyncio
async def test_sync_prompt_with_required_arguments():
    """Sync prompts enforce required arguments."""
    from mcp.shared.exceptions import McpError

    from openmcp import types

    server = MCPServer("sync-required")

    with server.binding():

        @prompt("needs_arg", arguments=[{"name": "topic", "required": True}])
        def needs_arg(arguments: dict[str, str]):
            return [("user", f"Topic: {arguments['topic']}")]

    # Valid call
    result = await server.invoke_prompt("needs_arg", arguments={"topic": "Python"})
    assert "Python" in result.messages[0].content.text

    # Missing required argument
    with pytest.raises(McpError) as excinfo:
        await server.invoke_prompt("needs_arg", arguments={})

    assert excinfo.value.error.code == types.INVALID_PARAMS


@pytest.mark.asyncio
async def test_async_prompt_with_required_arguments():
    """Async prompts enforce required arguments."""
    from mcp.shared.exceptions import McpError

    from openmcp import types

    server = MCPServer("async-required")

    with server.binding():

        @prompt("needs_async_arg", arguments=[{"name": "subject", "required": True}])
        async def needs_async_arg(arguments: dict[str, str]):
            await asyncio.sleep(0)
            return [("user", f"Subject: {arguments['subject']}")]

    # Valid call
    result = await server.invoke_prompt("needs_async_arg", arguments={"subject": "Rust"})
    assert "Rust" in result.messages[0].content.text

    # Missing required argument
    with pytest.raises(McpError) as excinfo:
        await server.invoke_prompt("needs_async_arg", arguments={})

    assert excinfo.value.error.code == types.INVALID_PARAMS


@pytest.mark.asyncio
async def test_sync_prompt_concurrent_execution():
    """Multiple sync prompt invocations can run concurrently."""
    server = MCPServer("sync-concurrent")
    execution_log = []

    with server.binding():

        @prompt("concurrent")
        def concurrent(arguments: dict[str, str]):
            execution_log.append(f"start-{arguments['id']}")
            execution_log.append(f"end-{arguments['id']}")
            return [("user", f"ID: {arguments['id']}")]

    # Execute multiple prompt invocations concurrently
    results = await asyncio.gather(
        server.invoke_prompt("concurrent", arguments={"id": "A"}),
        server.invoke_prompt("concurrent", arguments={"id": "B"}),
        server.invoke_prompt("concurrent", arguments={"id": "C"}),
    )

    # All should succeed
    assert len(results) == 3
    assert all(len(r.messages) == 1 for r in results)

    # Execution log should contain all events
    assert len(execution_log) == 6
    assert all(f"start-{x}" in execution_log for x in ["A", "B", "C"])


@pytest.mark.asyncio
async def test_async_prompt_concurrent_execution():
    """Multiple async prompt invocations can run concurrently."""
    server = MCPServer("async-concurrent")
    execution_log = []

    with server.binding():

        @prompt("concurrent_async")
        async def concurrent_async(arguments: dict[str, str]):
            execution_log.append(f"start-{arguments['id']}")
            await asyncio.sleep(0)
            execution_log.append(f"end-{arguments['id']}")
            return [("user", f"ID: {arguments['id']}")]

    # Execute multiple prompt invocations concurrently
    results = await asyncio.gather(
        server.invoke_prompt("concurrent_async", arguments={"id": "X"}),
        server.invoke_prompt("concurrent_async", arguments={"id": "Y"}),
        server.invoke_prompt("concurrent_async", arguments={"id": "Z"}),
    )

    # All should succeed
    assert len(results) == 3

    # Execution log should contain all events
    assert len(execution_log) == 6
    assert all(f"start-{x}" in execution_log for x in ["X", "Y", "Z"])
