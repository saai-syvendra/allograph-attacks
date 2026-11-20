"""Assemble a runnable deep agent from a shared graph, for one invoker.

This is the baseline platform (setting D0):
  * connectors, remote agents and subagents are attached only if the invoker may use them,
    and connector calls run on the invoker's behalf;
  * skills and memory load from the platform VFS in layered scopes (space, group, user);
  * every instruction-bearing piece is recorded with its author.
Defenses plug in through `rc.defense`: pinning (C3), author ceiling, Countersign middleware
(C1/C2) and the prompt-injection baselines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from deepagents import SubAgent, create_deep_agent

from ..defenses.countersign import Countersign
from ..defenses.pi_baselines import Detector, PromptInjectionBaseline, provenance_note
from ..defenses.pinning import choose_versions
from ..domain.artifacts import Artifact, Piece, Registry, RunsAs
from ..protocols.a2a.client import a2a_tool
from ..protocols.a2a.server import A2AHost
from ..protocols.mcp_servers import FIRST_PARTY, collector
from .mcp_proxy import AttachedConnector, MCPProxy
from .run_context import RunContext, Segment
from .tool_semantics import FS_SEMANTICS, ToolMeta, operator_dest
from .vfs import INSTRUCTION_FILES, ScopedBackend


@dataclass
class Assembly:
    agent: Any
    tool_meta: dict[str, ToolMeta]
    attached: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _text(pieces: list[Piece]) -> str:
    return "\n\n".join(p.text for p in pieces)


def _fill(template: str, rc: RunContext) -> list[str]:
    """Expand {invoker} and {group} in a VFS path template."""
    if "{group}" in template:
        return [template.format(invoker=rc.invoker, group=g) for g in rc.world.dir.groups_of(rc.invoker)]
    return [template.format(invoker=rc.invoker)]


class Assembler:
    def __init__(self, registry: Registry, a2a_host: A2AHost | None = None,
                 detector: Detector | None = None) -> None:
        self.reg = registry
        self.a2a = a2a_host
        self.detector = detector

    # ---- helpers -----------------------------------------------------
    def _usable(self, rc: RunContext, art: Artifact, graph_authors: frozenset[str]) -> bool:
        if not self.reg.can_use(rc.invoker, art.id):
            return False
        if rc.defense.author_ceiling:
            return all(self.reg.can_use(a, art.id) for a in graph_authors if a in self.reg.dir.principals)
        return True

    def _file_authors(self, rc: RunContext, gc: dict) -> frozenset[str]:
        """Authors of the skill and memory files the graph links, as far as the invoker can see them."""
        sources = [p for t in gc.get("skill_sources", []) + gc.get("memory_sources", []) for p in _fill(t, rc)]
        return frozenset(f.author for path, f in rc.world.files.items()
                         if path.endswith(INSTRUCTION_FILES) and any(path.startswith(s) for s in sources)
                         and rc.invoker in rc.world.readers_of_path(path))

    def _provenance(self, rc: RunContext, author: str) -> str:
        return provenance_note(rc, author)

    async def _keep(self, rc: RunContext, piece: Piece, where: str) -> bool:
        """Prompt-injection detector baseline: drop flagged pieces not written by the invoker."""
        if self.detector is None or not rc.defense.pi_detector or piece.author == rc.invoker:
            return True
        if await self.detector(piece.text, rc.user_text, self._provenance(rc, piece.author)):
            rc.pi_flags.append(where)
            return False
        return True

    async def _filter_vfs(self, rc: RunContext) -> None:
        if self.detector is None or not rc.defense.pi_detector:
            return
        for path, f in list(rc.world.files.items()):
            if path.endswith(INSTRUCTION_FILES) and f.author != rc.invoker and rc.invoker in rc.world.readers_of_path(path):
                if await self.detector(f.content, rc.user_text, self._provenance(rc, f.author)):
                    rc.pi_flags.append(f"vfs:{path}")
                    del rc.world.files[path]

    def _server(self, art: Artifact, version: int | None):
        spec = art.at(version).content["server"]
        if isinstance(spec, str):
            return FIRST_PARTY[spec](), True
        return collector.build(art.id, art.owner, spec["tool"], spec["description"], spec.get("result", "ok")), False

    # ---- main --------------------------------------------------------
    async def build(self, rc: RunContext, graph_id: str, model: Any, proxy: MCPProxy,
                    pins: dict[str, int] | None = None) -> Assembly:
        graph = self.reg.get(graph_id)
        refs = graph.current.content
        linked = [graph] + [self.reg.get(i) for i in refs.get("connectors", []) + refs.get("subagents", [])]
        versions = choose_versions(rc, linked, pins or {})
        gc = graph.at(versions[graph.id]).content
        graph_authors = graph.authors(versions[graph.id]) | self._file_authors(rc, gc)
        tool_meta: dict[str, ToolMeta] = proxy.tool_meta   # one shared dict with the proxy
        tool_meta.update(FS_SEMANTICS)
        out = Assembly(agent=None, tool_meta=tool_meta)

        # system prompt, with authorship recorded per piece. The platform states who the user is,
        # as real platforms do; this text is the platform's own and is never screened or gated.
        who = self.reg.dir.principals.get(rc.invoker)
        identity = Piece(f"You are working for {who.display if who else rc.invoker} (user id: {rc.invoker}, "
                         f"email: {who.email if who else ''}). Their home folder is /home/{rc.invoker}/.",
                         "platform")
        pieces = [identity] + [p for p in gc.get("system", []) if await self._keep(rc, p, f"graph:{graph.id}")]
        for p in pieces:
            rc.add_segment(Segment(p.text, "graph", frozenset([p.author]), True))
        await self._filter_vfs(rc)

        async def connector_tools(ids: list[str]) -> list[Any]:
            tools = []
            for cid in ids:
                art = self.reg.get(cid)
                if not self._usable(rc, art, graph_authors):
                    out.skipped.append(cid)
                    continue
                server, first_party = self._server(art, versions.get(cid))
                tools += await proxy.tools_for(AttachedConnector(art, server, first_party))
                out.attached.append(cid)
            return tools

        tools = await connector_tools(gc.get("connectors", []))

        # remote A2A agents
        reply_authors: dict[str, frozenset[str]] = {}
        for aid in gc.get("agents", []):
            art = self.reg.get(aid)
            if self.a2a is None or not self._usable(rc, art, graph_authors):
                out.skipped.append(aid)
                continue
            name = f"ask_{aid}"
            content = art.current.content
            tools.append(a2a_tool(name, content["description"], self.a2a.url(aid), rc.invoker))
            tool_meta[name] = ToolMeta(f"a2a.{aid}", "send", operator_dest(art.owner, aid), rc.invoker, art.owner)
            reply_authors[name] = frozenset([art.owner])
            out.attached.append(aid)

        # subagents (shared specs, possibly authored by others)
        subagent_authors: dict[str, frozenset[str]] = {}
        countersign = Countersign(rc, tool_meta, subagent_authors, reply_authors)
        middleware: list[Any] = [countersign]
        if rc.defense.pi_spotlight or rc.defense.pi_detector:
            middleware.append(PromptInjectionBaseline(rc, self.detector if rc.defense.pi_detector else None,
                                                      rc.defense.pi_spotlight, reply_authors))
        subagents: list[SubAgent] = []
        for sid in gc.get("subagents", []):
            art = self.reg.get(sid)
            if not self._usable(rc, art, graph_authors):
                out.skipped.append(sid)
                continue
            sc = art.at(versions.get(sid)).content
            spieces = [p for p in sc["prompt"] if await self._keep(rc, p, f"subagent:{sid}")]
            subagent_authors[sc["name"]] = frozenset(p.author for p in spieces) | {art.owner}
            subagents.append(SubAgent(name=sc["name"], description=sc["description"],
                                      system_prompt=_text([identity] + spieces),
                                      tools=await connector_tools(sc.get("connectors", [])),
                                      middleware=list(middleware)))
            out.attached.append(sid)

        skills = [p for t in gc.get("skill_sources", []) for p in _fill(t, rc)]
        memory = [p for t in gc.get("memory_sources", []) for p in _fill(t, rc)]
        out.agent = create_deep_agent(
            model=model, tools=tools, system_prompt=_text(pieces), middleware=middleware,
            subagents=subagents or None, skills=skills or None, memory=memory or None,
            backend=ScopedBackend(rc), name=graph.id,
        )
        return out
