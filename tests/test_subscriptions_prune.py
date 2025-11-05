# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Unit tests for SubscriptionManager.prune_session outside request context.

Verifies that prune_session() can be called safely from cleanup/background tasks
without requiring an active request context (per spec section
``docs/mcp/spec/schema-reference/resources-subscribe.md``).
"""

from __future__ import annotations

import pytest

from openmcp.server.subscriptions import SubscriptionManager


@pytest.mark.anyio
async def test_prune_session_without_request_context() -> None:
    """prune_session() should work without request context."""
    manager = SubscriptionManager()

    # Create a mock session object
    class MockSession:
        pass

    session1 = MockSession()
    session2 = MockSession()

    # Manually populate the internal structures (simulating what subscribe_current would do)
    async with manager._lock:
        manager._by_uri["resource://test/1"].add(session1)
        manager._by_uri["resource://test/2"].add(session1)
        manager._by_uri["resource://test/2"].add(session2)

        manager._by_session[session1] = {"resource://test/1", "resource://test/2"}
        manager._by_session[session2] = {"resource://test/2"}

    # Verify initial state
    by_uri, by_session = await manager.snapshot()
    assert len(by_uri) == 2
    assert len(by_session) == 2

    # Prune session1 WITHOUT request context (this is the key test)
    await manager.prune_session(session1)

    # Verify session1 is gone
    by_uri, by_session = await manager.snapshot()
    assert len(by_session) == 1
    assert session2 in by_session
    assert session1 not in by_session

    # Verify URIs are updated
    assert "resource://test/1" not in by_uri  # No subscribers left
    assert "resource://test/2" in by_uri  # session2 still subscribed
    assert list(by_uri["resource://test/2"]) == [session2]

    # Prune session2
    await manager.prune_session(session2)

    # Verify everything is clean
    by_uri, by_session = await manager.snapshot()
    assert len(by_uri) == 0
    assert len(by_session) == 0


@pytest.mark.anyio
async def test_prune_session_nonexistent_session() -> None:
    """prune_session() should handle nonexistent sessions gracefully."""
    manager = SubscriptionManager()

    class MockSession:
        pass

    session = MockSession()

    # Pruning a session that was never added should not raise
    await manager.prune_session(session)

    by_uri, by_session = await manager.snapshot()
    assert len(by_uri) == 0
    assert len(by_session) == 0
