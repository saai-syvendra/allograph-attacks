"""A deterministic LangChain chat model for tests and dry runs.

A policy function sees the messages and the bound tool names and returns the next
AIMessage (text and/or tool calls). It lets the whole stack (deepagents, middleware,
MCP, A2A, VFS) run end to end without an API key.
"""

from __future__ import annotations

import itertools
from typing import Any, Callable, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr

Policy = Callable[[list[BaseMessage], list[str]], AIMessage]
_ids = itertools.count(1)


def call(name: str, **args: Any) -> dict:
    return {"name": name, "args": args, "id": f"call_{next(_ids)}", "type": "tool_call"}


class ScriptedChatModel(BaseChatModel):
    policy: Callable[..., AIMessage]
    _tool_names: list[str] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        clone = self.model_copy()
        names = []
        for t in tools:
            n = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
            if n is None and isinstance(t, dict) and "function" in t:
                n = t["function"].get("name")
            names.append(n or str(t))
        clone._tool_names = names
        return clone

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: Any = None, **kwargs: Any) -> ChatResult:
        msg = self.policy(messages, self._tool_names)
        return ChatResult(generations=[ChatGeneration(message=msg)])


def plan_policy(steps: list[list[dict] | str]) -> Policy:
    """Replay a fixed plan: each step is a list of tool calls, or a final text answer.

    The plan advances once per model turn of the top-level agent; subagent turns (which see a
    fresh conversation with a single human message) get a short final answer.
    """
    state = {"i": 0}

    def _policy(messages: list[BaseMessage], tools: list[str]) -> AIMessage:
        if sum(1 for m in messages if m.type == "human") == 1 and len(messages) == 1 and state["i"] > 0:
            return AIMessage(content="Subtask done.")
        if state["i"] >= len(steps):
            return AIMessage(content="Done.")
        step = steps[state["i"]]
        state["i"] += 1
        if isinstance(step, str):
            return AIMessage(content=step)
        return AIMessage(content="", tool_calls=step)

    return _policy
