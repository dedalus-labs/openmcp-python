# OpenMCP Logging Examples

This directory contains comprehensive examples for customizing OpenMCP's logging system.

## Files

- **`logging_customization_guide.md`** - Complete guide with all customization options
- **`custom_logging.py`** - Working code examples (server with custom logging)

## Quick Examples

### Default (Colored Console)

```python
from openmcp.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("Colored output by default")
```

### Disable Colors

```bash
# Standard NO_COLOR convention
export NO_COLOR=1
python your_app.py
```

Or in code:

```python
from openmcp.utils.logger import setup_logger, get_logger

setup_logger(use_color=False)
logger = get_logger(__name__)
```

### Custom Colors

```python
from openmcp.utils.logger import ColoredFormatter, setup_logger, get_logger
import logging

class MyColors(ColoredFormatter):
    LEVEL_COLORS = {
        "INFO": "\033[38;5;156m",    # Pastel green
        "ERROR": "\033[38;5;210m",   # Pastel red
        # ... customize all levels
    }

setup_logger(force=True)
root = logging.getLogger()
for handler in root.handlers:
    handler.setFormatter(MyColors())

logger = get_logger(__name__)
logger.info("Custom colors!")
```

### JSON Logging

```python
from openmcp.utils.logger import setup_logger, get_logger

setup_logger(use_json=True)
logger = get_logger(__name__)
logger.info("Structured", user_id=123)
```

### Custom Handler

```python
from openmcp.utils.logger import OpenMCPHandler, ColoredFormatter
import logging

class FilteredHandler(OpenMCPHandler):
    """Filter debug logs from noisy modules."""

    def emit(self, record):
        if record.levelno == logging.DEBUG and "noisy" in record.name:
            return
        super().emit(record)

# Use your custom handler
handler = FilteredHandler()
handler.setFormatter(ColoredFormatter())
# ... configure and add to root logger
```

## Design Philosophy

OpenMCP's logger is **intentionally minimal**:

1. **Zero dependencies** - Only stdlib + ANSI escapes
2. **Public extension points** - `ColoredFormatter` and `OpenMCPHandler`
3. **No config sprawl** - Subclass instead of adding flags
4. **Small core** - ~300 lines, easy to understand

## Third-Party Integration

The logger plays nicely with:

- **colorama** - Subclass `ColoredFormatter`, use colorama's `Fore`/`Style`
- **rich** - Replace handler entirely with `RichHandler`
- **orjson** - Pass `json_serializer=orjson.dumps` for fast JSON
- **structlog** - Use instead of OpenMCP's logger if you need more power

See `logging_customization_guide.md` for detailed examples of each.

## Standard Conventions

- **`NO_COLOR`** - Respects the [NO_COLOR](https://no-color.org/) standard
- **Environment variables** - `OPENMCP_LOG_LEVEL`, `OPENMCP_LOG_JSON`, `NO_COLOR`
- **Extension over configuration** - Subclass classes instead of adding config flags

## When to Use What

| You want... | Use... |
|-------------|--------|
| Default setup | `get_logger(__name__)` |
| No colors | `NO_COLOR=1` or `setup_logger(use_color=False)` |
| Different colors | Subclass `ColoredFormatter` |
| Filter logs | Subclass `OpenMCPHandler` |
| JSON output | `setup_logger(use_json=True)` |
| Rich/colorama | Replace handler or subclass formatter |

## See Also

- `src/openmcp/utils/logger.py` - Source (simple, readable)
- Python `logging` docs - Standard library reference
- [NO_COLOR](https://no-color.org/) - Standard for disabling colors
