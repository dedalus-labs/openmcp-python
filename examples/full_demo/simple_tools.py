"""Utility helpers for registering Brave Search tools in the demo server."""

from __future__ import annotations

from typing import Any

from brave_search_python_client import (
    BraveSearch,
    ImagesSearchRequest,
    NewsSearchRequest,
    VideosSearchRequest,
    WebSearchRequest,
)

from openmcp import tool
from openmcp.server import MCPServer

__all__ = ["register_brave_tools"]


def _serialise(result: Any) -> Any:
    """Return a JSON-serialisable representation of Brave responses."""

    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "dict"):
        return result.dict()
    return result


def register_brave_tools(server: MCPServer, *, api_key: str | None = None) -> None:
    """Register Brave Search tools onto *server*."""

    if api_key is None:
        raise ValueError("BRAVE_SEARCH_API_KEY not set; unable to configure Brave tools")

    client = BraveSearch(api_key=api_key)

    with server.binding():

        @tool(tags=["search", "web"])
        async def brave_web_search(query: str, count: int = 5):
            """Run a Brave web search and return the raw payload."""

            request = WebSearchRequest(q=query, count=count)
            response = await client.web(request)
            return _serialise(response)

        @tool(tags=["search", "images"])
        async def brave_image_search(query: str, count: int = 5):
            """Return Brave image search results."""

            request = ImagesSearchRequest(q=query, count=count)
            response = await client.images(request)
            return _serialise(response)

        @tool(tags=["search", "videos"])
        async def brave_video_search(query: str, count: int = 5):
            """Return Brave video search results."""

            request = VideosSearchRequest(q=query, count=count)
            response = await client.videos(request)
            return _serialise(response)

        @tool(tags=["search", "news"])
        async def brave_news_search(query: str, count: int = 5):
            """Return Brave news search results."""

            request = NewsSearchRequest(q=query, count=count)
            response = await client.news(request)
            return _serialise(response)
