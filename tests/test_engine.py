import random
import time
import unittest

from app.curriculum import check_answer
from app.detect import detect_emotion, detect_safety
from app.engine import Engine
from app.models import Exercise, Mode, Profile


def start(seed=1):
    e, p = Engine(random.Random(seed)), Profile("t")
    e.handle(p, "")                 # greeting
    e.handle(p, "my name is Mia")   # name
    return e, p


def answer(p):
    ex = p.pending
    return ex.answers[-1] if ex.kind == "spell" else ex.answers[0]


class Onboarding(unittest.TestCase):
    def test_greets_and_stores_name(self):
        e, p = start()
        self.assertEqual(p.name, "Mia")


class Modes(unittest.TestCase):
    def test_four_modes_reachable(self):
        e, p = start()
        self.assertEqual(e.handle(p, "i like dogs").mode, Mode.CONVERSATION)
        self.assertEqual(e.handle(p, "i am sad").mode, Mode.SUPPORT)
        self.assertEqual(e.handle(p, "can we play a game").mode, Mode.ENGAGEMENT)
        self.assertEqual(e.handle(p, "learn").mode, Mode.LEARNING)

    def test_not_always_teaching(self):
        e, p = start()
        modes = [e.handle(p, "my dog is big").mode, e.handle(p, "i had fun today").mode]
        self.assertTrue(all(m == Mode.CONVERSATION for m in modes))
        self.assertIsNone(p.pending)

    def test_brain_break_after_four_lessons(self):
        e, p = start()
        e.handle(p, "learn")
        modes = []
        for _ in range(6):
            modes.append(e.handle(p, answer(p)).mode)
            if modes[-1] == Mode.ENGAGEMENT:
                break
        self.assertIn(Mode.ENGAGEMENT, modes)

    def test_bored_goes_to_engagement(self):
        e, p = start()
        self.assertEqual(e.handle(p, "this is boring").mode, Mode.ENGAGEMENT)

    def test_no_is_respected(self):
        e, p = start()
        e.handle(p, "hello")
        r = e.handle(p, "not now")
        self.assertEqual(r.mode, Mode.CONVERSATION)
        self.assertIsNone(p.pending)


class Learning(unittest.TestCase):
    def test_level_up_and_never_above_3(self):
        e, p = start()
        e.handle(p, "learn")
        for _ in range(60):
            r = e.handle(p, answer(p) if p.pending and p.pending.kind != "riddle" else "learn")
        self.assertEqual(p.level, 3)

    def test_level_down_after_misses(self):
        e, p = start()
        p.level = 2
        e.handle(p, "learn")
        for _ in range(8):
            if p.pending and p.pending.kind != "riddle":
                e.handle(p, "zzz"); e.handle(p, "zzz")
            else:
                e.handle(p, "learn")
        self.assertEqual(p.level, 1)

    def test_hint_then_reveal(self):
        e, p = start()
        e.handle(p, "learn")
        w = p.pending.word
        r1 = e.handle(p, "banana")
        self.assertIn("Hint", r1.text)
        r2 = e.handle(p, "banana")
        self.assertIn(w.upper(), r2.text)
        self.assertIn(w, p.weak)

    def test_weak_words_reviewed_later(self):
        e, p = start()
        p.weak["cat"] = 1
        seen = {e.handle(p, "learn").text for _ in range(1)}
        # review happens with 40% probability per pick - check it is reachable
        hits = 0
        for s in range(200):
            q = Profile("x"); q.weak = {"cat": 1}; q.seen = ["dog"]
            ex, _ = __import__("app.curriculum", fromlist=["x"]).next_exercise(q, random.Random(s))
            hits += ex.word == "cat"
        self.assertGreater(hits, 20)

    def test_typo_tolerance(self):
        ex = Exercise("name", "apple", "?", ["apple"])
        self.assertEqual(check_answer(ex, "aple"), "close")
        self.assertEqual(check_answer(ex, "an apple"), "correct")
        self.assertEqual(check_answer(ex, "dog"), "wrong")


class SEL(unittest.TestCase):
    def test_emotions(self):
        for text, emo in [("i am sad", "sad"), ("i am scared", "scared"), ("im so mad", "angry"),
                          ("this is too hard", "frustrated"), ("yay i love it", "happy"),
                          ("i am not sad", None)]:
            self.assertEqual(detect_emotion(text), emo, text)

    def test_support_teaches_feeling_word_and_offers_choices(self):
        e, p = start()
        r = e.handle(p, "i feel sad")
        self.assertEqual(r.mode, Mode.SUPPORT)
        self.assertIn("SAD", r.text)
        self.assertTrue(r.quick_replies)

    def test_breathing(self):
        e, p = start()
        r = e.handle(p, "Breathe with me")
        self.assertIn("breathe", r.text.lower())

    def test_safety_routes_to_grown_up(self):
        self.assertTrue(detect_safety("someone hits me"))
        e, p = start()
        r = e.handle(p, "someone hits me")
        self.assertIn("grown-up", r.text)
        self.assertEqual(p.safety_flags, 1)

    def test_recovery_is_acknowledged(self):
        e, p = start()
        e.handle(p, "i am sad")
        r = e.handle(p, "i like cats")
        self.assertIn("glad you feel better", r.text)


class Context(unittest.TestCase):
    def test_interest_shapes_content(self):
        e, p = start()
        e.handle(p, "i like dogs")
        self.assertIn("animals", p.interests)

    def test_profile_roundtrip(self):
        e, p = start()
        e.handle(p, "learn")
        q = Profile.from_dict(p.to_dict())
        self.assertEqual(q.pending.word, p.pending.word)
        self.assertEqual(q.mode, p.mode)


class Performance(unittest.TestCase):
    def test_engine_turn_is_fast(self):
        e, p = start()
        t = time.perf_counter()
        for i in range(500):
            e.handle(p, "learn" if i % 7 else "i am sad")
        per_turn_ms = (time.perf_counter() - t) * 1000 / 500
        self.assertLess(per_turn_ms, 5)


if __name__ == "__main__":
    unittest.main()
