import os
import random
import re
import unittest
from unittest.mock import patch

import push_shit as ps
from tests.support import RepoCase


def normalized(text):
    return re.sub(r"[\W_]+", "", text.casefold())


class VarietyTests(RepoCase):
    voice = "I catalogued that TODO; this repository never forgets its unfinished work."

    def setUp(self):
        super().setUp()
        self.cfg = {"lang": "en", "haunt_count": 0, "lifetime_hauntings": 0,
                    "probability": 1, "diary_path": None}
        ps.save_config(str(self.repo), self.cfg)
        self.sins = ps.collect_sins(str(self.repo), self.git("rev-parse", "HEAD"), ps.ZERO_SHA)

    def remember(self, message, **extra):
        ps.ledger_append(str(self.repo), {"type": "whisper", "file": "src/app.py",
                                        "line": "# 💩 " + message, "silent": False, **extra})

    def plant(self, cfg=None):
        with patch.object(ps, "server_alive", return_value=True):
            return ps.plant_whisper(str(self.repo), cfg or self.cfg, self.sins, random.Random(7))

    def test_successive_real_planting_commits_do_not_repeat_the_model(self):
        values = []
        with patch.object(ps, "server_alive", return_value=True), \
                patch.object(ps, "llm_chat", return_value=self.voice):
            for number in range(2):
                cfg = ps.load_config(str(self.repo))
                assert cfg is not None
                result = ps._perform_haunting(str(self.repo), cfg, self.sins, random.Random(number))
                assert result is not None
                whisper = result["whisper_result"]
                assert whisper is not None
                values.append(whisper["text"])
        self.assertNotEqual(normalized(values[0]), normalized(values[1]))
        rows = [r for r in ps.ledger_read(str(self.repo)) if r["type"] == "whisper"]
        self.assertEqual(rows[0].get("source"), "model")
        self.assertEqual(rows[1].get("source"), "template")
        self.assertEqual(rows[0].get("language"), "en")

    def test_punctuation_case_and_exorcised_legacy_history_are_respected(self):
        self.remember(self.voice, exorcised=True)
        candidate = self.voice.upper().replace(";", " ... ")
        with patch.object(ps, "llm_chat", return_value=candidate):
            result = self.plant()
        assert result is not None
        self.assertNotEqual(normalized(result["text"]), normalized(self.voice))

    def test_near_duplicate_is_rejected_not_just_exact_text(self):
        self.remember(self.voice)
        candidate = "I catalogued that TODO; this repository will never forget unfinished work."
        with patch.object(ps, "llm_chat", return_value=candidate):
            result = self.plant()
        assert result is not None
        self.assertNotEqual(result["text"], candidate)

    def test_appending_new_prose_does_not_hide_a_copied_previous_line(self):
        self.remember(self.voice)
        candidate = self.voice + " I also kept a separate handover receipt for whoever reads the next review."
        self.assertLessEqual(len(candidate), 180)
        with patch.object(ps, "llm_chat", return_value=candidate):
            result = self.plant()
        assert result is not None
        self.assertNotEqual(result["text"], candidate)

    def test_long_ramble_is_rejected_not_truncated_into_a_duplicate(self):
        candidate = "I retained the review evidence and will not accept another excuse. " * 5
        with patch.object(ps, "llm_chat", return_value=candidate):
            result = self.plant()
        assert result is not None
        self.assertNotEqual(result["text"], candidate)
        self.assertEqual(result["entry"].get("source"), "template")

    def test_model_preface_is_not_a_usable_ghost_comment(self):
        candidate = "Okay, here's a ghost comment, delivered with maximum disdain:"
        with patch.object(ps, "llm_chat", return_value=candidate):
            result = self.plant()
        assert result is not None
        self.assertNotEqual(result["text"], candidate)

    def test_prompt_does_not_feed_back_full_previous_prose_as_an_example(self):
        self.remember(self.voice, theme="handover", fact="todo")
        candidate = "The handover checklist has teeth now; I am the one holding it."
        with patch.object(ps, "llm_chat", return_value=candidate) as chat:
            self.plant()
        self.assertNotIn(self.voice, chat.call_args.args[1])
        self.assertIn("Speech act:", chat.call_args.args[1])

    def test_mixed_language_is_a_system_constraint_not_just_a_hint(self):
        candidate = "我把这轮记录留在交接桌上；The receipt stays open."
        with patch.object(ps, "llm_chat", return_value=candidate) as chat:
            self.plant({**self.cfg, "lang": "mixed"})
        systems = [call.args[0] for call in chat.call_args_list]
        self.assertTrue(any("中文" in system for system in systems))
        self.assertTrue(any("English" in system for system in systems))

    def test_repository_data_does_not_remove_substrings_from_english_words(self):
        cases = [
            ("交接还没结束；I am still here.", {"files": ["src/a"]}),
            ("交接还没结束；It fixed our case.", {"bad_commits": ["fix"]}),
        ]
        for text, sins in cases:
            with self.subTest(text=text):
                self.assertTrue(ps._voice_language_ok(text, "mixed", sins))

    def test_composition_does_not_accept_code_markers_as_its_english_part(self):
        chinese = "我把这轮交接记录封存，别让文件名替决定签字。"
        english = "I kept the original review receipt."
        with patch.object(ps, "llm_chat", side_effect=[chinese, "TODO FIXME HACK XXX", english]) as chat:
            result = self.plant({**self.cfg, "lang": "mixed"})
        assert result is not None
        self.assertEqual(chat.call_count, 3)
        self.assertEqual(result["entry"].get("source"), "model")
        self.assertNotIn("FIXME", result["text"])
        self.assertIn(english, result["text"])
        self.assertTrue(ps._voice_language_ok(result["text"], "mixed", self.sins))

    def test_mixed_can_compose_two_genuine_monolingual_model_clauses(self):
        chinese = "我把这轮交接记录封存，别让文件名替决定签字。"
        english = "I kept the original review receipt."
        calls = [0]

        def reply(*_args, **_kwargs):
            calls[0] += 1
            return chinese if calls[0] == 1 else english

        with patch.object(ps, "llm_chat", side_effect=reply) as chat:
            result = self.plant({**self.cfg, "lang": "mixed"})
        assert result is not None
        self.assertEqual(result["entry"].get("source"), "model")
        self.assertEqual(chat.call_count, 2)
        self.assertIn(chinese.rstrip("。"), result["text"])
        self.assertIn(english, result["text"])

    def test_directory_labels_do_not_masquerade_as_natural_english(self):
        candidate = "增加了注释行，似乎在 archive/renames 目录下。"
        with patch.object(ps, "llm_chat", return_value=candidate):
            result = self.plant({**self.cfg, "lang": "mixed"})
        assert result is not None
        self.assertNotEqual(result["text"], candidate)
        self.assertEqual(result["entry"].get("source"), "template")

    def test_internal_theme_labels_cannot_be_invented_as_repository_paths(self):
        candidate = "增加了注释行，似乎在 archive/renames 目录下。"
        with patch.object(ps, "llm_chat", return_value=candidate):
            result = self.plant({**self.cfg, "lang": "zh"})
        assert result is not None
        self.assertNotEqual(result["text"], candidate)
        self.assertIn("unverified-path", result["entry"]["rejections"])

    def test_known_paths_allow_adjacent_chinese_grammar_and_unicode_names(self):
        cases = [
            ("src/app.py里的 TODO 仍未处理。", {"files": ["src/app.py"]}),
            ("我检查了src/app.py里的记录。", {"files": ["src/app.py"]}),
            ("源码/处理器.py里的任务未完成。", {"files": ["源码/处理器.py"]}),
            ("处理器.py中的任务未完成。", {"files": ["源码/处理器.py"]}),
        ]
        for text, sins in cases:
            with self.subTest(text=text):
                self.assertTrue(ps._voice_paths_verified(text, sins))

    def test_unverified_root_filenames_and_continued_paths_are_rejected(self):
        sins = {"files": ["src/app.py", "app.py", "源码/处理器.py"]}
        for text in ("The audit found a stale TODO in secret.py.",
                     "src/app.py/unknown.py contains a hidden note.",
                     "源码/处理器.py/未知.py里的内容。"):
            with self.subTest(text=text):
                self.assertFalse(ps._voice_paths_verified(text, sins))
        for text in ("The app.py file stays on the review list.",
                     "The review remains open, e.g. until the handover.",
                     "我检查app.py里的记录。"):
            with self.subTest(text=text):
                self.assertTrue(ps._voice_paths_verified(text, sins))

    def test_code_markers_are_not_a_natural_english_clause(self):
        for text in ("TODO、FIXME、HACK、XXX，这些标记还在交接清单里。",
                     "JSON、HTTP、TODO、FIXME，这些都是代码标签。"):
            with self.subTest(text=text):
                self.assertFalse(ps._voice_language_ok(text, "mixed", {}))

    def test_short_natural_english_clauses_still_count_as_mixed(self):
        for text in ("交接还没结束；I am still here.",
                     "原始记录还在；The record remains open.",
                     "我登记了它；I kept the original receipt."):
            with self.subTest(text=text):
                self.assertTrue(ps._voice_language_ok(text, "mixed", {}))

    def test_distinct_view_of_same_repository_is_not_rejected(self):
        self.remember(self.voice)
        candidate = "The handover checklist has teeth now; I am the one holding it."
        with patch.object(ps, "llm_chat", return_value=candidate) as chat:
            result = self.plant()
        assert result is not None
        self.assertEqual(result["text"], candidate)
        self.assertEqual(chat.call_count, 1)

    def test_repeat_retries_are_bounded_and_use_one_shared_deadline(self):
        self.remember(self.voice)
        clock = [0.0]

        def reply(*_args, **_kwargs):
            clock[0] += 10.0
            return self.voice

        with patch.dict(os.environ, {"PUSH_SHIT_TIMEOUT": "30"}), \
                patch.object(ps.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(ps, "llm_chat", side_effect=reply) as chat:
            result = self.plant()
        self.assertGreaterEqual(chat.call_count, 2)
        self.assertLessEqual(chat.call_count, 3)
        timeouts = [call.kwargs.get("timeout") for call in chat.call_args_list]
        self.assertTrue(all(isinstance(value, (int, float)) for value in timeouts), timeouts)
        self.assertEqual(timeouts, [30.0, 20.0, 10.0])
        assert result is not None
        self.assertNotEqual(normalized(result["text"]), normalized(self.voice))

    def test_fallback_has_several_structures_not_one_generic_line(self):
        values = []
        with patch.object(ps, "llm_chat", return_value=None):
            for _ in range(6):
                result = self.plant()
                assert result is not None
                values.append(normalized(result["text"]))
                ps.ledger_append(str(self.repo), result["entry"])
                self.git("add", "src/app.py", "README.md")
                self.git("commit", "-m", "fixture accepted planting")
        self.assertEqual(len(set(values)), 6)

    def test_generation_rotates_themes_and_includes_recent_avoidance(self):
        self.remember(self.voice, text=self.voice, language="en", theme="handover", source="model")
        candidate = "The handover checklist has teeth now; I am the one holding it."
        with patch.object(ps, "llm_chat", return_value=candidate) as chat:
            result = self.plant()
        assert result is not None
        self.assertNotEqual(result["entry"].get("theme"), "handover")
        self.assertNotIn(self.voice, chat.call_args.args[1])
        self.assertIn("Speech act:", chat.call_args.args[1])
        self.assertNotIn("line 41", chat.call_args.args[1])

    def test_history_window_is_recent_not_an_infinite_global_blacklist(self):
        self.remember(self.voice)
        for index in range(31):
            self.remember(f"Old maintenance note number {index} about another observation.")
        with patch.object(ps, "llm_chat", return_value=self.voice):
            result = self.plant()
        assert result is not None
        self.assertEqual(result["text"], self.voice)

    def test_exhausted_candidates_skip_instead_of_planting_a_repeat(self):
        before = {name: (self.repo / name).read_bytes() for name in ("src/app.py", "README.md")}
        with patch.object(ps, "_recent_repeat", return_value=True, create=True), \
                patch.object(ps, "llm_chat", return_value=self.voice):
            result = self.plant()
        self.assertIsNone(result)
        self.assertEqual(before, {name: (self.repo / name).read_bytes() for name in before})

    def test_silent_offline_marker_is_not_reported_as_model_variety(self):
        with patch.object(ps, "server_alive", return_value=False):
            result = ps.plant_whisper(str(self.repo), self.cfg, self.sins, random.Random(1))
        assert result is not None
        self.assertTrue(result["silent"])
        self.assertEqual(result["entry"].get("source"), "silent")

    def test_mixed_fallback_contains_natural_words_from_both_languages(self):
        with patch.object(ps, "llm_chat", return_value=None):
            result = self.plant({**self.cfg, "lang": "mixed"})
        assert result is not None
        self.assertRegex(result["text"], r"[\u3400-\u9fff]")
        self.assertRegex(result["text"], r"[A-Za-z]{3}")


if __name__ == "__main__":
    unittest.main()
