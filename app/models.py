"""Core data models: modes, exercises, and the per-child profile (learning memory)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Mode(str, Enum):
    LEARNING = "learning"
    CONVERSATION = "conversation"
    ENGAGEMENT = "engagement"
    SUPPORT = "support"


@dataclass
class Exercise:
    kind: str                       # repeat | pick | name | spell | cloze | riddle
    word: str                       # target word (key for mastery tracking)
    prompt: str
    answers: list[str]              # accepted answers (lower case)
    options: list[str] = field(default_factory=list)  # tap-able choices
    hint: str = ""
    level: int = 1

    @staticmethod
    def from_dict(d: Optional[dict]) -> Optional["Exercise"]:
        return Exercise(**d) if d else None


@dataclass
class Profile:
    """Everything the bot remembers about one child. Small (<2 KB) so it is cheap to load/save."""
    session_id: str
    name: Optional[str] = None
    level: int = 1
    mode: Mode = Mode.CONVERSATION
    turn: int = 0

    # dialogue state
    greeted: bool = False
    awaiting_name: bool = False
    pending: Optional[Exercise] = None
    attempts: int = 0                 # attempts on the pending exercise
    lessons_in_row: int = 0           # exercises done since last break
    chat_turns_in_row: int = 0        # free-chat turns since last lesson offer
    low_engagement: int = 0           # consecutive empty / "idk" style replies
    recovering: bool = False          # just came out of SUPPORT mode

    # learning history
    recent: list[bool] = field(default_factory=list)       # last 6 results
    level_correct: int = 0                                  # correct answers at this level
    wrong_streak: int = 0
    word_correct: dict[str, int] = field(default_factory=dict)
    weak: dict[str, int] = field(default_factory=dict)      # word -> times missed
    seen: list[str] = field(default_factory=list)

    # personal / emotional context
    interests: list[str] = field(default_factory=list)
    last_emotion: Optional[str] = None
    emotion_log: list[str] = field(default_factory=list)    # last 10
    history: list[dict] = field(default_factory=list)       # last 10 turns
    safety_flags: int = 0

    last_seen: float = field(default_factory=time.time)

    # ---- helpers -------------------------------------------------
    @property
    def mastered(self) -> set[str]:
        return {w for w, n in self.word_correct.items() if n >= 2}

    def record(self, mode: Mode, user: str, emotion: Optional[str]) -> None:
        self.history.append({"t": self.turn, "mode": mode.value, "user": user[:80], "emotion": emotion})
        del self.history[:-10]
        if emotion:
            self.emotion_log.append(emotion)
            del self.emotion_log[:-10]
            self.last_emotion = emotion

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode"] = self.mode.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "Profile":
        d = dict(d)
        d["mode"] = Mode(d.get("mode", "conversation"))
        d["pending"] = Exercise.from_dict(d.get("pending"))
        return Profile(**d)


@dataclass
class Reply:
    text: str
    mode: Mode
    emotion: Optional[str] = None
    quick_replies: list[str] = field(default_factory=list)
    suffix: str = ""                  # appended after (optional) LLM text, e.g. a lesson nudge
    llm_eligible: bool = False        # free-form chat the optional LLM may rephrase
    llm_hint: str = ""                # what the LLM should talk about

    @property
    def full_text(self) -> str:
        return (self.text + (" " + self.suffix if self.suffix else "")).strip()
