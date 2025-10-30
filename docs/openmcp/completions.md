# Completions

**Problem**: MCP clients expect responsive suggestions for prompt arguments and resource templates via `completion/complete`, including result limits, pagination hints, and context-aware filtering.

**Solution**: Provide a simple registration API that binds completion providers to prompt names or resource URIs, normalizes return payloads to the spec format, and enforces the 100-item response cap.

**OpenMCP**: Decorate a callable with `@completion(prompt=...)` or `@completion(resource=...)`. The function receives the argument being completed plus optional context (previous arguments) and returns a list of suggestions, a `CompletionResult`, or raw `types.Completion`. OpenMCP handles coercion, `total`/`hasMore` fields, and capability advertisement automatically.

```python
from openmcp import MCPServer, completion, prompt

server = MCPServer("complete-demo")

with server.binding():
    @prompt("greet", arguments=[{"name": "name", "required": True}])
    def greet_prompt(args: dict[str, str]):
        return [("user", f"Greet {args['name']}")]

    @completion(prompt="greet")
    def suggest_names(argument, context):
        base = ["Ada", "Grace", "Katherine", "Barbara"]
        prefix = argument.value.lower()
        matches = [name for name in base if name.lower().startswith(prefix)]
        return {"values": matches, "total": len(base), "hasMore": len(matches) < len(base)}
```

- Spec receipts: `docs/mcp/spec/schema-reference/completion-complete.md`, `docs/mcp/capabilities/completion/index.md`
- OpenMCP limits responses to 100 items and toggles `hasMore` when truncation occurs.
- You can target resource template placeholders with `@completion(resource="file:///{path}")` to power URI autocompletion.
