"""Countersign as a LangChain agent middleware.

Sits around every tool call of a deepagents/LangChain agent (and its subagents):
  * before an outbound call, runs C1/C2 and blocks unless allowed or confirmed;
  * after a call, records provenance: subagent and remote-agent replies are
    instruction-bearing text authored by whoever wrote that subagent or runs that agent.
The same middleware instance records effects even when no check is enabled (baseline D0),
so every configuration produces the same logs.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from ..platform.run_context import RunContext, Segment
from ..platform.tool_semantics import ToolMeta
from .checks import check_outbound


class Countersign(AgentMiddleware):
    def __init__(self, rc: RunContext, tool_meta: dict[str, ToolMeta],
                 subagent_authors: dict[str, frozenset[str]] | None = None,
                 reply_authors: dict[str, frozenset[str]] | None = None) -> None:
        super().__init__()
        self.rc = rc
        self.tool_meta = tool_meta
        self.subagent_authors = subagent_authors or {}
        self.reply_authors = reply_authors or {}    # tool name -> authors of its replies (A2A)

    @property
    def name(self) -> str:  # stable name so subagent stacks can carry it
        return "countersign"

    def _pre(self, call: dict) -> ToolMessage | None:
        name, args = call["name"], call.get("args", {}) or {}
        if name == "task":
            authors = self.subagent_authors.get(args.get("subagent_type", ""), frozenset())
            self.rc.add_segment(Segment(args.get("description", ""), "subagent", authors, True))
            return None
        meta = self.tool_meta.get(name)
        if meta is None or meta.effect == "read":
            return None
        decision = check_outbound(self.rc, meta, args)
        audience = meta.dest(args, self.rc.world, meta.identity or self.rc.invoker)[0] if meta.dest else frozenset()
        self.rc.world.record_effect(meta.key, meta.identity or self.rc.invoker, args, audience,
                                    decision.allow, decision.reason)
        if decision.allow and audience:
            # the replayed step shows data going to `audience`; only they may see it on replay
            self.rc.step(f"effect:{name}", str(args)[:200], audience)
        if decision.allow:
            return None
        return ToolMessage(content=f"Blocked by platform policy: {decision.reason}. "
                                   f"{self.rc.invoker} did not confirm this action.",
                           tool_call_id=call["id"], name=name, status="error")

    def _post(self, call: dict, result: Any) -> None:
        authors = self.reply_authors.get(call["name"])
        if authors and isinstance(result, ToolMessage):
            self.rc.add_segment(Segment(str(result.content), "a2a_reply", authors, True))

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        blocked = self._pre(request.tool_call)
        if blocked is not None:
            return blocked
        result = handler(request)
        self._post(request.tool_call, result)
        return result

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        blocked = self._pre(request.tool_call)
        if blocked is not None:
            return blocked
        result = await handler(request)
        self._post(request.tool_call, result)
        return result
