"""Curriculum (L1-L3), exercise generation, answer checking and progression rules."""
from __future__ import annotations

import random
import re
from typing import Optional

from .models import Exercise, Profile

# (word, emoji, category, level)
WORDS = [
    # ---- Level 1: first words, sounds, single-word recognition ----
    ("cat", "🐱", "animals", 1), ("dog", "🐶", "animals", 1), ("sun", "☀️", "nature", 1),
    ("ball", "⚽", "toys", 1), ("apple", "🍎", "food", 1), ("red", "🔴", "colors", 1),
    ("blue", "🔵", "colors", 1), ("one", "1️⃣", "numbers", 1), ("two", "2️⃣", "numbers", 1),
    ("happy", "😊", "feelings", 1), ("sad", "😢", "feelings", 1), ("hello", "👋", "greetings", 1),
    # ---- Level 2: more nouns, naming, letters / spelling ----
    ("bird", "🐦", "animals", 2), ("fish", "🐟", "animals", 2), ("cow", "🐮", "animals", 2),
    ("car", "🚗", "toys", 2), ("book", "📖", "things", 2), ("tree", "🌳", "nature", 2),
    ("star", "⭐", "nature", 2), ("milk", "🥛", "food", 2), ("green", "🟢", "colors", 2),
    ("yellow", "🟡", "colors", 2), ("three", "3️⃣", "numbers", 2), ("angry", "😠", "feelings", 2),
    ("scared", "😨", "feelings", 2), ("hat", "🎩", "things", 2),
]
WORD = {w[0]: w for w in WORDS}

# Level 3: short sentences with one blank. (sentence, answer, options)
SENTENCES = [
    ("The 🐱 says ___ .", "meow", ["meow", "woof"]),
    ("The 🐶 says ___ .", "woof", ["woof", "moo"]),
    ("The 🐮 says ___ .", "moo", ["moo", "meow"]),
    ("I ___ an 🍎 .", "eat", ["eat", "run"]),
    ("The ☀️ is ___ .", "hot", ["hot", "cold"]),
    ("The 🐦 can ___ .", "fly", ["fly", "swim"]),
    ("The 🐟 can ___ .", "swim", ["swim", "fly"]),
    ("I am ___ 😊 .", "happy", ["happy", "sad"]),
    ("I feel ___ 😢 .", "sad", ["sad", "happy"]),
    ("I read a ___ 📖 .", "book", ["book", "ball"]),
    ("I kick the ___ ⚽ .", "ball", ["ball", "book"]),
    ("I drink ___ 🥛 .", "milk", ["milk", "star"]),
]

LEVEL_UP_CORRECT = 5       # correct answers needed at a level ...
LEVEL_UP_ACCURACY = 0.8    # ... with this accuracy over the last 6 answers
LEVEL_DOWN_WRONG = 3       # consecutive misses before stepping down


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9' ]", " ", text.lower()).strip()


def _lev1(a: str, b: str) -> bool:
    """True if edit distance(a, b) <= 1 (typo tolerance for emerging spellers)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    s, l = sorted((a, b), key=len)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def check_answer(ex: Exercise, text: str) -> str:
    """Return 'correct', 'close' (typo accepted) or 'wrong'."""
    toks = norm(text).split()
    if not toks:
        return "wrong"
    for ans in ex.answers:
        if ans in toks or ans == " ".join(toks):
            return "correct"
    for ans in ex.answers:
        if len(ans) >= 4 and any(_lev1(ans, t) for t in toks):
            return "close"
    return "wrong"


def _pool(p: Profile) -> list[tuple]:
    return [w for w in WORDS if w[3] <= p.level]


def next_exercise(p: Profile, rng: random.Random) -> tuple[Exercise, str]:
    """Pick the next exercise. Returns (exercise, intro). Context-aware: reviews weak words,
    prefers new words, and leans toward the child's interests."""
    # Level 3 -> sentence completion (with 25% review of single words)
    if p.level >= 3 and rng.random() < 0.75:
        pool = [s for s in SENTENCES if s[1] not in p.mastered] or SENTENCES
        weak = [s for s in pool if s[1] in p.weak]
        s = rng.choice(weak) if weak and rng.random() < 0.4 else rng.choice(pool)
        ex = Exercise("cloze", s[1], f"Finish it: {s[0]}", [s[1]], s[2], f"It starts with '{s[1][0]}'.", 3)
        return ex, ""

    pool = _pool(p)
    weak = [w for w in pool if w[0] in p.weak]
    fresh = [w for w in pool if w[0] not in p.seen]
    liked = [w for w in (fresh or pool) if w[2] in p.interests or w[0] in p.interests]
    review = bool(weak) and rng.random() < 0.4
    if review:
        w = rng.choice(weak)
    elif liked and rng.random() < 0.6:
        w = rng.choice(liked)
    else:
        w = rng.choice(fresh or pool)
    word, emoji = w[0], w[1]
    first_time = word not in p.seen
    intro = ""
    if review:
        intro = f"Let's try {word.upper()} again - you can do it! "

    # level 1 -> hear it, then pick it
    if p.level == 1:
        if first_time:
            ex = Exercise("repeat", word, f"This is a {word.upper()} {emoji}. Can you say it? Say: {word}",
                          [word], [word], f"Say: {word}", 1)
        else:
            other = rng.choice([x for x in pool if x[0] != word])
            opts = [word, other[0]]
            rng.shuffle(opts)
            ex = Exercise("pick", word, f"Which one is {emoji} ?", [word], opts, f"It starts with '{word[0]}'.", 1)
        return ex, intro
    # level 2+ -> name it or fill the missing letter
    if rng.random() < 0.5 or len(word) < 3:
        other = rng.choice([x for x in pool if x[0] != word])
        opts = [word, other[0]]
        rng.shuffle(opts)
        ex = Exercise("name", word, f"What is this? {emoji}", [word], opts, f"It starts with '{word[0]}'.", 2)
    else:
        i = rng.randrange(1, len(word))
        blanked = word[:i] + "_" + word[i + 1:]
        ex = Exercise("spell", word, f"{emoji}  Which letter is missing?  {blanked.upper()}",
                      [word[i], word], [word[i]], f"The word is {word}.", 2)
    return ex, intro


def record_result(p: Profile, ex: Exercise, ok: bool) -> Optional[str]:
    """Update history/mastery. Returns 'up', 'down' or None when the level changes."""
    p.recent.append(ok)
    del p.recent[:-6]
    p.attempts = 0
    if ex.word not in p.seen:
        p.seen.append(ex.word)
    if ok:
        p.word_correct[ex.word] = p.word_correct.get(ex.word, 0) + 1
        p.level_correct += 1
        p.wrong_streak = 0
        if p.weak.get(ex.word, 0) > 0 and p.word_correct[ex.word] >= 2:
            p.weak.pop(ex.word, None)
        acc = sum(p.recent) / len(p.recent)
        if p.level < 3 and p.level_correct >= LEVEL_UP_CORRECT and acc >= LEVEL_UP_ACCURACY:
            p.level += 1
            p.level_correct = 0
            return "up"
    else:
        p.weak[ex.word] = p.weak.get(ex.word, 0) + 1
        p.wrong_streak += 1
        if p.wrong_streak >= LEVEL_DOWN_WRONG and p.level > 1:
            p.level -= 1
            p.level_correct = 0
            p.wrong_streak = 0
            return "down"
    return None
