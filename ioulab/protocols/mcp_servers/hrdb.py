"""First-party HR records over MCP. Employees see their own row; HR sees all rows."""

from __future__ import annotations

import json

from mcp.server.mcpserver import Context, MCPServer

from .common import denied, lab, subject, world


def build() -> MCPServer:
    srv = MCPServer("hrdb", instructions="HR records.")

    @srv.tool(description="Get the HR record for an employee (user id or name).")
    async def get_employee(user: str, ctx: Context) -> str:
        who, w = subject(ctx), world()
        uid = w.dir.resolve_address(user)
        row = w.hr.get(uid)
        readers = w.hr_row_readers(uid)
        if row is None or who not in readers:
            raise denied()
        return json.dumps({"user": uid, "salary": row.salary, "rating": row.rating,
                           "notes": row.notes, "_readers": lab(readers)})

    return srv
