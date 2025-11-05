# OpenMCP Logging Customization Guide

Complete guide to customizing OpenMCP's logging system while keeping the core simple.

## Quick Start

```python
from openmcp.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("Colored output by default")
```

## Disabling Colors

### Method 1: NO_COLOR Environment Variable (Recommended)

Respects the standard `NO_COLOR` convention used by many CLI tools:

```bash
export NO_COLOR=1
python your_script.py
```

Or in Python:

```python
import os
os.environ["NO_COLOR"] = "1"

from openmcp.utils.logger import get_logger
logger = get_logger(__name__)
logger.info("No colors")
```

### Method 2: Explicit Parameter

```python
from openmcp.utils.logger import setup_logger, get_logger

setup_logger(use_color=False)
logger = get_logger(__name__)
logger.info("No colors")
```

### Method 3: JSON Mode (Colors Disabled Automatically)

```bash
export OPENMCP_LOG_JSON=1
python your_script.py
```

### Method 4: Plain Formatter

```python
import logging
from openmcp.utils.logger import setup_logger, get_logger

# Use plain formatter (no colors)
setup_logger(force=True)

# Replace with plain formatter
root = logging.getLogger()
for handler in root.handlers:
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

logger = get_logger(__name__)
logger.info("No colors here")
```

### Method 3: Custom Setup Function

```python
from openmcp.utils.logger import OpenMCPHandler, get_logger
import logging

def setup_plain_logging():
    """Set up logging without colors."""
    root = logging.getLogger()
    root.handlers.clear()

    handler = OpenMCPHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    root.addHandler(handler)
    root.setLevel(logging.INFO)

setup_plain_logging()
logger = get_logger(__name__)
```

## Custom Colors with OpenMCP's ColoredFormatter

### Using Built-in ANSI Constants

```python
from openmcp.utils.logger import (
    ColoredFormatter,
    setup_logger,
    get_logger,
    # Import color constants
    DEBUG_COLOR,
    INFO_COLOR,
    WARNING_COLOR,
    ERROR_COLOR,
    CRITICAL_COLOR,
    RESET,
    BOLD,
    DIM,
)
import logging

class MyColorScheme(ColoredFormatter):
    """Custom color palette using OpenMCP's constants."""

    LEVEL_COLORS = {
        "DEBUG": DEBUG_COLOR,      # Cyan
        "INFO": INFO_COLOR,        # Green
        "WARNING": WARNING_COLOR,  # Yellow
        "ERROR": ERROR_COLOR,      # Red
        "CRITICAL": f"{BOLD}{CRITICAL_COLOR}",  # Bold Magenta
    }

setup_logger(force=True)
root = logging.getLogger()
for handler in root.handlers:
    handler.setFormatter(MyColorScheme())

logger = get_logger(__name__)
logger.info("Using OpenMCP's color constants")
```

### Custom ANSI Codes (No Dependencies)

```python
from openmcp.utils.logger import ColoredFormatter, setup_logger, get_logger
import logging

class PastelColors(ColoredFormatter):
    """Pastel color scheme with 256-color ANSI."""

    LEVEL_COLORS = {
        "DEBUG": "\033[38;5;117m",   # Light blue
        "INFO": "\033[38;5;156m",    # Light green
        "WARNING": "\033[38;5;222m", # Light orange
        "ERROR": "\033[38;5;210m",   # Light red
        "CRITICAL": "\033[38;5;201m",# Bright pink
    }

setup_logger(force=True)
root = logging.getLogger()
for handler in root.handlers:
    handler.setFormatter(PastelColors())

logger = get_logger(__name__)
logger.info("Soft pastel colors")
```

## Using Third-Party Color Libraries

### With Colorama

```python
from openmcp.utils.logger import ColoredFormatter, setup_logger, get_logger
import logging

try:
    from colorama import Fore, Style, init
    init(autoreset=True)  # Auto-reset colors after each print

    class ColoramaFormatter(ColoredFormatter):
        """Use colorama's cross-platform colors."""

        LEVEL_COLORS = {
            "DEBUG": Fore.CYAN,
            "INFO": Fore.GREEN,
            "WARNING": Fore.YELLOW,
            "ERROR": Fore.RED,
            "CRITICAL": f"{Style.BRIGHT}{Fore.MAGENTA}",
        }

        def format(self, record):
            # Colorama handles reset automatically if autoreset=True
            result = super().format(record)
            return result + Style.RESET_ALL

    setup_logger(force=True)
    root = logging.getLogger()
    for handler in root.handlers:
        handler.setFormatter(ColoramaFormatter())

    logger = get_logger(__name__)
    logger.info("Using colorama (cross-platform)")

except ImportError:
    print("Install colorama: uv add colorama")
```

### With Rich (Advanced)

```python
from openmcp.utils.logger import OpenMCPHandler, get_logger
import logging

try:
    from rich.logging import RichHandler
    from rich.console import Console

    def setup_rich_logging():
        """Replace OpenMCP handler with Rich."""
        console = Console()

        rich_handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            show_time=True,
            show_path=True,
            markup=True,
        )
        rich_handler.setLevel(logging.INFO)

        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(rich_handler)
        root.setLevel(logging.INFO)

    setup_rich_logging()
    logger = get_logger(__name__)
    logger.info("[bold green]Rich markup support![/bold green]", extra={"markup": True})

except ImportError:
    print("Install rich: uv add rich")
```

## Custom Handler Behaviors

### Filter by Module

```python
from openmcp.utils.logger import OpenMCPHandler, ColoredFormatter, get_logger
import logging

class FilteredHandler(OpenMCPHandler):
    """Filter out debug logs from noisy modules."""

    IGNORED_MODULES = {"httpx", "urllib3", "boto3"}

    def emit(self, record):
        # Skip debug logs from noisy modules
        module_name = record.name.split(".")[0]
        if record.levelno == logging.DEBUG and module_name in self.IGNORED_MODULES:
            return
        super().emit(record)

# Set up filtered handler
handler = FilteredHandler()
handler.setLevel(logging.DEBUG)
handler.setFormatter(ColoredFormatter())

root = logging.getLogger()
root.handlers.clear()
root.addHandler(handler)
root.setLevel(logging.DEBUG)

logger = get_logger("myapp")
noisy_logger = get_logger("httpx")

logger.debug("This shows")
noisy_logger.debug("This is filtered")
```

### Rate Limiting

```python
from openmcp.utils.logger import OpenMCPHandler, ColoredFormatter, get_logger
import logging
import time
from collections import defaultdict

class RateLimitedHandler(OpenMCPHandler):
    """Rate-limit repeated log messages."""

    def __init__(self, *args, max_per_minute=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_per_minute = max_per_minute
        self.message_counts = defaultdict(list)

    def emit(self, record):
        now = time.time()
        key = (record.name, record.levelno, record.getMessage())

        # Clean old timestamps
        self.message_counts[key] = [
            ts for ts in self.message_counts[key]
            if now - ts < 60
        ]

        # Rate limit
        if len(self.message_counts[key]) >= self.max_per_minute:
            return

        self.message_counts[key].append(now)
        super().emit(record)

handler = RateLimitedHandler(max_per_minute=5)
handler.setFormatter(ColoredFormatter())

root = logging.getLogger()
root.handlers.clear()
root.addHandler(handler)

logger = get_logger(__name__)

# Only first 5 will show
for i in range(10):
    logger.info("Repeated message")
```

### Multi-Destination Logging

```python
from openmcp.utils.logger import OpenMCPHandler, ColoredFormatter, get_logger
import logging
from pathlib import Path

def setup_multi_destination():
    """Log to both console and file."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    # Console handler with colors
    console_handler = OpenMCPHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ColoredFormatter())
    root.addHandler(console_handler)

    # File handler without colors (plain text)
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    file_handler = logging.FileHandler(log_dir / "app.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    root.addHandler(file_handler)

setup_multi_destination()
logger = get_logger(__name__)

logger.debug("Only in file")
logger.info("In both console and file")
```

## Structured JSON Logging

### Basic JSON

```python
from openmcp.utils.logger import setup_logger, get_logger

setup_logger(use_json=True, force=True)
logger = get_logger(__name__)

logger.info("Structured log", user_id=123, action="login")
```

### With orjson (Performance)

```python
try:
    import orjson
    from openmcp.utils.logger import setup_logger, get_logger

    def orjson_serializer(payload):
        return orjson.dumps(payload).decode("utf-8")

    setup_logger(
        use_json=True,
        json_serializer=orjson_serializer,
        force=True
    )

    logger = get_logger(__name__)
    logger.info("Fast JSON", requests=1000)

except ImportError:
    print("Install orjson: uv add orjson")
```

### Redacting Sensitive Data

```python
from openmcp.utils.logger import setup_logger, get_logger
import re

def redact_sensitive(payload):
    """Redact credit cards, SSNs, tokens."""
    if "message" in payload:
        msg = payload["message"]
        # Redact patterns
        msg = re.sub(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b', '[CC-REDACTED]', msg)
        msg = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN-REDACTED]', msg)
        msg = re.sub(r'token=[\w-]+', 'token=[REDACTED]', msg)
        payload["message"] = msg
    return payload

setup_logger(
    use_json=True,
    payload_transformer=redact_sensitive,
    force=True
)

logger = get_logger(__name__)
logger.info("Card: 4532-1234-5678-9010, token=abc123xyz")
# Output: Card: [CC-REDACTED], token=[REDACTED]
```

## Environment-Based Configuration

```python
import os
from openmcp.utils.logger import setup_logger, get_logger

def configure_logging():
    """Configure based on environment."""
    env = os.getenv("ENVIRONMENT", "development")

    if env == "production":
        # JSON for log aggregation
        setup_logger(use_json=True, level="INFO")
    elif env == "staging":
        # JSON with debug
        setup_logger(use_json=True, level="DEBUG")
    else:
        # Colored console for development
        setup_logger(level="DEBUG")

    return get_logger(__name__)

logger = configure_logging()
logger.info(f"Configured for {os.getenv('ENVIRONMENT', 'development')}")
```

## Design Philosophy

OpenMCP's logger is intentionally minimal:

1. **Zero dependencies** - Uses only stdlib `logging` and ANSI escapes
2. **Extensibility over features** - Provide classes to subclass, not config flags
3. **Opt-in complexity** - Colors by default, everything else is user code
4. **Small surface area** - `ColoredFormatter` and `OpenMCPHandler` are the extension points

This keeps the core small (~300 lines) while letting you build exactly what you need.

## Quick Reference

| Goal | Approach |
|------|----------|
| Disable colors | Set `NO_COLOR=1` or `setup_logger(use_color=False)` |
| Custom colors | Subclass `ColoredFormatter` and override `LEVEL_COLORS` |
| Use colorama/rich | Subclass formatters or replace handler entirely |
| Filter logs | Subclass `OpenMCPHandler` and override `emit()` |
| JSON logging | `setup_logger(use_json=True)` |
| Fast JSON | Pass `json_serializer=orjson.dumps` |
| Redact sensitive | Pass `payload_transformer=your_function` |
| Multi-destination | Create multiple handlers with different formatters |

## See Also

- `examples/advanced/custom_logging.py` - Working code examples
- `src/openmcp/utils/logger.py` - Source code (simple, readable)
- Python `logging` docs - Standard library reference
