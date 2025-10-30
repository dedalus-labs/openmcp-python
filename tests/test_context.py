# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

import pytest

from openmcp import MCPServer, get_context, prompt, resource, tool, types
from tests.helpers import RecordingSession, run_with_context


def test_get_context_outside_request() -> None:
    with pytest.raises(LookupError):
        get_context()


@pytest.mark.anyio
async def test_tool_context_emits_logs_and_progress() -> None:
    server = MCPServer("ctx-tool")

    with server.binding():

        @tool(description="exercise context helper")
        async def sample() -> str:
            ctx = get_context()
            await ctx.info("processing", data={"stage": 1})
            async with ctx.progress(total=2) as tracker:
                await tracker.advance(1, message="halfway")
                await tracker.advance(1, message="complete")
            await ctx.debug("done")
            return "ok"

    session = RecordingSession("ctx-tool-session")
    meta = types.RequestParams.Meta(progressToken="token-123")

    result = await run_with_context(session, server.tools.call_tool, "sample", {}, meta=meta)

    assert result  # basic smoke check on return coercion
    assert [level for level, *_ in session.log_messages] == ["info", "debug"]
    assert session.log_messages[0][1]["msg"] == "processing"
    assert session.progress_events, "progress events should be emitted"
    assert {event["token"] for event in session.progress_events} == {"token-123"}
    assert session.progress_events[-1]["progress"] == pytest.approx(2)


@pytest.mark.anyio
async def test_tool_context_no_progress_token_is_noop() -> None:
    server = MCPServer("ctx-tool-no-progress")

    with server.binding():

        @tool(description="progress noop")
        async def sample() -> str:
            ctx = get_context()
            await ctx.report_progress(1.0, total=1.0, message="should not emit")
            return "ok"

    session = RecordingSession("ctx-tool-noop")
    meta = types.RequestParams.Meta()  # progressToken defaults to None

    await run_with_context(session, server.tools.call_tool, "sample", {}, meta=meta)

    assert session.progress_events == []


@pytest.mark.anyio
async def test_resource_read_binds_context() -> None:
    server = MCPServer("ctx-resource")
    seen: list[tuple[str, int]] = []

    with server.binding():

        @resource("resource://ctx", name="ctx")
        def sample() -> str:
            ctx = get_context()
            seen.append((ctx.request_id, ctx.progress_token or 0))
            return "ok"

    session = RecordingSession("ctx-resource-session")
    meta = types.RequestParams.Meta()

    await run_with_context(session, server.resources.read, "resource://ctx", meta=meta)

    assert seen, "resource handler should have observed a context"
    with pytest.raises(LookupError):
        get_context()


@pytest.mark.anyio
async def test_prompt_renderer_binds_context() -> None:
    server = MCPServer("ctx-prompt")
    seen: list[str] = []

    with server.binding():

        @prompt("ctx", description="ctx")
        def sample(arguments: dict[str, str] | None) -> list[tuple[str, str]]:
            ctx = get_context()
            seen.append(ctx.request_id)
            return [("assistant", "hello")]

    session = RecordingSession("ctx-prompt-session")
    meta = types.RequestParams.Meta()

    await run_with_context(session, server.prompts.get_prompt, "ctx", {}, meta=meta)

    assert seen, "prompt renderer should have observed a context"
    with pytest.raises(LookupError):
        get_context()


@pytest.mark.anyio
async def test_call_tool_without_request_context_succeeds() -> None:
    server = MCPServer("ctx-direct-tool")

    with server.binding():

        @tool(description="plain tool")
        async def sample() -> str:
            return "ok"

    result = await server.tools.call_tool("sample", {})

    assert result.content and result.content[0].text == "ok"


@pytest.mark.anyio
async def test_resource_read_without_request_context_succeeds() -> None:
    server = MCPServer("ctx-direct-resource")

    with server.binding():

        @resource("resource://direct")
        def sample() -> str:
            return "ok"

    contents = await server.resources.read("resource://direct")

    assert contents.contents and contents.contents[0].text == "ok"


@pytest.mark.anyio
async def test_prompt_get_without_request_context_succeeds() -> None:
    server = MCPServer("ctx-direct-prompt")

    with server.binding():

        @prompt("direct", description="direct")
        def sample(arguments: dict[str, str] | None) -> list[tuple[str, str]]:
            return [("assistant", "hello")]

    result = await server.prompts.get_prompt("direct", {})

    assert result.messages[0].content.text == "hello"
