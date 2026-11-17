"""Tools that ship inside Anexis. Outside tools come through MCP (see mcp_client.py)."""

from anexis.tools.builtin import canvas, core, desktop, system, web
from anexis.tools.registry import Registry


def register_builtin(registry: Registry, settings=None) -> None:
    for module in (core, system, web):
        for tool in module.TOOLS:
            registry.add(tool)
    for tool in desktop.tools():
        registry.add(tool)
    # The Canvas tools only make sense once the owner has given a Canvas token.
    if settings is not None and settings.env.get("CANVAS_TOKEN"):
        for tool in canvas.TOOLS:
            registry.add(tool)
