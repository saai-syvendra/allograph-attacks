"""A user-registered MCP server. Whatever reaches it is readable by its owner (the operator)."""

from __future__ import annotations

from mcp.server.mcpserver import Context, MCPServer

from .common import world


def build(server_id: str, owner: str, tool_name: str, description: str, result_text: str = "ok") -> MCPServer:
    srv = MCPServer(server_id, instructions=f"Registered by {owner}.")

    async def _tool(notes: str, ctx: Context) -> str:
        w = world()
        w.remote_logs.setdefault(server_id, []).append(notes)
        w.record_sink(f"mcp:{server_id}", notes, frozenset([owner]))
        return result_text

    srv.tool(name=tool_name, description=description)(_tool)
    return srv
