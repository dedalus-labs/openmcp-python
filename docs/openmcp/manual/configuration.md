# Configuration Reference

This appendix documents every tunable parameter exposed by OpenMCP. Tables include defaults,
validation rules, and behavioural notes.

## MCPServer Parameters

| Name | Default | Behaviour |
| ---- | ------- | --------- |
| `name` | — | Advertised identifier (required). |
| `version` | `None` | Optional string included in initialization response. |
| `instructions` | `None` | Free-form guidance for clients; displayed during initialization. |
| `website_url` | `None` | Optional informational URL. |
| `icons` | `None` | List of `types.Icon`; empty list if unspecified. |
| `notification_flags` | all `False` | Controls list change notifications. |
| `experimental_capabilities` | `{}` | Copied into `capabilities.experimental`. |
| `lifespan` | reference SDK default | Async factory called during startup/shutdown. |
| `transport` | `"streamable-http"` | Default transport when calling `serve()`; set to `"stdio"` to default to STDIO. |
| `notification_sink` | `DefaultNotificationSink()` | Override to integrate custom notification delivery. |
| `http_security` | DNS rebinding protection enabled | Instance of `TransportSecuritySettings`; controls allowed hosts/origins. |
| `authorization` | `AuthorizationConfig(enabled=False)` | Opt-in authorization scaffolding. |

### AuthorizationConfig

| Field | Default | Behaviour |
| ----- | ------- | --------- |
| `enabled` | `False` | When `True`, the server serves PRM and enforces bearer tokens. |
| `metadata_path` | `"/.well-known/oauth-protected-resource"` | Route at which PRM is served. |
| `authorization_servers` | `["https://as.dedaluslabs.ai"]` | AS discovery list included in PRM. |
| `required_scopes` | `[]` | Scopes checked after token validation (provider-specific logic). |
| `cache_ttl` | `300` seconds | Used for PRM `Cache-Control` headers. |
| `fail_open` | `False` | When true, authorization failures log a warning and requests proceed (for development only). |

### TransportSecuritySettings (subset)

| Field | Default | Behaviour |
| ----- | ------- | --------- |
| `enable_dns_rebinding_protection` | `True` | Rejects Host headers that do not match allowed list. |
| `allowed_hosts` | `["127.0.0.1:*", "localhost:*"]` | Additional allowed host:port pairs. |
| `allowed_origins` | empty | Origins accepted for browser clients. |

### Ping Service Thresholds

| Attribute | Default | Behaviour |
| --------- | ------- | --------- |
| `interval` | `5.0` seconds | Heartbeat cadence. |
| `jitter` | `0.2` (20%) | Randomisation to avoid thundering herd. |
| `timeout` | `2.0` seconds | Ping timeout before a failure is recorded. |
| `phi_threshold` | `None` (use default) | Failure detector threshold; see `PingService.is_alive`. |
| `max_concurrency` | `None` | Optional semaphore for concurrent pings. |

### Sampling Service

| Attribute | Default | Behaviour |
| --------- | ------- | --------- |
| `timeout` | `60.0` seconds | Maximum wait for a client sampling response. |
| `max_concurrent` | `4` | Concurrency guard per client session. |
| `FAILURE_THRESHOLD` | `3` | Number of consecutive failures before cooldown is enforced. |
| `COOLDOWN_SECONDS` | `30.0` | Duration of cooldown period. |

### Elicitation Service

| Attribute | Default | Behaviour |
| --------- | ------- | --------- |
| `timeout` | `60.0` seconds | Maximum wait for elicitation responses. |

## MCPClient Parameters

| Name | Default | Behaviour |
| ---- | ------- | --------- |
| `capabilities` | `ClientCapabilitiesConfig()` | Enables optional features (roots, sampling, elicitation, logging). |
| `client_info` | `None` | Advertised via `initialize`. |

### ClientCapabilitiesConfig

| Field | Default | Behaviour |
| ----- | ------- | --------- |
| `enable_roots` | `False` | Advertise the `roots` capability. |
| `initial_roots` | `None` | Iterable of roots to expose immediately. |
| `sampling` | `None` | Callable returning `types.CreateMessageResult`. |
| `elicitation` | `None` | Callable returning `types.ElicitResult`. |
| `logging` | `None` | Callable invoked on `notifications/logging/message`. |

### Future: ClientAuthorizationConfig (Preview)

Not yet implemented. Planned fields include:

- `enabled`: toggle authorization handling.
- `token_store`: pluggable persistence (in-memory, file-based, custom).
- `client_registration`: settings for dynamic client registration.
- `http_client`: override to customise retry/backoff behaviour.

See `docs/openmcp/design/authorization.md` for the forthcoming design.

## Environment Variables

| Variable | Behaviour |
| -------- | --------- |
| `OPENMCP_LOG_LEVEL` | Overrides the default Python logging level (`INFO`). |
| `OPENMCP_PROGRESS_LOG_LEVEL` | Sets the logger level for progress telemetry (`DEBUG` by default). |

## Defaults Summary

- Pagination limit: 50 items per page.
- Heartbeat interval: 5 seconds with 20% jitter.
- Sampling timeout: 60 seconds.
- Progress emission: 8 Hz (can be adjusted via `set_default_progress_config`).
- Authorization: disabled unless `AuthorizationConfig.enabled` is set.

Refer back to the server/client guides for behavioural context and example usage.
