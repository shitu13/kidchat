"""Optional LLM enhancer for *free-form chat only*.

The lesson/SEL/mode logic never waits on an LLM. If ANTHROPIC_API_KEY is set, free chat
turns get one short LLM call with a hard timeout; on any failure we keep the template reply,
so latency stays bounded (timeout 1.0 s + engine < 5 ms + network).
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from .models import Profile

API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
TIMEOUT = float(os.getenv("LLM_TIMEOUT_SECONDS", "1.0"))
ENABLED = bool(API_KEY)

SYSTEM = (
    "You are Pip, a friendly parrot who chats with a child aged 4-6 who is learning English. "
    "Reply in at most 2 very short, simple sentences (max 12 words each), using words a 5-year-old knows. "
    "Be warm and curious. Never ask for personal details (address, school, phone). "
    "Never discuss scary, violent or adult topics - gently change the subject to animals, colors or feelings. "
    "Use at most one emoji. Do not ask more than one question."
)

_client: Optional[httpx.AsyncClient] = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:   # one pooled connection => no TLS handshake on the hot path
        _client = httpx.AsyncClient(timeout=TIMEOUT, headers={
            "x-api-key": API_KEY or "", "anthropic-version": "2023-06-01", "content-type": "application/json"})
    return _client


async def chat_reply(p: Profile, child_text: str) -> Optional[str]:
    if not ENABLED:
        return None
    ctx = f"Child's name: {p.name or 'unknown'}. Level {p.level}. Likes: {', '.join(p.interests) or 'unknown'}."
    try:
        r = await client().post("https://api.anthropic.com/v1/messages", json={
            "model": MODEL, "max_tokens": 60, "system": SYSTEM + " " + ctx,
            "messages": [{"role": "user", "content": child_text[:200]}]})
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
        return text if 0 < len(text) <= 200 else None
    except Exception:
        return None   # timeout / network / quota -> caller uses template reply
