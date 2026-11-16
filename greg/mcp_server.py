"""A small read only MCP server for Claude Code.

It lets Claude look up who the owner is and how they like things done while it
writes code for them. Register it once with:

    claude mcp add --scope user greg-memory -- greg mcp
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from greg.config import Settings
from greg.memory.store import Memory

NOTHING = "Nothing is known about the owner yet."


def build_server(settings: Settings) -> MCPServer:
    server = MCPServer(
        "greg-memory",
        instructions="Read only access to what the owner's assistant knows about them. "
        "Check it before making choices about style, tools or naming.",
    )
    read_only = ToolAnnotations(read_only_hint=True)

    def open_memory() -> Memory | None:
        # Opened per call and read only, so this never competes with the main server.
        return Memory(settings.db_path, readonly=True) if settings.db_path.exists() else None

    @server.tool(annotations=read_only)
    def about_owner() -> str:
        """Who the owner is: name, school, work, projects, and how they want things done."""
        memory = open_memory()
        if memory is None:
            return NOTHING
        try:
            lines = [m.text for m in memory.pinned()]
            lines += [m.text for m in memory.list("lesson", 20) if not m.pinned]
            return "\n".join(f"- {line}" for line in lines) or NOTHING
        finally:
            memory.close()

    @server.tool(annotations=read_only)
    def search_memory(query: str) -> str:
        """Search what is remembered about the owner: preferences, habits, projects, past corrections."""
        memory = open_memory()
        if memory is None:
            return NOTHING
        try:
            found = memory.search(query, k=8)
            return "\n".join(f"- [{m.kind}] {m.text}" for m in found) or "Nothing remembered about that."
        finally:
            memory.close()

    return server
