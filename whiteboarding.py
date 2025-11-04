"""Working notes on design traits worth spreading across OpenMCP.

These notes were captured after refining the transport layer.  They are meant
to guide future refactors rather than ship as production code.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DesignPrinciple:
    """Simple container for the qualities we want to replicate elsewhere."""

    title: str
    description: str


TRANSPORT_PRINCIPLES: tuple[DesignPrinciple, ...] = (
    DesignPrinciple(
        title="Small, composable abstractions",
        description=(
            "The transports divide responsibilities between a minimal base class, "
            "the ASGI specialisation, and tiny adapters.  Every subclass overrides "
            "one or two focused hooks instead of threading through a forest of flags."
        ),
    ),
    DesignPrinciple(
        title="Configuration captured as data",
        description=(
            "Runtime behaviour lives in dataclasses (`ASGITransportConfig`, `ASGIRunConfig`) "
            "instead of loose kwargs.  This keeps call sites explicit, makes refactors safer, "
            "and provides natural spots for validation."
        ),
    ),
    DesignPrinciple(
        title="Clear extension seams",
        description=(
            "New transports plug in via `BaseTransport` without touching unrelated code.  "
            "Explicit protocols (`SessionManagerProtocol`) and typed hooks document the minimal "
            "surface area required for integrations."
        ),
    ),
    DesignPrinciple(
        title="Naming mirrors behaviour",
        description=(
            "Classes like `StreamableHTTPTransport` and `SessionManagerHandler` read like "
            "documentation.  Helper methods (`transport_display_name`, `_build_routes`) explain "
            "why they exist, so readers rarely need to chase definitions."
        ),
    ),
    DesignPrinciple(
        title="Tests in mind",
        description=(
            "Dependency points (`get_stdio_server`, `_to_asgi`) are factored out for injection.  "
            "This keeps unit tests lightweight and avoids monkeypatching internals."
        ),
    ),
)


def dump_principles() -> list[str]:
    """Return the principles as human-readable bullet points."""

    bullets: list[str] = []
    for principle in TRANSPORT_PRINCIPLES:
        bullets.append(f"- {principle.title}: {principle.description}")
    return bullets


if __name__ == "__main__":  # Manual scratchpad mode
    for line in dump_principles():
        print(line)
