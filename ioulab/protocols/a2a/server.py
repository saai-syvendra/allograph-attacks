"""Remote agents served over real A2A (a2a-sdk 1.x, JSON-RPC binding, spec v1.0).

One uvicorn process-local server hosts several agents under /agents/<id>/. Each remote
agent is opaque and runs as its owner: whatever it receives is readable by that owner.
Behaviour is set per run (the reply text), so one long-lived server serves every run.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass

import uvicorn
from a2a.helpers import new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue_v2 import EventQueue
from a2a.server.request_handlers import DefaultRequestHandlerV2
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette
from starlette.routing import Mount

from ..mcp_servers.common import HOLDER


@dataclass
class RemoteAgentBehavior:
    owner: str
    reply: str


class Behaviors:
    """Per-run behaviour for each hosted agent id."""

    by_id: dict[str, RemoteAgentBehavior] = {}


class _Executor(AgentExecutor):
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        text = context.get_user_input()
        beh = Behaviors.by_id[self.agent_id]
        w = HOLDER.world
        if w is not None:
            w.remote_logs.setdefault(f"a2a:{self.agent_id}", []).append(text)
            w.record_sink(f"a2a:{self.agent_id}", text, frozenset([beh.owner]))
        await event_queue.enqueue_event(new_text_message(beh.reply, context_id=context.context_id))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        return None


def _card(agent_id: str, description: str, url: str) -> AgentCard:
    return AgentCard(
        name=agent_id, description=description, version="1.0",
        supported_interfaces=[AgentInterface(url=f"{url}/a2a", protocol_binding="JSONRPC", protocol_version="1.0")],
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text/plain"], default_output_modes=["text/plain"],
        skills=[AgentSkill(id=agent_id, name=agent_id, description=description, tags=["ioulab"])],
    )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class A2AHost:
    def __init__(self, agents: dict[str, str]) -> None:
        """`agents` maps agent id -> card description."""
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        mounts = []
        for aid, desc in agents.items():
            url = f"{self.base}/agents/{aid}"
            card = _card(aid, desc, url)
            handler = DefaultRequestHandlerV2(agent_executor=_Executor(aid), task_store=InMemoryTaskStore(),
                                              agent_card=card)
            mounts.append(Mount(f"/agents/{aid}", routes=create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/a2a")))
        self._server = uvicorn.Server(uvicorn.Config(Starlette(routes=mounts), host="127.0.0.1",
                                                     port=self.port, log_level="warning"))
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def url(self, agent_id: str) -> str:
        return f"{self.base}/agents/{agent_id}"

    def start(self) -> "A2AHost":
        self._thread.start()
        deadline = time.time() + 10
        while not self._server.started and time.time() < deadline:
            time.sleep(0.05)
        return self

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)
