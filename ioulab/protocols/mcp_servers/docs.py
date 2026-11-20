"""First-party document store (Drive-like), exposed over MCP."""

from __future__ import annotations

import json

from mcp.server.mcpserver import Context, MCPServer

from .common import denied, lab, subject, world


def build() -> MCPServer:
    srv = MCPServer("docs", instructions="Company documents (Drive-like).")

    @srv.tool(description="Search documents you can access. Returns id, title and a snippet.")
    async def search_docs(query: str, ctx: Context) -> str:
        who, w = subject(ctx), world()
        terms = query.lower().split()
        hits = []
        for d in w.docs.values():
            if who not in d.readers:
                continue
            text = f"{d.title} {d.body}".lower()
            if not terms or any(t in text for t in terms):
                hits.append({"id": d.id, "title": d.title, "snippet": d.body[:160], "_readers": lab(d.readers)})
        return json.dumps({"results": hits[:8]})

    @srv.tool(description="Read the full text of a document by id.")
    async def read_doc(doc_id: str, ctx: Context) -> str:
        who, w = subject(ctx), world()
        d = w.docs.get(doc_id)
        if d is None or who not in d.readers:
            raise denied()
        return json.dumps({"id": d.id, "title": d.title, "body": d.body, "_readers": lab(d.readers)})

    return srv
