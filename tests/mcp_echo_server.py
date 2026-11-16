"""A tiny real MCP server used by the tests, run as its own process over stdio."""

import os
import sys

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("echo")


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def echo(text: str) -> str:
    """Repeat the text back."""
    return f"echo: {text}"


@server.tool()
def save_note(path: str, text: str) -> str:
    """Save a note to a file."""
    return f"saved {len(text)} chars to {path}"


@server.tool()
def explode() -> str:
    """Always fails."""
    raise RuntimeError("it broke")


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
def show_env(name: str) -> str:
    """Return one environment variable, or 'unset'."""
    return os.environ.get(name, "unset")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--crash":
        sys.exit(3)
    server.run("stdio")
