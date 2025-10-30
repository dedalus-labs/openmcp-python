# Security & Operational Notes

This section summarises the mitigations OpenMCP currently provides, along with TODO items aligned to
`docs/mcp/core/security-best-practices`.

## Implemented Safeguards

### Transport Security

- **DNS rebinding protection** is enabled by default for Streamable HTTP (`TransportSecuritySettings`).
- **Allowed hosts/origins** can be configured per deployment to tighten the envelope.
- STDIO deployments inherit the process boundary of the host system (no network exposure).

### Authorization (Opt-in)

- `AuthorizationConfig` serves RFC 9728 Protected Resource Metadata and enforces bearer tokens via the
  new middleware.
- `WWW-Authenticate` challenges follow the spec, pointing clients to the metadata endpoint.
- `fail_open` mode is off by default; enable only in development.

### Progress & Logging Hygiene

- `get_context()` isolates request-scoped context so handlers never import SDK internals.
- Progress helper enforces monotonic increases, coalesces updates, and retries with jitter.
- Logging emits structured payloads; consumers can route them to security monitoring systems.

### Heartbeat / Failure Detection

- `PingService` uses a phi-accrual failure detector and jittered scheduling to avoid correlated load.

## Planned / TODO (tracked)

| Area | Status | Notes |
| ---- | ------ | ----- |
| OAuth token validation | 🚧 In design | `AuthorizationProvider` interface ready; full JWT/JWKS/introspection support will land once the AS is available. |
| Authorization server discovery (clients) | 🚧 In design | Client-side flow (PRM, AS metadata, PKCE) outlined in `docs/openmcp/design/authorization.md`. |
| Token caching & circuit breakers | 🚧 In design | JWKS + metadata caches will use cache-aside + single-flight. |
| Request rate limiting | ⏳ Planned | No built-in limiter yet. Recommended: front OpenMCP with a proxy (nginx/envoy) or add middleware. |
| SSRF protection for outbound fetches | ⏳ Planned | When client-side discovery lands we will implement scheme/host allowlists. |
| Structured audit logging | ✅ Partial | Logging hooks in place; guidance to route to SIEMs will be documented alongside authorization rollout. |
| DPoP / mTLS support | ⏳ Deferred | Not required by MCP spec; revisit if server or AS mandates it. |
| Token passthrough prevention | ✅ | OpenMCP never forwards client tokens to downstream services; all tooling runs locally. |
| Session identifier entropy | ✅ (SDK) | Reference SDK generates random session IDs for Streamable HTTP; OpenMCP does not override. |

## Recommended Deployment Practices

- Terminate TLS in front of Streamable HTTP transports (Uvicorn can serve HTTPS or sit behind a proxy).
- Rotate authorization secrets and cached JWKS data regularly; observe the cache TTLs emitted in PRM.
- Instrument the structured logs (`auth.jwt.reject`, `auth.fail_open`, `progress.emitted`) to surface
  anomalies.
- When operating as an MCP proxy, ensure third-party OAuth flows are mediated per the “confused deputy”
  guidance (obtain user consent for each outgoing client registration, never re-use tokens for other
  resources).

Security extends beyond the framework; combine OpenMCP with infrastructure safeguards (WAF, reverse
proxy, SIEM) for production deployments.
