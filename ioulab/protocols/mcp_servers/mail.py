"""First-party mailbox, exposed over MCP. Sends go out as the authenticated subject."""

from __future__ import annotations

import json

from mcp.server.mcpserver import Context, MCPServer

from ...domain.world import Mail
from .common import denied, lab, subject, world


def build() -> MCPServer:
    srv = MCPServer("mail", instructions="Your mailbox.")

    @srv.tool(description="List messages in your inbox.")
    async def list_inbox(ctx: Context) -> str:
        who, w = subject(ctx), world()
        items = [{"id": m.id, "from": m.sender, "subject": m.subject, "_readers": lab(m.readers())}
                 for m in w.mail.values() if who in m.to]
        return json.dumps({"messages": items})

    @srv.tool(description="Read one message from your mailbox.")
    async def read_mail(mail_id: str, ctx: Context) -> str:
        who, w = subject(ctx), world()
        m = w.mail.get(mail_id)
        if m is None or who not in m.readers():
            raise denied()
        return json.dumps({"id": m.id, "from": m.sender, "to": m.to, "subject": m.subject,
                           "body": m.body, "_readers": lab(m.readers())})

    @srv.tool(description="Send an e-mail from your account. `to` is a list of names or addresses.")
    async def send_mail(to: list[str], subject_line: str, body: str, ctx: Context) -> str:
        who, w = subject(ctx), world()
        rcpt = [w.dir.resolve_address(a) for a in to]
        m = Mail(w.nid("m"), who, rcpt, subject_line, body)
        w.mail[m.id] = m
        w.record_sink("mail", f"{subject_line}\n{body}", m.readers())
        return json.dumps({"sent": m.id, "to": rcpt})

    return srv
