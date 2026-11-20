"""Shared pieces for the MCP servers: the bound world, on-behalf-of tokens, labels.

First-party servers enforce their own ACLs against the identity carried in a signed
on-behalf-of token, which the platform puts in each call's `_meta`. Data items in results
carry `_readers` labels taken from the source ACL; the platform strips them before the
model sees the result.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from ...domain.world import World

OBO_META_KEY = "io.ioulab/obo"
_SECRET = b"ioulab-platform-signing-key"


class WorldHolder:
    """Servers can outlive a run; the world is swapped per run."""

    world: World | None = None


HOLDER = WorldHolder()


def sign_obo(subject: str, run_id: str) -> str:
    mac = hmac.new(_SECRET, f"{subject}|{run_id}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{subject}|{run_id}|{mac}"


def verify_obo(token: str | None) -> str:
    if not token:
        raise PermissionError("missing on-behalf-of token")
    subject, run_id, mac = token.split("|")
    good = hmac.new(_SECRET, f"{subject}|{run_id}".encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(mac, good):
        raise PermissionError("bad on-behalf-of token")
    return subject


def subject(ctx: Context) -> str:
    meta = ctx.request_context.meta or {}
    try:
        return verify_obo(meta.get(OBO_META_KEY))
    except (PermissionError, ValueError) as e:
        raise ToolError(f"unauthenticated: {e}") from e


def world() -> World:
    assert HOLDER.world is not None, "no world bound"
    return HOLDER.world


def lab(readers: frozenset[str]) -> list[str]:
    return sorted(readers)


def denied() -> ToolError:
    return ToolError("permission denied or not found")


def strip_labels(obj: Any, found: list[frozenset[str]]) -> Any:
    """Remove `_readers` labels from a JSON result, collecting them."""
    if isinstance(obj, dict):
        if "_readers" in obj:
            found.append(frozenset(obj["_readers"]))
        return {k: strip_labels(v, found) for k, v in obj.items() if k != "_readers"}
    if isinstance(obj, list):
        return [strip_labels(v, found) for v in obj]
    return obj
