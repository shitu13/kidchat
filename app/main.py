"""HTTP API. POST /api/chat is the only hot path."""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import llm
from .curriculum import LEVEL_UP_CORRECT
from .engine import Engine
from .models import Mode
from .store import ProfileStore

STATIC = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(title="Pip - English buddy for little learners", version="1.0")
engine = Engine()
store = ProfileStore(os.getenv("DATA_DIR"))


class ChatIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(default="", max_length=300)


class Progress(BaseModel):
    level: int
    level_correct: int
    level_target: int
    words_mastered: int


class ChatOut(BaseModel):
    reply: str
    mode: Mode
    emotion: str | None
    quick_replies: list[str]
    progress: Progress
    llm_used: bool
    latency_ms: float


@app.middleware("http")
async def timing(request: Request, call_next):
    t0 = time.perf_counter()
    resp = await call_next(request)
    resp.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
    return resp


@app.post("/api/chat", response_model=ChatOut)
async def chat(body: ChatIn) -> ChatOut:
    t0 = time.perf_counter()
    p = store.get(body.session_id)
    r = engine.handle(p, body.message)          # < 5 ms, pure CPU
    used = False
    if r.llm_eligible and llm.ENABLED:          # free-form chat only, hard-capped by LLM_TIMEOUT
        try:
            text = await asyncio.wait_for(llm.chat_reply(p, r.llm_hint), timeout=llm.TIMEOUT + 0.1)
        except asyncio.TimeoutError:
            text = None
        if text:
            r.text, used = text, True
    store.save(p)
    return ChatOut(
        reply=r.full_text, mode=r.mode, emotion=r.emotion, quick_replies=r.quick_replies,
        progress=Progress(level=p.level, level_correct=p.level_correct, level_target=LEVEL_UP_CORRECT,
                          words_mastered=len(p.mastered)),
        llm_used=used, latency_ms=round((time.perf_counter() - t0) * 1000, 1))


@app.get("/health")
async def health():
    return {"status": "ok", "llm": llm.ENABLED}


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
