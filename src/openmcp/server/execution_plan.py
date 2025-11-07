# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Execution plan models and builders for delegated connectors."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence

from typing_extensions import Literal
from pydantic import BaseModel, Field, HttpUrl, constr


class _BaseModel(BaseModel):
    """Base model with shared configuration."""

    model_config = {
        "populate_by_name": True,
        "protected_namespaces": (),
        "extra": "forbid",
        "str_strip_whitespace": True,
    }


class ConnectionReference(_BaseModel):
    """Reference to a connection handle that the token authorised."""

    id: str = Field(..., min_length=1, description="Connection handle identifier (e.g. ddls:conn_supabase_01H…)")
    auth_type: str = Field(..., min_length=1, description="Authentication method (service_role_key, user_oauth_token, …)")
    fingerprint: str | None = Field(
        None,
        min_length=1,
        description="Optional fingerprint used to detect tampering.",
    )
    version: int | None = Field(None, ge=0, description="Metadata version for rolling connector updates.")
    scope: list[str] | None = Field(None, description="Scopes granted for this handle (parsed from the JWT claim).")


class TargetSpec(_BaseModel):
    """Describes the upstream surface contacted by the execution backend."""

    kind: constr(strip_whitespace=True, min_length=1) = Field(
        ...,
        description="Target type: rest, graphql, sql, or service:<slug> for bespoke drivers.",
    )
    base: HttpUrl | constr(strip_whitespace=True, min_length=1) | None = Field(
        None,
        description="Base URL (REST/GraphQL) or DSN / host identifier (SQL/custom).",
    )
    resource: HttpUrl | constr(strip_whitespace=True, min_length=1) | None = Field(
        None,
        description="Audience/resource URI used for downstream authorization decisions.",
    )


class AdditionalAuthenticatedData(_BaseModel):
    """Metadata captured for audit logging and correlation."""

    request_id: str = Field(..., min_length=1, description="Server-side request identifier.")
    tool: str | None = Field(None, min_length=1, description="Optional tool name for audit readability.")
    extra: dict[str, Any] | None = Field(None, description="Optional structured metadata for analytics.")


class ComputeHint(_BaseModel):
    """Hints that steer execution runtime selection."""

    mode: Literal["stateless", "stateful"] = Field(
        "stateless",
        description="Stateless workloads map to short-lived compute (e.g. Lambda); stateful requires longer-lived containers.",
    )
    profile: Literal["bursty", "durable"] | None = Field(
        None,
        description="High-level workload shape; bursty pairs with serverless, durable with provisioned compute.",
    )
    max_duration_ms: int | None = Field(None, ge=1, description="Upper bound on runtime before the task should abort.")


class WorkspaceHint(_BaseModel):
    """Filesystem or storage requirements for execution."""

    type: Literal["ephemeral", "persistent"] = Field(
        "ephemeral",
        description="Ephemeral workspaces map to tmpfs/ephemeral storage; persistent uses mounted volumes (e.g. EFS).",
    )
    size_mb: int | None = Field(None, ge=1, description="Workspace size in megabytes.")
    mount: str | None = Field(None, min_length=1, description="Desired mount point inside the execution container.")


class ExecutionPlan(_BaseModel):
    """Top-level execution plan consumed by the execution backend."""

    v: Literal[1] = Field(1, description="Plan schema version.")
    slug: str = Field(..., min_length=1, description="Marketplace/server identifier used for policy lookup.")
    connection: ConnectionReference = Field(..., description="Handle metadata describing which secret to use.")
    target: TargetSpec = Field(..., description="Upstream target details.")
    op: dict[str, Any] = Field(..., description="Driver-specific operation payload (REST/GraphQL/SQL/etc.).")
    mcp_user_credential: dict[str, Any] | None = Field(
        None,
        alias="_mcp_user_credential",
        description="Encrypted payload for user-delegated credentials (null for org secrets).",
    )
    compute: ComputeHint | None = Field(None, description="Optional compute/runtime hints.")
    workspace: WorkspaceHint | None = Field(None, description="Optional workspace requirements.")
    aad: AdditionalAuthenticatedData | None = Field(None, description="Authenticated metadata for auditing.")

    def model_dump_plan(self) -> dict[str, Any]:
        """Return the plan as a JSON-serialisable dictionary."""

        return self.model_dump(by_alias=True, exclude_none=True)


def _normalise_scope(scope_value: Any) -> list[str] | None:
    if scope_value is None:
        return None
    if isinstance(scope_value, str):
        return [chunk for chunk in scope_value.split() if chunk]
    if isinstance(scope_value, Sequence):  # type: ignore[arg-type]
        return [str(item) for item in scope_value]
    return None


def build_plan_from_claims(
    *,
    handle: str,
    claims: Mapping[str, Any],
    slug: str,
    target: Mapping[str, Any],
    op: Mapping[str, Any],
    request_id: str,
    tool: str | None = None,
    user_credential: Mapping[str, Any] | None = None,
    compute: Mapping[str, Any] | None = None,
    workspace: Mapping[str, Any] | None = None,
    aad_extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an execution plan using token claims and optional hints.

    Args:
        handle: Connection handle identifier.
        claims: Token claims (must include ``ddls:connections`` array).
        slug: Marketplace/server slug (policy lookup key).
        target: Target specification for the driver.
        op: Operation payload (method/path/query for REST, etc.).
        request_id: Correlation identifier for audits/logging.
        tool: Optional tool name for logging context.
        user_credential: Encrypted user credential blob, if applicable.
        compute: Optional compute hint mapping.
        workspace: Optional workspace hint mapping.
        aad_extra: Additional structured metadata to embed in the plan.

    Returns:
        Dict representing the execution plan ready to be sent to the execution backend.

    Raises:
        KeyError: If the requested handle is not present in the token claims.
    """

    connection_claim = None
    for entry in claims.get("ddls:connections", []):
        if isinstance(entry, Mapping) and entry.get("id") == handle:
            connection_claim = entry
            break
    if connection_claim is None:
        raise KeyError(f"Handle '{handle}' is not authorised by the current token")

    connection_ref = ConnectionReference(
        id=handle,
        auth_type=connection_claim.get("auth_type", "unknown"),
        fingerprint=connection_claim.get("fingerprint"),
        version=connection_claim.get("version"),
        scope=_normalise_scope(connection_claim.get("scope")),
    )

    aad_payload = AdditionalAuthenticatedData(
        request_id=request_id,
        tool=tool,
        extra=dict(aad_extra) if aad_extra else None,
    )

    plan = ExecutionPlan(
        slug=slug,
        connection=connection_ref,
        target=TargetSpec.model_validate(target),
        op=dict(op),
        mcp_user_credential=dict(user_credential) if user_credential else None,
        compute=ComputeHint.model_validate(compute) if compute else None,
        workspace=WorkspaceHint.model_validate(workspace) if workspace else None,
        aad=aad_payload,
    )

    return plan.model_dump_plan()


__all__ = [
    "ExecutionPlan",
    "ConnectionReference",
    "TargetSpec",
    "ComputeHint",
    "WorkspaceHint",
    "AdditionalAuthenticatedData",
    "build_plan_from_claims",
]
