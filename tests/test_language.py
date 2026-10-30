import json
import random
import re
import string
import sys
import unittest
from unittest.mock import patch

import push_shit as ps
from tests.support import RepoCase


class LanguageTests(RepoCase):
    def preferences(self):
        path = self.repo / ".git/push-shit/preferences.json"
        self.assertTrue(path.is_file(), "language selection must persist target preferences")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_english_interface_and_help_then_switch_back(self):
        output = self.panel(["lang en", "/help", "meter", "stop", "diary", "status",
                             "lang zh", "/help lang", "quit"])
        english = output.split("lang en\n", 1)[1].split("lang zh\n", 1)[0]
        self.assertIn("UI language: en", english)
        self.assertIn("Examples", english)
        self.assertIn("lang content", english)
        self.assertNotRegex(english, r"[\u3400-\u9fff]")
        self.assertIn("界面语言", output.split("lang zh\n", 1)[1])

    def test_language_persists_without_installing_or_committing(self):
        before = self.git("rev-parse", "HEAD")
        self.panel(["lang en", "quit"])
        self.assertEqual(self.preferences(), {"ui_lang": "en", "content_lang": "en"})
        self.assertFalse((self.repo / ".git/push-shit/config.json").exists())
        self.assertFalse(self.hook().exists())
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        result = self.cli(data="lang\n/help lang\nquit\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UI language: en", result.stdout)
        self.assertNotRegex(result.stdout, r"[\u3400-\u9fff]")

    def test_ui_and_content_can_be_selected_independently(self):
        output = self.panel(["lang ui en", "lang content zh", "lang", "quit"])
        self.assertEqual(self.preferences(), {"ui_lang": "en", "content_lang": "zh"})
        self.assertIn("content language: zh", output)
        english = output.split("lang ui en\n", 1)[1]
        self.assertNotRegex(english, r"[\u3400-\u9fff]")

    def test_mixed_changes_content_not_ui(self):
        self.panel(["lang en", "lang mixed", "quit"])
        self.assertEqual(self.preferences(), {"ui_lang": "en", "content_lang": "mixed"})

    def test_invalid_language_does_not_change_preferences(self):
        self.panel(["lang en", "quit"])
        before = self.preferences()
        output = self.panel(["lang fr", "lang ui mixed", "quit"])
        self.assertIn("Unsupported", output)
        self.assertEqual(self.preferences(), before)

    def test_install_preserves_preference_unless_explicitly_overridden(self):
        self.panel(["lang en", "quit"])
        self.install()
        cfg = ps.load_config(str(self.repo))
        assert cfg is not None
        self.assertEqual(cfg["lang"], "en")
        result = self.cli("install", "--lang", "zh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.preferences()["content_lang"], "zh")
        self.assertEqual(self.preferences()["ui_lang"], "en")

    def test_next_haunt_uses_saved_content_language(self):
        with patch.object(ps, "server_alive", return_value=False):
            self.panel(["lang content en", "haunt", "n", "quit"])
        cfg = ps.load_config(str(self.repo))
        assert cfg is not None
        self.assertEqual(cfg["lang"], "en")
        self.assertEqual(ps.ledger_read(str(self.repo))[0].get("language"), "en")

    def test_target_switch_loads_its_own_languages(self):
        other = self.repo / "other-target"
        other.mkdir()
        result = self.run_process(["git", "-C", other, "init"])
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.panel(["lang en", f"target {other.as_posix()}", "lang",
                             f"target {self.repo.as_posix()}", "lang", "quit"])
        self.assertIn("界面语言：zh", output)
        self.assertIn("UI language: en", output.rsplit("lang\n", 1)[1])

    def test_ui_can_change_without_a_target_for_this_session(self):
        result = self.cli(data="lang ui en\n/help lang\nquit\n",
                          extra={"GIT_DIR": str(self.repo / "not-a-git-directory")})
        self.assertEqual(result.returncode, 0, result.stderr)
        english = result.stdout.split("lang ui en\n", 1)[1]
        self.assertIn("session", english.lower())
        self.assertNotRegex(english, r"[\u3400-\u9fff]")
        self.assertFalse((self.repo / ".git/push-shit/preferences.json").exists())

    def test_catalogs_are_complete_and_english_frames_have_no_chinese_literals(self):
        for message, pair in ps.UI_TEXT.items():
            self.assertEqual(len(pair), 2, message)
            fields = [{name for _, name, _, _ in string.Formatter().parse(value) if name is not None}
                      for value in pair]
            self.assertEqual(fields[0], fields[1], message)
            self.assertNotRegex(pair[1], r"[\u3400-\u9fff]", message)
        self.assertEqual(set(ps.PANEL_HELP), set(ps.PANEL_HELP_EN))
        for value in ps.PANEL_HELP_EN.values():
            self.assertNotRegex(value, r"[\u3400-\u9fff]")

    def test_full_english_operation_flow_includes_errors_cleanup_and_uninstall(self):
        with patch.object(ps, "server_alive", return_value=False), \
                patch.object(ps, "llm_chat", return_value=None):
            output = self.panel(["lang en", "connect file:///invalid", "target missing-path",
                                 "haunt", "n", "meter", "diary", "exorcise", "uninstall",
                                 "/help", "quit"])
        english = output.split("lang en\n", 1)[1]
        self.assertNotRegex(english, r"[\u3400-\u9fff]")
        self.assertIn("Connection failed", english)
        self.assertIn("uninstall complete", english)
        self.assertIn("Examples", english)

    def test_ui_translation_does_not_translate_model_payload_or_paths(self):
        self.panel(["lang ui en", "quit"])
        payload = "保持这句中文和 D:/中文路径 原样"
        with ps.ui_scope(str(self.repo)):
            output = ps._ui("voice_source", source=ps._ui("source_model"), text=payload)
        self.assertIn("[model]", output)
        self.assertIn(payload, output)

    def test_initial_preference_failure_leaves_no_unconfigured_wrapper(self):
        args = ps.argparse.Namespace(probability=1.0, lang="en")
        with patch.object(ps, "save_preferences", side_effect=OSError("preferences read-only")):
            result = ps.cmd_install(args, str(self.repo))
        self.assertEqual(result, 1)
        self.assertFalse(self.hook().exists())
        self.assertFalse((self.repo / ".git/push-shit/config.json").exists())

    def test_preference_failure_during_install_restores_original_gate(self):
        self.hook().write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
        before = self.hook().read_bytes()
        args = ps.argparse.Namespace(probability=1.0, lang="en")
        with patch.object(ps, "save_preferences", side_effect=OSError("preferences read-only")):
            result = ps.cmd_install(args, str(self.repo))
        self.assertEqual(result, 1)
        self.assertEqual(self.hook().read_bytes(), before)
        self.assertFalse((self.repo / ".git/push-shit/config.json").exists())

    def test_preference_failure_during_reinstall_restores_managed_hook_and_config(self):
        self.install()
        before = self.hook().read_bytes()
        config_path = self.repo / ".git/push-shit/config.json"
        config_before = config_path.read_bytes()
        args = ps.argparse.Namespace(probability=1.0, lang="en")
        with patch.object(ps.sys, "executable", "C:/alternate/python.exe"), \
                patch.object(ps, "save_preferences", side_effect=OSError("preferences read-only")):
            result = ps.cmd_install(args, str(self.repo))
        self.assertEqual(result, 1)
        self.assertEqual(self.hook().read_bytes(), before)
        self.assertEqual(config_path.read_bytes(), config_before)

    def test_failed_preference_save_preserves_previous_complete_json(self):
        self.panel(["lang en", "quit"])
        path = self.repo / ".git/push-shit/preferences.json"
        before = path.read_bytes()

        def fail_after_partial_write(_data, handle, **_kwargs):
            handle.write('{"ui_lang":')
            raise OSError("simulated full disk")

        with patch.object(ps.json, "dump", side_effect=fail_after_partial_write), self.assertRaises(OSError):
            ps.save_preferences(str(self.repo), content_lang="zh")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.preferences(), {"ui_lang": "en", "content_lang": "en"})
        self.assertFalse(list(path.parent.glob("preferences-*.tmp")))

    def test_mixed_ghost_code_speaks_both_languages(self):
        result = ps.plant_ghost_code(str(self.repo), {"lang": "mixed"}, random.Random(4))
        assert result is not None
        run = self.run_process([sys.executable, "-B", self.repo / result["file"]])
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertRegex(run.stdout, r"[\u3400-\u9fff]")
        self.assertRegex(run.stdout, r"[A-Za-z]{3}")

    def test_model_prefaces_do_not_become_diary_seed_or_epitaph_content(self):
        preface = "Okay, here's a ghost diary entry, channeling pure disdain:"
        cfg = {"lang": "en"}
        sins = ps.collect_sins(str(self.repo), self.git("rev-parse", "HEAD"), ps.ZERO_SHA)
        with patch.object(ps, "llm_chat", return_value=preface):
            outputs = [ps.gen_diary_entry(cfg, sins, "one synthetic planting"),
                       ps.gen_seed_whisper(cfg), ps.gen_epitaph(cfg, "one haunting")]
        for output in outputs:
            self.assertNotIn(preface, output)
        self.assertIn("one synthetic planting", outputs[0])

    def test_mixed_fallback_diary_seed_and_epitaph_use_both_languages(self):
        cfg = {"lang": "mixed"}
        sins = ps.collect_sins(str(self.repo), self.git("rev-parse", "HEAD"), ps.ZERO_SHA)
        with patch.object(ps, "llm_chat", return_value=None):
            outputs = [ps.gen_diary_entry(cfg, sins, "one planting"),
                       ps.gen_seed_whisper(cfg), ps.gen_epitaph(cfg, "one haunting")]
        for output in outputs:
            self.assertRegex(output, r"[\u3400-\u9fff]")
            self.assertRegex(output, re.compile(r"[A-Za-z]{3}"))


if __name__ == "__main__":
    unittest.main()
