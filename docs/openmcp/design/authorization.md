# OpenMCP Authorization Integration (Design Draft)

## Goals

- Support the HTTP authorization flow described in `docs/mcp/core/authorization`, ahead of the
  central Authorization Server (AS) going live at `https://as.dedaluslabs.ai`.
- Allow MCP servers built with OpenMCP to protect HTTP endpoints via OAuth 2.1 access tokens while
  remaining backward-compatible with unauthenticated deployments.
- Equip MCP clients to discover authorization requirements, register dynamically when needed, obtain
  tokens (PKCE + resource indicators), and attach them to subsequent requests.
- Keep the design modular so that downstream products can plug in alternative AS implementations or
  additional policy/guardrail layers.

## Non-goals

- Implement the AS itself; we assume an OAuth-compliant AS is available at
  `https://as.dedaluslabs.ai`.
- Support STDIO authorization (docs explicitly steer STDIO transports toward environment-driven
  credentials).
- Build UI/UX around login flows; downstream apps remain responsible for interactive consent screens.

## Overview

The design introduces opt-in authorization for the Streamable HTTP transport while keeping legacy
deployments unaffected. When enabled we model authorization as three cooperating subsystems:

1. **Discovery & metadata** – the server serves OAuth protected-resource metadata (PRM) at
   `/.well-known/oauth-protected-resource` with proper caching. Clients fetch and cache PRM and AS
   metadata (RFC 8414) using cache-aside, single-flight guards, and SSRF-safe HTTP fetchers.
2. **Token validation** – per-request middleware validates bearer tokens using a chain of validators:
   JWT verification with JWKS cache-aside (single-flight, TTL honoring `Cache-Control`) followed by
   an RFC 7662 introspection fallback. Validation enforces issuer/audience/resource (RFC 8707) and
   JWT BCP (reject `alg=none`, enforce leeway, pin algorithms). Optional DPoP support can be layered
   later.
3. **Client token lifecycle** – on `401` with `WWW-Authenticate`, the client runs discovery, optional
   dynamic client registration (RFC 7591), and an authorization-code-with-PKCE flow. Token storage
   implements single-flight refresh, monotonic expiry tracking, and circuit breakers around AS calls.

Tokens are attached via `Authorization: Bearer` and requests consistently supply the `resource`
indicator. Observability is built-in: each subsystem emits structured events (e.g. `auth.prm.cache.hit`,
`auth.jwt.valid`, `auth.refresh.fail`).

## Server Components

### Configuration

Extend `MCPServer` to accept an optional `authorization` configuration block:

```python
AuthorizationConfig(
    enabled=True,
    metadata_path="/.well-known/oauth-protected-resource",
    required_scopes=["mcp:read", "mcp:write"],
    fail_open=False,  # allow local/dev to bypass auth on AS outage
    cache_ttl=300,
)
```

Defaults keep authorization disabled for existing deployments. When enabled the server:

- Generates and serves protected-resource metadata (RFC 9728) under the configured path. Responses
  include `Cache-Control` headers so clients can cache aggressively, and optionally ETags for
  conditional requests.
- Advertises one or more AS URLs (initially `https://as.dedaluslabs.ai`) and supported scopes/audience.
- Issues `401 Unauthorized` responses with a `WWW-Authenticate` challenge that points to the PRM URL,
  following RFC 9728 section 5.1.

### Token Validation

Streamable HTTP middleware will:

1. Extract and parse the `Authorization` header. Missing/invalid headers immediately trigger a
   challenge with the PRM link.
2. Delegate to an `AuthorizationProvider` abstraction that attempts validation via a **chain** of
   small validators:
   - `JwtValidator` uses a JWKS cache (cache-aside, single-flight fetches, TTL honoring
     `Cache-Control`, circuit breaker per JWKS host) plus JWT BCP checks (`alg` allow-list,
     `iss`,`aud`,`exp`,`nbf` validation with small leeway, optional DPoP binding later).
   - `IntrospectionValidator` (RFC 7662) for opaque tokens or JWKS misses, guarded by its own breaker
     and exponential backoff.
3. Enforce required scopes and resource indicators: token `aud`/`resource` must contain the canonical
   server URI, otherwise reject with `invalid_token`.

The provider interface stays simple:

```python
class AuthorizationProvider(Protocol):
    async def validate(self, token: str) -> AuthorizationContext: ...
```

`AuthorizationContext` is attached to the request scope so handlers can inspect claims. A default
provider loads metadata from the AS discovered via PRM, but developers can swap implementations.

### Metadata Serving

A new handler exposes PRM at the configured path. It returns JSON aligned with RFC 9728 and includes
fields such as `resource`, `authorization_servers`, and `scopes_supported`. Responses set
`Cache-Control: public, max-age=<ttl>` so clients can cache per spec. Metadata generation must compute
the canonical resource URI (scheme + host + optional port/path) consistently; we’ll add helpers that
respect proxy headers (`X-Forwarded-Host`, etc.) for deployments behind load balancers.

### Request Context

On successful validation we attach the decoded token claims to the request context (e.g., via
`request_ctx` metadata) so tool/resource handlers can optionally inspect user identity or scopes.

## Client Components

### Capability & Config

`MCPClient` gains optional authorization settings:

```python
ClientAuthorizationConfig(
    enabled=True,
    token_store=TokenStore(...),
    client_registration=DynamicRegistrationConfig(...),
)
```

When enabled the client pipeline will:

1. Detect `401` responses with `WWW-Authenticate` headers. Parse the protected-resource metadata URI
   and feed it into a discovery cache that performs SSRF-safe fetches.
2. Fetch PRM and AS metadata (RFC 8414) using cache-aside storage with single-flight guards and
   per-host circuit breakers. Honor `Cache-Control`/`Expires` where provided.
3. Optionally perform dynamic client registration (RFC 7591) if a client ID/secret is not already
   stored.
4. Run the authorization-code-with-PKCE flow using host-provided hooks (e.g., open browser + await
   redirect). Always include the `resource` indicator (RFC 8707) to scope the token.
5. Persist access/refresh tokens in a `TokenStore` abstraction (in-memory, file-backed, or custom). The
   store deduplicates concurrent refresh attempts via single-flight and uses monotonic clocks for
   expiry.
6. Attach `Authorization: Bearer <token>` and `MCP-Protocol-Version` headers to all subsequent HTTP
   requests.

### Token Refresh

Implement automatic refresh with the refresh token grants exposed by the AS. The `TokenStore` tracks
expiry using monotonic clocks, wraps refresh operations in single-flight guards, and applies
exponential backoff with jitter plus a circuit breaker to avoid hammering the AS during outages.

### Error Handling

If token acquisition fails, raise a structured error (e.g., `AuthorizationError`) so hosting apps can
surface UX to the user. All error paths should emit structured logs (`auth.discovery.fail`,
`auth.refresh.fail`, etc.) to aid observability. For non-HTTP transports nothing changes.

## Shared Utilities

- JWKS caching helper with TTL and background refresh.
- URL helpers to compute canonical resource URIs.
- Pluggable storage abstraction (env var fallback, encrypted file store, in-memory for testing).
- CLI warnings/logging when authorization is required but config missing.

## Sequencing Plan

1. Land this design doc and gather feedback.
2. Implement server-side metadata + validation (feature-flagged).
3. Update Streamable HTTP transport to enforce tokens when enabled; add tests.
4. Extend `MCPClient` with discovery/registration/token management (mocked AS for tests).
5. Document configuration (`docs/openmcp/authorization.md`) and add integration examples.
6. Wire in the real AS endpoint when available; end-to-end smoke test using staging credentials.

## Open Questions

- How will hosted products capture OAuth redirect callbacks? (Likely per-app configuration; we expose a
  hook or callback interface.)
- Do we require mTLS or DPoP support from the AS? (Out of scope initially; rely on HTTPS + token
  claims.)
- Should we expose a lightweight policy interface so server authors can map scopes to tool/resource
  availability? (Nice-to-have once core flow is stable.)

## Risks

- AS downtime could block requests. We mitigate by caching validated tokens until expiry and allowing a
  “fail-open” optional mode for development.
- Clock skew can cause token validation failures; include leeway and log diagnostics.
- Dynamic registration may be disabled on the AS; clients must gracefully handle manual credential
  provisioning.
