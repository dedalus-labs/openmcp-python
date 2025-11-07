# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Tests for the execution plan schema and builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openmcp.server.execution_plan import ExecutionPlan, build_plan_from_claims


@pytest.fixture
def claims() -> dict[str, object]:
    return {
        "ddls:connections": [
            {
                "id": "ddls:conn_supabase_01H",
                "auth_type": "service_role_key",
                "fingerprint": "sha256:abc",
                "scope": "supabase:read supabase:write",
                "version": 1,
            }
        ]
    }


@pytest.mark.parametrize(
    "compute, workspace",
    [
        ({"mode": "stateless", "profile": "bursty"}, None),
        (None, {"type": "persistent", "size_mb": 1024, "mount": "/data"}),
    ],
)
def test_build_plan_from_claims(claims, compute, workspace):
    plan = build_plan_from_claims(
        handle="ddls:conn_supabase_01H",
        claims=claims,
        slug="supabase/generic",
        target={
            "kind": "rest",
            "base": "https://abc.supabase.co",
            "resource": "https://mcp.example.com/supabase",
        },
        op={"method": "GET", "path": "/rest/v1/users", "query": {"select": "*"}},
        request_id="req-123",
        tool="query_users",
        compute=compute,
        workspace=workspace,
    )

    assert plan["slug"] == "supabase/generic"
    assert plan["connection"]["id"] == "ddls:conn_supabase_01H"
    assert plan["connection"]["scope"] == ["supabase:read", "supabase:write"]
    assert plan["target"]["kind"] == "rest"
    assert "_mcp_user_credential" not in plan
    assert plan["aad"]["request_id"] == "req-123"
    if compute:
        assert plan["compute"]["mode"] == compute["mode"]
    if workspace:
        assert plan["workspace"]["type"] == workspace["type"]


def test_build_plan_infers_scope_list(claims):
    plan = build_plan_from_claims(
        handle="ddls:conn_supabase_01H",
        claims=claims,
        slug="supabase/generic",
        target={"kind": "rest", "base": "https://abc.supabase.co"},
        op={"method": "GET", "path": "/", "query": {}},
        request_id="req-456",
    )

    assert plan["connection"]["fingerprint"] == "sha256:abc"
    assert plan["aad"]["request_id"] == "req-456"


def test_build_plan_rejects_unknown_handle(claims):
    with pytest.raises(KeyError):
        build_plan_from_claims(
            handle="ddls:conn_missing",
            claims=claims,
            slug="supabase/generic",
            target={"kind": "rest", "base": "https://abc.supabase.co"},
            op={"method": "GET", "path": "/", "query": {}},
            request_id="req-789",
        )


def test_schema_snapshot_matches(tmp_path):
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "execution_plan.schema.json"
    stored = json.loads(schema_path.read_text())
    ExecutionPlan.model_rebuild(_types_namespace=globals())
    assert ExecutionPlan.model_json_schema() == stored
