# Versioning

**Problem**: MCP clients and servers can implement different protocol revisions (identified by
strings such as `2025-06-18`). Implementations must negotiate a single revision per session to avoid
subtle incompatibilities.

**Solution**: OpenMCP aligns with the reference SDK's negotiation, but narrows the supported set to
the latest revision the framework implements. Today that is `2025-06-18`. If a client requests an
older revision, it receives `2025-06-18` in the initialization response and can decide to proceed or
terminate.

**OpenMCP**: `ensure_sdk_importable()` patches the reference SDK so
`SUPPORTED_PROTOCOL_VERSIONS = ["2025-06-18"]`. Helpers in `openmcp.versioning` let you inspect the
negotiated version and associated feature switches if you need to branch behaviour explicitly in the
future.

```python
from openmcp.versioning import get_negotiated_version, get_features

version = get_negotiated_version(default="2025-06-18")
features = get_features()
```

- Spec receipts: `docs/mcp/capabilities/versioning`, `docs/mcp/spec/schema-reference/initialize.md`
- When we add compatibility shims for older revisions, `openmcp.versioning` will expose per-version
  codecs and feature flags so handlers remain clean and domain-focused.
