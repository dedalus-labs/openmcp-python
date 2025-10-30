# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Prompt capability tests.

Exercises the prompt lifecycle defined in
``docs/mcp/spec/schema-reference/prompts-list.md`` and
``docs/mcp/spec/schema-reference/prompts-get.md``.
"""

from __future__ import annotations

from mcp.shared.exceptions import McpError
import pytest

from openmcp import MCPServer, NotificationFlags, prompt, types
from tests.helpers import DummySession, run_with_context


@pytest.mark.anyio
async def test_prompt_registration_and_rendering() -> None:
    server = MCPServer("prompts")

    with server.binding():

        @prompt(
            "greet",
            description="Generate a greeting",
            arguments=[{"name": "name", "description": "Person to greet", "required": True}],
        )
        def greet(arguments: dict[str, str]):
            name = arguments["name"]
            return [("assistant", "You are a helpful assistant."), ("user", f"Say hello to {name}")]

    assert server.prompt_names == ["greet"]

    result = await server.invoke_prompt("greet", arguments={"name": "Ada"})
    assert result.description == "Generate a greeting"
    assert len(result.messages) == 2
    assert result.messages[1].content.type == "text"
    assert "Ada" in result.messages[1].content.text


@pytest.mark.anyio
async def test_prompt_missing_argument_raises_mcp_error() -> None:
    server = MCPServer("prompts-missing")

    with server.binding():

        @prompt("needs-arg", arguments=[{"name": "topic", "required": True}])
        def _needs_arg(arguments: dict[str, str]):
            return [("assistant", f"Topic is {arguments['topic']}")]

    with pytest.raises(McpError) as excinfo:
        await server.invoke_prompt("needs-arg")

    assert excinfo.value.error.code == types.INVALID_PARAMS


@pytest.mark.anyio
async def test_prompt_unknown_name_raises_mcp_error() -> None:
    server = MCPServer("prompts-unknown")

    with pytest.raises(McpError) as excinfo:
        await server.invoke_prompt("does-not-exist")

    assert excinfo.value.error.code == types.INVALID_PARAMS


@pytest.mark.anyio
async def test_prompt_custom_mapping_result() -> None:
    server = MCPServer("prompts-mapping")

    with server.binding():

        @prompt("status")
        async def status_prompt(_: dict[str, str]):
            return {"description": "Status template", "messages": [("assistant", "You summarize status reports.")]}

    result = await server.invoke_prompt("status")
    assert result.description == "Status template"
    assert result.messages[0].role == "assistant"


@pytest.mark.anyio
async def test_prompt_none_result_produces_empty_messages() -> None:
    server = MCPServer("prompts-none")

    with server.binding():

        @prompt("noop", description="No output")
        def noop(arguments: dict[str, str] | None = None):  # pragma: no cover - invoked below
            return None

    result = await server.invoke_prompt("noop")
    assert result.messages == []
    assert result.description == "No output"


@pytest.mark.anyio
async def test_prompts_list_pagination() -> None:
    server = MCPServer("prompts-pagination")

    with server.binding():
        for idx in range(120):

            def make_prompt(i: int):
                @prompt(f"prompt-{i:03d}")
                def _prompt(arguments: dict[str, str] | None = None, _i=i):
                    return [("user", f"Value {_i}")]

                return _prompt

            make_prompt(idx)

    handler = server.request_handlers[types.ListPromptsRequest]

    first = await run_with_context(DummySession("prompts-1"), handler, types.ListPromptsRequest())
    first_result = first.root
    assert len(first_result.prompts) == 50
    assert first_result.nextCursor == "50"

    second_request = types.ListPromptsRequest(params=types.PaginatedRequestParams(cursor="50"))
    second = await run_with_context(DummySession("prompts-2"), handler, second_request)
    second_result = second.root
    assert len(second_result.prompts) == 50
    assert second_result.nextCursor == "100"

    third_request = types.ListPromptsRequest(params=types.PaginatedRequestParams(cursor="100"))
    third = await run_with_context(DummySession("prompts-3"), handler, third_request)
    third_result = third.root
    assert len(third_result.prompts) == 20
    assert third_result.nextCursor is None


@pytest.mark.anyio
async def test_prompts_list_invalid_cursor() -> None:
    server = MCPServer("prompts-invalid-cursor")

    with server.binding():

        @prompt("one")
        def _one(arguments: dict[str, str] | None = None):
            return [("user", "hi")]

    handler = server.request_handlers[types.ListPromptsRequest]
    request = types.ListPromptsRequest(params=types.PaginatedRequestParams(cursor="bad"))

    with pytest.raises(McpError) as excinfo:
        await run_with_context(DummySession("prompts-invalid"), handler, request)

    assert excinfo.value.error.code == types.INVALID_PARAMS


@pytest.mark.anyio
async def test_prompts_list_cursor_past_end() -> None:
    server = MCPServer("prompts-past-end")

    with server.binding():
        for idx in range(2):

            @prompt(f"prompt-{idx}")
            def _prompt(arguments: dict[str, str] | None = None, _i=idx):
                return [("user", str(_i))]

    handler = server.request_handlers[types.ListPromptsRequest]
    request = types.ListPromptsRequest(params=types.PaginatedRequestParams(cursor="400"))
    response = await run_with_context(DummySession("prompts-past"), handler, request)

    assert response.root.prompts == []
    assert response.root.nextCursor is None


@pytest.mark.anyio
async def test_prompts_list_changed_notification_enabled() -> None:
    server = MCPServer("prompts-list-changed", notification_flags=NotificationFlags(prompts_changed=True))
    handler = server.request_handlers[types.ListPromptsRequest]
    session = DummySession("prompt-observer")

    await run_with_context(session, handler, types.ListPromptsRequest())
    await server.notify_prompts_list_changed()

    assert session.notifications
    assert session.notifications[-1].root.method == "notifications/prompts/list_changed"


@pytest.mark.anyio
async def test_prompts_list_changed_notification_disabled() -> None:
    server = MCPServer("prompts-list-changed-off")
    handler = server.request_handlers[types.ListPromptsRequest]
    session = DummySession("prompt-observer-off")

    await run_with_context(session, handler, types.ListPromptsRequest())
    await server.notify_prompts_list_changed()

    assert all(note.root.method != "notifications/prompts/list_changed" for note in session.notifications)
