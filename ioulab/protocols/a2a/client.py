"""A2A client tool: lets the platform agent delegate to a remote A2A agent.

The message carries the invoker as metadata (A2A leaves on-behalf-of to the deployment);
the remote agent still acts with its owner's authority.
"""

from __future__ import annotations

import uuid

from a2a.client import create_client
from a2a.helpers import get_message_text
from a2a.types import Message, Part, Role, SendMessageRequest
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class _AskArgs(BaseModel):
    message: str = Field(description="What to ask the remote agent. Include any context it needs.")


def a2a_tool(name: str, description: str, url: str, invoker: str) -> StructuredTool:
    client_holder: dict = {}

    async def _ask(message: str) -> str:
        if "c" not in client_holder:
            client_holder["c"] = await create_client(url)
        msg = Message(message_id=str(uuid.uuid4()), role=Role.ROLE_USER, parts=[Part(text=message)],
                      metadata={"on_behalf_of": invoker})
        texts = []
        async for ev in client_holder["c"].send_message(SendMessageRequest(message=msg)):
            if ev.HasField("message"):
                texts.append(get_message_text(ev.message))
            elif ev.HasField("task") and ev.task.status.HasField("message"):
                texts.append(get_message_text(ev.task.status.message))
        return "\n".join(t for t in texts if t) or "(no reply)"

    return StructuredTool(name=name, description=description, args_schema=_AskArgs, coroutine=_ask)
