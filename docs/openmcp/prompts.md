# Prompts

**Problem**: MCP prompts require structured message payloads and argument definitions so clients can list templates and render parameterized conversations while maintaining spec compliance.

**Solution**: Provide a decorator that captures prompt metadata (name, description, arguments, icons) and a renderer that returns prompt messages in the expected shape. Handle required argument validation and error reporting automatically.

**OpenMCP**: Use `@prompt` within `server.collecting()` to register prompts. A renderer receives a dictionary of arguments and returns an iterable of `(role, content)` pairs, a list of `PromptMessage` objects, or a mapping containing `messages` and optional `description`. Missing required arguments raise `McpError` with the `INVALID_PARAMS` code. Listings (`prompts/list`) paginate via opaque cursors per the pagination spec, so clients can pass the returned `nextCursor` while bad cursors trigger an `INVALID_PARAMS` response and a missing `nextCursor` marks completion.

```python
from openmcp import MCPServer, prompt

server = MCPServer("prompter")

with server.collecting():
    @prompt(
        "daily-standup",
        description="Summarize yesterday/today/blockers",
        arguments=[{"name": "name", "required": True}],
    )
    def daily(arguments: dict[str, str]):
        target = arguments["name"]
        return [
            ("assistant", "You are a concise project bot."),
            ("user", f"Gather standup updates for {target}"),
        ]

# Render programmatically (mirrors `prompts/get`)
result = await server.invoke_prompt("daily-standup", arguments={"name": "Ada"})
```

- Spec receipts: `docs/mcp/spec/schema-reference/prompts-list.md`, `prompts-get.md`
- Advertise `listChanged` by toggling `NotificationFlags.prompts_changed` and emitting notifications when your prompt registry changes.
- Completions can target prompts directly using the `@completion(prompt=...)` decorator; see the companion document.
- Prompt renderers executed during an MCP request can call `get_context()` to
  log or stream progress (e.g. when generating resource-heavy prompt content).
