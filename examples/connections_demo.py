#!/usr/bin/env python3
"""Demo of the connection definition framework."""

from openmcp.server.connectors import ConnectorHandle, define


# Define connection types
HttpApiConn = define(
    kind="http-api",
    params={"base_url": str, "label": str},
    auth=["service_credential", "user_token"],
    description="HTTP API database connection",
)

PostgresConn = define(
    kind="postgres",
    params={"host": str, "port": int, "database": str},
    auth=["password", "cert"],
    description="PostgreSQL database connection",
)

RedisConn = define(
    kind="redis",
    params={"host": str, "port": int},
    auth=["password", "none"],
    description="Redis cache connection",
)


# Example: Create connection handles
def demo_http_api() -> None:
    """Demo HTTP API connection."""
    handle = ConnectorHandle(
        id="ddls:conn_http_api_prod",
        kind="http-api",
        config={
            "base_url": "https://api.example.com",
            "label": "myproject",
        },
        auth_type="service_credential",
    )

    # Validate handle against definition
    HttpApiConn.validate(handle)
    print(f"✓ Validated HTTP API connection: {handle.id}")


def demo_postgres() -> None:
    """Demo PostgreSQL connection."""
    handle = ConnectorHandle(
        id="ddls:conn_postgres_main",
        kind="postgres",
        config={
            "host": "localhost",
            "port": 5432,
            "database": "myapp",
        },
        auth_type="password",
    )

    PostgresConn.validate(handle)
    print(f"✓ Validated PostgreSQL connection: {handle.id}")


def demo_redis() -> None:
    """Demo Redis connection."""
    handle = ConnectorHandle(
        id="ddls:conn_redis_cache",
        kind="redis",
        config={
            "host": "localhost",
            "port": 6379,
        },
        auth_type="none",
    )

    RedisConn.validate(handle)
    print(f"✓ Validated Redis connection: {handle.id}")


def demo_serialization() -> None:
    """Demo JSON serialization for .well-known endpoint."""
    print("\nConnection definitions for .well-known endpoint:")
    print("-" * 50)

    for conn_type in [HttpApiConn, PostgresConn, RedisConn]:
        json_output = conn_type.definition.to_json()
        print(f"\n{json_output['kind']}:")
        print(f"  Description: {json_output['description']}")
        print(f"  Parameters: {list(json_output['params'].keys())}")
        print(f"  Auth methods: {json_output['auth_methods']}")


def demo_validation_errors() -> None:
    """Demo validation error handling."""
    print("\n\nValidation error examples:")
    print("-" * 50)

    # Wrong kind
    try:
        handle = ConnectorHandle(
            id="ddls:conn_wrong",
            kind="mysql",  # Wrong!
            config={"host": "localhost"},
            auth_type="password",
        )
        PostgresConn.validate(handle)
    except ValueError as e:
        print(f"\n✗ Wrong kind: {e}")

    # Missing params
    try:
        handle = ConnectorHandle(
            id="ddls:conn_incomplete",
            kind="postgres",
            config={"host": "localhost"},  # Missing port and database
            auth_type="password",
        )
        PostgresConn.validate(handle)
    except ValueError as e:
        print(f"✗ Missing params: {e}")

    # Wrong param type
    try:
        handle = ConnectorHandle(
            id="ddls:conn_badtype",
            kind="postgres",
            config={
                "host": "localhost",
                "port": "5432",  # Should be int!
                "database": "myapp",
            },
            auth_type="password",
        )
        PostgresConn.validate(handle)
    except TypeError as e:
        print(f"✗ Wrong param type: {e}")

    # Unsupported auth
    try:
        handle = ConnectorHandle(
            id="ddls:conn_badauth",
            kind="postgres",
            config={
                "host": "localhost",
                "port": 5432,
                "database": "myapp",
            },
            auth_type="kerberos",  # Not supported!
        )
        PostgresConn.validate(handle)
    except ValueError as e:
        print(f"✗ Unsupported auth: {e}")


if __name__ == "__main__":
    print("Connection Definition Framework Demo")
    print("=" * 50)

    demo_http_api()
    demo_postgres()
    demo_redis()
    demo_serialization()
    demo_validation_errors()

    print("\n" + "=" * 50)
    print("Demo complete!")
