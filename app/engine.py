"""Dialog engine: one `handle()` call = one conversational turn. Pure Python, no I/O."""
from __future__ import annotations

import random
import re
import time
from typing import Optional

from . import curriculum as cur
from .detect import (BOT_QUESTIONS, LEARN_WORDS, LOW_EFFORT, YES, detect_emotion, detect_mode,
                     detect_safety, has_intent, is_no, is_yes)
from .models import Exercise, Mode, Profile, Reply

FEELING_OPTIONS = ["😊 Happy", "😢 Sad", "😠 Angry", "😴 Tired"]
SUPPORT_OPTIONS = ["Breathe with me 🌬️", "Play a game 🎮", "Keep learning 📚"]
LEARN_OFFER = ["Yes! 👍", "Not now"]

PRAISE = [
    "Great job, {n}! You tried so hard! 🌟",
    "Yes! I love how you kept trying, {n}! 💪",
    "Super, {n}! Your brain is growing! 🧠",
    "You did it, {n}! Be proud! 🎉",
    "Wow, {n}! Look at you learn! 🌈",
]
ENCOURAGE = [
    "Good try, {n}! Mistakes help our brains grow. 🧠",
    "Nice try, {n}! Let's look again. 👀",
    "Almost, {n}! You are brave to try. 💪",
]
CURIOUS = [
    "Ooh, tell me more! What is your favorite animal? 🐾",
    "That is interesting! What do you see around you? 👀",
    "I wonder... what makes you happy? 😊",
    "Cool! What is your favorite color? 🎨",
]
FEELINGS = {  # emotion -> (feeling word, emoji, validation, strategy)
    "sad": ("SAD", "😢", "It is okay to feel sad. I am here with you. 🤗", "A big hug for you!"),
    "angry": ("ANGRY", "😠", "It is okay to feel angry. Big feelings are normal.", "Let's cool down together."),
    "scared": ("SCARED", "😨", "You are safe here. It is okay to feel scared.", "I am right here with you."),
    "tired": ("TIRED", "😴", "Our bodies need rest sometimes.", "We can take it slow."),
    "frustrated": ("STUCK", "😤", "That one is tricky! Hard things make our brains strong.", "We can go step by step."),
}
RIDDLES = [
    ("I say meow. I like milk. What am I?", "cat", "🐱"),
    ("I say woof. I wag my tail. What am I?", "dog", "🐶"),
    ("I am big and yellow. I shine in the sky. What am I?", "sun", "☀️"),
    ("I live in water. I can swim. What am I?", "fish", "🐟"),
    ("I say moo. I give you milk. What am I?", "cow", "🐮"),
    ("I have wings. I can fly. What am I?", "bird", "🐦"),
]
MOVES = [
    ("Clap your hands 👏👏 Then say: clap!", "clap"),
    ("Jump up high 🦘 Then say: jump!", "jump"),
    ("Touch your nose 👃 Then say: nose!", "nose"),
    ("Wave your hand 👋 Then say: wave!", "wave"),
]
META = YES | {"learning", "keep", "learn", "again", "try"}


class Engine:
    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()

    # ------------------------------------------------------------------ entry
    def handle(self, p: Profile, text: str) -> Reply:
        text = (text or "").strip()[:200]
        p.last_seen = time.time()
        if not p.greeted:
            return self._greet(p)
        if not text and not p.awaiting_name:
            return self._resume(p)
        p.turn += 1
        if p.awaiting_name:
            return self._take_name(p, text)

        emotion = detect_emotion(text)
        safety = detect_safety(text)
        if p.pending and cur.check_answer(p.pending, text) != "wrong":
            emotion = None   # "sad" / "scared" as an *answer* to a feelings word is not a feeling
        p.low_engagement = p.low_engagement + 1 if cur.norm(text) in LOW_EFFORT else 0
        mode = detect_mode(p, text, emotion, safety)
        if mode != Mode.ENGAGEMENT and p.pending and p.pending.kind == "riddle":
            p.pending = None  # abandoned game

        was_recovering = p.recovering
        if mode == Mode.SUPPORT:
            reply = self._support(p, text, emotion, safety)
        elif mode == Mode.ENGAGEMENT:
            reply = self._engagement(p, text, emotion)
        elif mode == Mode.CONVERSATION:
            reply = self._conversation(p, text, emotion)
        else:
            reply = self._learning(p, text, emotion)

        if was_recovering and reply.mode != Mode.SUPPORT:
            p.recovering = False
            reply.text = f"I am glad you feel better, {self._n(p)}! 💛 " + reply.text
        reply.emotion = emotion
        p.mode = reply.mode
        p.record(reply.mode, text, emotion)
        return reply

    # ------------------------------------------------------------- onboarding
    def _greet(self, p: Profile) -> Reply:
        p.greeted, p.awaiting_name = True, True
        return Reply("Hello! I am Pip the parrot. 🦜 What is your name?", Mode.CONVERSATION)

    def _resume(self, p: Profile) -> Reply:
        """Returning child (page reload / new visit): welcome back, continue where we left off."""
        n = self._n(p)
        if p.pending:
            return Reply(f"Welcome back, {n}! 🦜 " + p.pending.prompt, Mode.LEARNING,
                         quick_replies=list(p.pending.options))
        return Reply(f"Welcome back, {n}! 🦜 You are on Level {p.level}. Ready to learn a new word?",
                     Mode.CONVERSATION, quick_replies=LEARN_OFFER)

    def _take_name(self, p: Profile, text: str) -> Reply:
        t = text.lower()
        m = re.search(r"(?:my name is|i am|i'm|im|it's|its|name's)\s+([a-z]+)", t)
        raw = m.group(1) if m else (re.findall(r"[a-z]+", t) or ["friend"])[0]
        p.name = raw.capitalize()[:20]
        p.awaiting_name = False
        return Reply(f"Nice to meet you, {p.name}! 🎉 How do you feel today?",
                     Mode.CONVERSATION, quick_replies=FEELING_OPTIONS)

    @staticmethod
    def _n(p: Profile) -> str:
        return p.name or "friend"

    # -------------------------------------------------------------- learning
    def _learning(self, p: Profile, text: str, emotion: Optional[str]) -> Reply:
        if p.pending and p.pending.kind == "riddle":
            p.pending = None
        if p.pending:
            return self._evaluate(p, text)
        pre = "Let's try something easy. " if p.recovering else ""
        return self._new_exercise(p, pre)

    def _new_exercise(self, p: Profile, pre: str = "") -> Reply:
        ex, intro = cur.next_exercise(p, self.rng)
        p.pending, p.attempts, p.chat_turns_in_row = ex, 0, 0
        return Reply(pre + intro + ex.prompt, Mode.LEARNING, quick_replies=list(ex.options))

    def _evaluate(self, p: Profile, text: str) -> Reply:
        ex, n = p.pending, self._n(p)
        res = cur.check_answer(ex, text)
        toks = set(cur.norm(text).split())
        if res == "wrong" and toks and toks <= META:   # "ok", "again", "keep learning" -> just re-ask
            return Reply(ex.prompt, Mode.LEARNING, quick_replies=list(ex.options))

        if res in ("correct", "close"):
            p.pending = None
            change = cur.record_result(p, ex, True)
            p.lessons_in_row += 1
            msg = self.rng.choice(PRAISE).format(n=n)
            if res == "close":
                msg = f"Yes, {ex.answers[0].upper()}! 🌟 Watch the spelling: {ex.answers[0].upper()}. "
            if change == "up":
                msg += f" ⭐ LEVEL UP! You are on Level {p.level} now!"
            elif p.level_correct and p.level_correct % 3 == 0:
                msg += " How do you feel? Proud? 😊"          # SEL: confidence reflection
            if p.lessons_in_row >= 4:                         # not-always-teaching: brain break
                return self._engagement(p, "", None, prefix=msg + " Time for a fun break! 🎈 ")
            nxt = self._new_exercise(p)
            nxt.text = msg + " " + nxt.text
            return nxt

        # wrong answer
        p.attempts += 1
        if p.attempts == 1:
            msg = self.rng.choice(ENCOURAGE).format(n=n) + f" Hint: {ex.hint}"
            return Reply(msg, Mode.LEARNING, quick_replies=list(ex.options))
        streak_before = p.wrong_streak
        p.pending = None
        change = cur.record_result(p, ex, False)
        msg = f"That's okay, {n}! It is {ex.answers[0].upper()}. We will practice it again soon. 💛"
        if change == "down" or streak_before + 1 >= 2:       # SEL check-in after repeated misses
            p.lessons_in_row = 0
            p.recovering = True
            extra = " Let's make it easier." if change == "down" else ""
            return Reply(msg + extra + " Learning can feel hard. What would you like?", Mode.SUPPORT,
                         quick_replies=SUPPORT_OPTIONS)
        nxt = self._new_exercise(p)
        nxt.text = msg + " " + nxt.text
        return nxt

    # --------------------------------------------------------------- support
    def _support(self, p: Profile, text: str, emotion: Optional[str], safety: bool) -> Reply:
        n, t = self._n(p), text.lower()
        p.lessons_in_row = 0
        p.recovering = True
        if safety:
            p.safety_flags += 1
            return Reply(f"I am here with you, {n}. 💛 Please tell a grown-up you trust right now, "
                         "like mom, dad, or your teacher. They can help you.", Mode.SUPPORT,
                         quick_replies=["OK"])
        if "breathe" in t:
            return Reply("Let's breathe together. 🌸 Smell the flower... breathe IN, 1, 2, 3. "
                         "🕯️ Blow the candle... breathe OUT, 1, 2, 3. One more time! "
                         "How do you feel now?", Mode.SUPPORT, quick_replies=["😊 Better", "😢 Still sad"])
        word, emoji, validate, strat = FEELINGS.get(emotion or "sad")
        msg = f"{word} {emoji} is a feeling word. {validate} {strat}"
        opts = SUPPORT_OPTIONS
        if emotion == "tired":
            opts = ["Play a game 🎮", "Bye for now 👋"]
        if emotion == "frustrated" and p.pending:
            msg += f" Hint: {p.pending.hint}"
            opts = ["Keep learning 📚", "Play a game 🎮", "Breathe with me 🌬️"]
        return Reply(msg, Mode.SUPPORT, quick_replies=opts)

    # ------------------------------------------------------------ engagement
    def _engagement(self, p: Profile, text: str, emotion: Optional[str], prefix: str = "") -> Reply:
        n = self._n(p)
        if p.pending and p.pending.kind == "riddle":          # answering a game
            ex, res = p.pending, cur.check_answer(p.pending, text)
            if res != "wrong":
                p.pending = None
                p.word_correct[ex.word] = p.word_correct.get(ex.word, 0) + 1
                return Reply(f"Yes! {ex.word.upper()}! 🎉 {self.rng.choice(PRAISE).format(n=n)}",
                             Mode.ENGAGEMENT, quick_replies=["Another game 🎲", "Learn 📚"])
            p.attempts += 1
            if p.attempts < 2:
                return Reply(f"Good thinking, {n}! Try again. Hint: {ex.hint}", Mode.ENGAGEMENT,
                             quick_replies=list(ex.options))
            p.pending = None
            return Reply(f"It is {ex.word.upper()}! 😄 Good try! Want another game?", Mode.ENGAGEMENT,
                         quick_replies=["Another game 🎲", "Learn 📚"])

        p.lessons_in_row, p.attempts, p.chat_turns_in_row = 0, 0, 0
        if p.low_engagement >= 3:
            prefix += f"Are you sleepy, {n}? That is okay! Let's play. "
            p.low_engagement = 0
        elif emotion == "bored":
            prefix += f"Feeling bored is okay, {n}! Let's make it fun. "
        if self.rng.random() < 0.6:
            q, a, emoji = self.rng.choice(RIDDLES)
            other = self.rng.choice([r[1] for r in RIDDLES if r[1] != a])
            opts = [a, other]
            self.rng.shuffle(opts)
            p.pending = Exercise("riddle", a, f"Riddle time! {emoji} {q}", [a], opts, f"It starts with '{a[0]}'.")
        else:
            q, a = self.rng.choice(MOVES)
            p.pending = Exercise("riddle", a, f"Let's move! {q}", [a], [a], f"Say: {a}")
        return Reply(prefix + p.pending.prompt, Mode.ENGAGEMENT, quick_replies=list(p.pending.options))

    # ---------------------------------------------------------- conversation
    def _conversation(self, p: Profile, text: str, emotion: Optional[str]) -> Reply:
        n, t = self._n(p), text.lower().strip()
        p.chat_turns_in_row += 1
        suffix, quick, llm, hint = "", [], False, ""

        if is_no(t) and ("bye" in t or "stop" in t):
            return Reply(f"Bye bye, {n}! 👋 You did great today. See you soon! 🦜", Mode.CONVERSATION)
        if is_no(t):
            p.chat_turns_in_row = 0
            return Reply(f"OK, {n}! We can just talk. What do you like? 😊", Mode.CONVERSATION)

        m = re.search(r"\bi (?:like|love) (?:the |a |to )?([a-z]+)", t)
        interest = None
        if m:
            w = m.group(1)
            for cand in (w, w.rstrip("s")):
                if cand in cur.WORD:
                    interest = cand
                    break
        if interest:
            word, emoji, cat, _ = cur.WORD[interest]
            for i in (word, cat):
                if i not in p.interests:
                    p.interests.append(i)
            body = f"{word.upper()} {emoji}! I like {word}s too!"
        elif t in {"hi", "hello", "hey", "hiya", "yo"}:
            body = f"Hello again, {n}! 👋 I am happy to see you."
        elif "your name" in t or "who are you" in t:
            body = "I am Pip the parrot! 🦜 I love to play and learn words."
        elif "how are you" in t:
            body = "I am happy today! 😊 Thank you for asking. That is kind!"
        elif emotion in ("happy", "proud"):
            body = f"That is wonderful, {n}! 😊 HAPPY is an English word. Happy!"
        elif p.pending and p.pending.kind != "riddle":
            body = ""
        else:
            body, llm, hint = self.rng.choice(CURIOUS), True, text

        if p.pending and p.pending.kind != "riddle" and not interest:
            suffix = "Now, back to our game: " + p.pending.prompt
            quick = list(p.pending.options)
        elif p.chat_turns_in_row >= 2 or (not body):
            suffix, quick = "Do you want to learn a new word? 📚", LEARN_OFFER
        return Reply(body, Mode.CONVERSATION, quick_replies=quick, suffix=suffix,
                     llm_eligible=llm, llm_hint=hint)
