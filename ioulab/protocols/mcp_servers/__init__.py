"""MCP servers built with the official SDK (mcp 2.x `MCPServer`)."""

from . import collector, docs, hrdb, mail

FIRST_PARTY = {"docs": docs.build, "mail": mail.build, "hrdb": hrdb.build}

__all__ = ["FIRST_PARTY", "collector"]
