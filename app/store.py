"""Profile store: in-memory cache with TTL + optional write-through JSON persistence.

Interface (get / save) is deliberately tiny so it can be swapped for Redis or Postgres
without touching the engine. See DESIGN.md "Scaling".
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

from .models import Profile

TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 6)))
MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "5000"))


class ProfileStore:
    def __init__(self, data_dir: Optional[str] = None):
        self._mem: dict[str, Profile] = {}
        self._lock = threading.Lock()
        self._dir = Path(data_dir) if data_dir else None
        if self._dir:
            self._dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe(sid: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "", sid)[:64] or "anon"

    def get(self, sid: str) -> Profile:
        sid = self._safe(sid)
        with self._lock:
            p = self._mem.get(sid)
            if p is None and self._dir and (self._dir / f"{sid}.json").exists():
                try:
                    p = Profile.from_dict(json.loads((self._dir / f"{sid}.json").read_text()))
                except Exception:
                    p = None
            if p is None:
                p = Profile(session_id=sid)
            self._mem[sid] = p
            self._evict()
            return p

    def save(self, p: Profile) -> None:
        if self._dir:   # tiny file (<2 KB); write is ~0.1 ms
            tmp = self._dir / f"{p.session_id}.json.tmp"
            tmp.write_text(json.dumps(p.to_dict()))
            tmp.replace(self._dir / f"{p.session_id}.json")

    def _evict(self) -> None:
        if len(self._mem) <= MAX_SESSIONS:
            return
        cutoff = time.time() - TTL_SECONDS
        for k in [k for k, v in self._mem.items() if v.last_seen < cutoff] or list(self._mem)[:100]:
            self._mem.pop(k, None)
