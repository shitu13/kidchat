"""Emotion / safety detection and child-mode detection.

Rule-based on purpose: it runs in microseconds, is fully explainable, and never
sends a child's words to a third party just to decide what to do next.
"""
from __future__ import annotations

import re
from typing import Optional

from .models import Mode, Profile

# priority order matters: the first emotion with a hit wins
EMOTION_LEXICON: list[tuple[str, list[str]]] = [
    ("scared", ["scared", "afraid", "scary", "monster", "nightmare", "worried", "the dark"]),
    ("sad", ["sad", "cry", "crying", "cried", "lonely", "miss my", "unhappy", "upset"]),
    ("angry", ["angry", "mad", "hate", "grr", "hit him", "hit her", "kick"]),
    ("frustrated", ["too hard", "give up", "quit", "stupid", "dumb", "i can't", "i cant", "cant do"]),
    ("tired", ["tired", "sleepy", "sleep", "yawn", "exhausted"]),
    ("bored", ["bored", "boring", "boooring", "not fun", "nothing to do"]),
    ("proud", ["i did it", "i won", "proud"]),
    ("happy", ["happy", "yay", "yippee", "fun", "love", "great", "awesome", "excited", "wow", "good", "better"]),
]
SUPPORT_EMOTIONS = {"scared", "sad", "angry", "frustrated", "tired"}

# Words that mean "tell a trusted grown-up" - never handled by the bot alone.
SAFETY_PHRASES = ["hurt me", "hits me", "hit me", "nobody loves", "want to die", "hate myself",
                  "alone at home", "touched me", "afraid of my", "scared of my"]

GREETINGS = {"hi", "hello", "hey", "hiya", "yo", "good morning", "good night"}
YES = {"yes", "yeah", "yep", "yup", "ok", "okay", "sure", "ready", "next", "more", "again", "start", "please"}
NO = {"no", "nope", "not now", "later", "stop", "bye"}
PLAY_WORDS = {"game", "play", "joke", "riddle", "song", "story", "funny", "dance"}
LEARN_WORDS = {"learn", "lesson", "teach", "word", "words", "new word"}
BOT_QUESTIONS = ["who are you", "your name", "how are you", "are you real", "what do you like"]
LOW_EFFORT = {"", "idk", "...", "hmm", "um", "uh", "dunno", "?"}


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z']){re.escape(phrase)}(?![a-z'])", text) is not None


def detect_emotion(text: str) -> Optional[str]:
    t = text.lower()
    for emo, words in EMOTION_LEXICON:
        if any(_has(t, w) for w in words):
            # naive negation guard: "not happy" -> sad-ish, "not sad" -> neutral
            if emo == "happy" and re.search(r"\b(not|no|never)\s+(\w+\s+)?(" + "|".join(words[:6]) + r")\b", t):
                return "sad"
            if emo in SUPPORT_EMOTIONS and re.search(r"\b(not|no|never)\s+" + emo, t):
                return None
            return emo
    return None


def detect_safety(text: str) -> bool:
    t = text.lower()
    return any(p in t for p in SAFETY_PHRASES)


def has_intent(text: str, vocab: set[str]) -> bool:
    t = text.lower()
    return any(_has(t, w) for w in vocab)


def is_yes(text: str) -> bool:
    toks = set(re.findall(r"[a-z']+", text.lower()))
    return bool(toks & YES)


def is_no(text: str) -> bool:
    t = text.lower().strip()
    return any(_has(t, w) for w in NO)


def detect_mode(p: Profile, text: str, emotion: Optional[str], safety: bool) -> Mode:
    """Decide which of the four modes this turn belongs to.

    Order encodes priorities: child wellbeing > explicit request > lesson flow > chat.
    """
    t = text.lower().strip()
    # 1. Wellbeing always comes first.
    if safety or emotion in SUPPORT_EMOTIONS:
        return Mode.SUPPORT
    if "breathe" in t:
        return Mode.SUPPORT
    # 2. Engagement signals: bored, asks to play, or disengaged for 3 turns.
    if emotion == "bored" or has_intent(t, PLAY_WORDS) or p.low_engagement >= 3:
        return Mode.ENGAGEMENT
    # 3. A riddle/game answer in flight stays in engagement.
    if p.pending and p.pending.kind == "riddle" and not has_intent(t, LEARN_WORDS) and not is_no(t):
        return Mode.ENGAGEMENT
    # 4. Explicit "teach me".
    if has_intent(t, LEARN_WORDS):
        return Mode.LEARNING
    # 5. Child is asking about the bot / greeting -> chat, even mid-lesson (lesson stays pending).
    if any(q in t for q in BOT_QUESTIONS) or t in GREETINGS:
        return Mode.CONVERSATION
    # 5b. "no / not now / stop / bye" is always respected.
    if is_no(t):
        return Mode.CONVERSATION
    # 6. A lesson is waiting for an answer.
    if p.pending:
        return Mode.LEARNING
    # 7. Too many lessons in a row -> brain break instead of another drill.
    if p.lessons_in_row >= 4:
        return Mode.ENGAGEMENT
    # 8. Agreeing to learn.
    if is_yes(t) and p.chat_turns_in_row >= 1:
        return Mode.LEARNING
    if is_yes(t) and p.turn > 2:
        return Mode.LEARNING
    # 9. Sharing / chatting: keep chatting for up to 2 turns, then offer a lesson.
    if p.chat_turns_in_row < 2 and t:
        return Mode.CONVERSATION
    return Mode.LEARNING
