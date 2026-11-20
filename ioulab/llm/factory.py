"""Build LangChain chat models from `provider:model` strings.

Examples: `anthropic:claude-haiku-5-5`, `openai:gpt-5.5-mini`,
`openrouter:qwen/qwen3-235b-a22b` (OpenAI-compatible), `ollama:qwen3:32b`.
Keys come from a key file or from environment variables. Anthropic models read
IOULAB_ANTHROPIC_API_KEY and call the public API (or IOULAB_ANTHROPIC_BASE_URL if set), so the
experiments never pick up other ANTHROPIC_* settings from the environment.
"""

from __future__ import annotations

import os
import re
from typing import Any

from langchain.chat_models import init_chat_model


def make_model(spec: str, temperature: float = 0.0, max_tokens: int = 1024) -> Any:
    provider, _, model = spec.partition(":")
    if provider == "openrouter":
        return init_chat_model(model, model_provider="openai", temperature=temperature, max_tokens=max_tokens,
                               base_url="https://openrouter.ai/api/v1",
                               api_key=os.environ.get("OPENROUTER_API_KEY"), use_responses_api=False)
    if provider == "openai":
        return init_chat_model(model, model_provider="openai", temperature=temperature, max_tokens=max_tokens,
                               use_responses_api=False)
    if provider == "anthropic":
        key = anthropic_key()
        kw: dict[str, Any] = {"temperature": temperature, "max_tokens": max_tokens}
        if _always_thinks(model):
            # 5.x models reject a temperature setting and spend output tokens on thinking first
            kw = {"max_tokens": max(max_tokens, 8192)}
        return init_chat_model(model, model_provider="anthropic", api_key=key, max_retries=6,
                               base_url=os.environ.get("IOULAB_ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                               **kw)
    if provider in ("google", "google_genai", "gemini"):
        # A client-side rate limit; the SDK retries 429s with backoff and the runner pauses if
        # they persist.
        from langchain_core.rate_limiters import InMemoryRateLimiter
        rps = float(os.environ.get("IOULAB_GEMINI_RPS", "0.12"))     # about 7 requests a minute
        return init_chat_model(model, model_provider="google_genai", api_key=gemini_key(),
                               temperature=temperature, max_tokens=max(max_tokens, 8192), max_retries=6,
                               rate_limiter=InMemoryRateLimiter(requests_per_second=rps, max_bucket_size=1))
    return init_chat_model(model, model_provider=provider, temperature=temperature, max_tokens=max_tokens)


GEMINI_KEY_FILE = os.path.expanduser(os.environ.get("IOULAB_GEMINI_API_KEY_FILE", "~/.config/ioulab/gemini_key"))


def gemini_key() -> str | None:
    """The Gemini experiment key, from a file outside the repo (wins) or IOULAB_GEMINI_API_KEY. Never logged."""
    try:
        with open(GEMINI_KEY_FILE) as f:
            k = f.read().strip()
        if k:
            return k
    except OSError:
        pass
    return os.environ.get("IOULAB_GEMINI_API_KEY")


def _always_thinks(model: str) -> bool:
    """Claude 5.x models: thinking is always on and sampling parameters are rejected."""
    return bool(re.match(r"claude-(fable|mythos|(opus|sonnet|haiku)-5)", model))


def text_of(content: Any) -> str:
    """The visible text of a model reply. Thinking models return a list of blocks."""
    content = getattr(content, "content", content)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("text", "") if isinstance(c, dict) and c.get("type", "text") == "text"
                       else (c if isinstance(c, str) else "") for c in content)
    return str(content)


KEY_FILE = os.path.expanduser(os.environ.get("IOULAB_ANTHROPIC_API_KEY_FILE", "~/.config/ioulab/anthropic_key"))


def anthropic_key() -> str:
    """The experiment key: a key file wins over the environment, so a replacement key can be
    dropped in between a pause and a resume. Never logged."""
    try:
        with open(KEY_FILE) as f:
            k = f.read().strip()
        if k:
            return k
    except OSError:
        pass
    return os.environ.get("IOULAB_ANTHROPIC_API_KEY", "missing-api-key")
