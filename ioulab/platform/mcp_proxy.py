"""The platform's MCP proxy.

For each connector a graph references, the proxy attaches it only if the invoker may use
it (deterministic, invoker-only attachment: baseline D0). Each MCP tool becomes a LangChain
tool. Calls carry a signed on-behalf-of token for the identity the connector runs as.
Results have their `_readers` labels stripped and folded into the run label.
"""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from mcp import Client
from mcp.server.mcpserver import MCPServer

from ..domain.artifacts import Artifact, RunsAs
from ..protocols.mcp_servers.common import OBO_META_KEY, sign_obo, strip_labels
from ..defenses.pi_baselines import provenance_note
from .run_context import RunContext, Segment
from .tool_semantics import MCP_SEMANTICS, ToolMeta, operator_dest


@dataclass
class AttachedConnector:
    artifact: Artifact
    server: MCPServer
    first_party: bool


class MCPProxy:
    def __init__(self, rc: RunContext, tool_meta: dict[str, ToolMeta], detector: Any = None) -> None:
        self.rc = rc
        self.detector = detector         # prompt-injection baseline: screens third-party tool descriptions
        self.tool_meta = tool_meta       # shared with Countersign, keyed by LangChain tool name
        self.stack = AsyncExitStack()

    async def __aenter__(self) -> "MCPProxy":
        await self.stack.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.stack.__aexit__(*exc)

    async def tools_for(self, conn: AttachedConnector) -> list[StructuredTool]:
        art, server = conn.artifact, conn.server
        client = await self.stack.enter_async_context(Client(server, mode="legacy"))
        listing = await client.list_tools()
        identity = self.rc.invoker if art.runs_as == RunsAs.INVOKER else art.owner
        operator = None if conn.first_party else art.owner
        tools = []
        for t in listing.tools:
            key = f"{art.id}.{t.name}"
            name = f"{art.id}_{t.name}"
            if conn.first_party:
                effect, dest = MCP_SEMANTICS.get(key, ("send", None))
            else:
                # a user-registered server: whatever reaches it is readable by its operator
                effect, dest = "send", operator_dest(art.owner, art.id)
                self.rc.add_segment(Segment(t.description or "", "tool_desc", frozenset([art.owner]), True))
            description = t.description or name
            if (not conn.first_party and self.detector is not None and self.rc.defense.pi_detector
                    and await self.detector(description, self.rc.user_text, provenance_note(self.rc, art.owner))):
                self.rc.pi_flags.append(f"tool_desc:{name}")
                description = name
            self.tool_meta[name] = ToolMeta(key, effect, dest, identity, operator)
            tools.append(self._wrap(client, t, name, identity, description))
        return tools

    def _wrap(self, client: Client, t: Any, name: str, identity: str, description: str) -> StructuredTool:
        rc = self.rc

        async def _call(**kwargs: Any) -> str:
            res = await client.call_tool(t.name, kwargs, meta={OBO_META_KEY: sign_obo(identity, rc.run_id)})
            text = "".join(getattr(c, "text", "") for c in res.content)
            if res.is_error:
                return f"Error: {text}"
            labels: list[frozenset[str]] = []
            try:
                text = json.dumps(strip_labels(json.loads(text), labels))
            except (json.JSONDecodeError, TypeError):
                pass
            step_label = None
            for lab in labels:
                rc.observe(lab)
                step_label = lab if step_label is None else step_label & lab
            rc.step(f"tool:{name}", f"{kwargs}\n{text}", step_label)
            return text

        return StructuredTool(name=name, description=description,
                              args_schema=t.input_schema, coroutine=_call)
